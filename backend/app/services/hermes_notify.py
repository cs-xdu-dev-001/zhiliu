"""Durable Weixin outbox stored on the existing task row."""
import re
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from urllib.parse import urlsplit

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import Briefing, IntelligenceItem, Subscription, TaskRun

DELIVERY_ERRORS = {
    "failed": "Hermes微信发送失败，请检查宿主机投递服务后重试",
    "session_not_ready": "微信会话未就绪，请先给机器人发一条消息或重新配对，再重试推送",
    "unknown": "发送结果未确认，请先检查微信是否已收到；重试可能重复发送",
    "not_configured": "微信推送未启用，请先配置宿主机投递服务",
    "cancelled": "订阅已关闭微信推送",
}
RETRYABLE = ("failed", "session_not_ready", "not_configured", "unknown", "cancelled")
CLAIM_SECONDS = 300


def plain_message(message: str) -> str:
    # Hermes interprets MEDIA: as an attachment directive, even with --file -.
    message = re.sub(r"MEDIA\s*:", "MEDIA：", message, flags=re.IGNORECASE)
    return re.sub(r"\[\[[^]\n]*\]\]", "", message)


def prepare_notification(task: TaskRun, briefing: Briefing, items: list[IntelligenceItem], settings: Settings) -> None:
    if not task.subscription.notify_wechat:
        return
    base = settings.public_base_url.rstrip("/")
    parsed = urlsplit(base)
    footer = f"\n查看完整报告：{base}/reports/{briefing.id}" if parsed.scheme in {"http", "https"} and parsed.hostname else ""
    message = f"知流订阅：{task.subscription.name}\n{briefing.title[:160]}\n\n{briefing.content.strip()[:600]}"
    for item in items[:3]:
        line = f"\n\n{item.title[:90]}\n{item.url}"
        if len(message + line + footer) <= 1800:
            message += line
    task.notification_message = plain_message(message + footer)
    task.notification_status = "pending" if settings.weixin_push_enabled else "not_configured"
    task.notification_error = None if settings.weixin_push_enabled else DELIVERY_ERRORS["not_configured"]


def requeue_notification(db: Session, task: TaskRun, settings: Settings) -> None:
    if task.status != "success" or task.origin != "subscription-hermes" or not task.notification_message:
        raise ValueError("该任务没有可重试的微信通知")
    if not task.subscription.notify_wechat:
        raise ValueError("请先在订阅设置中开启微信推送")
    if not settings.weixin_push_enabled:
        raise ValueError(DELIVERY_ERRORS["not_configured"])
    result = db.execute(update(TaskRun).where(
        TaskRun.id == task.id, TaskRun.notification_status.in_(RETRYABLE),
    ).values(notification_status="pending", notification_error=None, notification_token=None,
             notification_claimed_at=None, notification_sent_at=None))
    if result.rowcount != 1:
        db.rollback()
        raise ValueError("通知已发送或正在投递，请刷新查看")
    db.commit()
    db.refresh(task)


def claim_notification(db: Session, settings: Settings) -> dict | None:
    now = datetime.now(timezone.utc)
    # An expired lease might have sent before the worker died. Never replay it
    # automatically: Hermes send does not provide delivery idempotency keys.
    db.execute(update(TaskRun).where(
        TaskRun.notification_status == "sending",
        TaskRun.notification_claimed_at < now - timedelta(seconds=CLAIM_SECONDS),
    ).values(notification_status="unknown", notification_error=DELIVERY_ERRORS["unknown"]))
    if not settings.weixin_push_enabled:
        db.commit()
        return None
    enabled = select(Subscription.id).where(Subscription.notify_wechat.is_(True))
    db.execute(update(TaskRun).where(
        TaskRun.notification_status == "pending", TaskRun.subscription_id.not_in(enabled),
    ).values(notification_status="cancelled", notification_error=DELIVERY_ERRORS["cancelled"]))
    candidate = select(TaskRun.id).where(
        TaskRun.status == "success", TaskRun.origin == "subscription-hermes",
        TaskRun.notification_status == "pending", TaskRun.notification_message.is_not(None),
        TaskRun.subscription_id.in_(enabled),
    ).order_by(TaskRun.id).limit(1).scalar_subquery()
    token = str(uuid4())
    row = db.execute(update(TaskRun).where(
        TaskRun.id == candidate, TaskRun.notification_status == "pending",
    ).values(notification_status="sending", notification_token=token, notification_claimed_at=now,
             notification_error=None).returning(TaskRun.id, TaskRun.notification_message)).first()
    payload = {"taskId": row.id, "token": token, "message": row.notification_message} if row else None
    db.commit()
    return payload


def acknowledge_notification(db: Session, task_id: int, token: str, status: str) -> bool:
    if status not in {"sent", "failed", "session_not_ready", "unknown"}:
        raise ValueError("无效的微信发送状态")
    result = db.execute(update(TaskRun).where(
        TaskRun.id == task_id, TaskRun.notification_token == token,
        TaskRun.notification_status.in_(("sending", "unknown")),
    ).values(notification_status=status, notification_error=DELIVERY_ERRORS.get(status),
             notification_sent_at=datetime.now(timezone.utc) if status == "sent" else None))
    db.commit()
    if result.rowcount:
        return True
    # A repeated acknowledgment after a lost response is harmless.
    return db.scalar(select(TaskRun.id).where(TaskRun.id == task_id,
        TaskRun.notification_token == token, TaskRun.notification_status == status)) is not None
