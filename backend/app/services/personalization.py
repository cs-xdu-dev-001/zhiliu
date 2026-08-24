import json

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import ContentFeedback, HermesPreference, HermesPublication, IntelligenceItem, ItemRevision, ItemTopic, PersonalizationSettings, PublicationItem

ALGORITHM_VERSION = 1


def settings(db: Session) -> PersonalizationSettings:
    record = db.get(PersonalizationSettings, 1)
    if record is None:
        record = PersonalizationSettings(id=1, auto_learning_enabled=True, algorithm_version=ALGORITHM_VERSION)
        db.add(record)
        db.flush()
    return record


def score_item(item: IntelligenceItem, *, auto_learning: bool, rules: list[HermesPreference], followed_topics: set[int], cited: bool, corrected: bool, feedback_types: set[str]) -> tuple[float, list[dict[str, object]]]:
    score = item.importance
    reasons: list[dict[str, object]] = []
    source = item.source.casefold()
    topic_names = {link.topic.name.casefold() for link in item.topic_links}
    for rule in rules:
        applies_to_kind = rule.kind in {"all", item.kind}
        matched = applies_to_kind and (
            rule.scope == "source" and rule.value.casefold() in source
            or rule.scope == "topic" and any(rule.value.casefold() in name for name in topic_names)
        )
        if matched and rule.effect == "prefer":
            delta = .12 if rule.scope == "source" else .1; score += delta
            reasons.append({"code": f"{rule.scope}_prefer", "text": f"偏好{('来源' if rule.scope == 'source' else '主题')}：{rule.value}", "delta": delta, "preferenceId": rule.id})
        elif matched and rule.effect == "avoid":
            delta = -.2; score += delta
            reasons.append({"code": f"{rule.scope}_avoid", "text": f"减少{('来源' if rule.scope == 'source' else '主题')}：{rule.value}", "delta": delta, "preferenceId": rule.id})
    matched_topics = sorted({link.topic.name for link in item.topic_links if link.topic_id in followed_topics})
    if matched_topics:
        score += .1; reasons.append({"code": "topic_followed", "text": f"已关注主题：{'、'.join(matched_topics[:2])}", "delta": .1})
    feedback_weights = {
        "useful": (.05, "你标记过有用"),
        "irrelevant": (-.25, "你标记为不相关"),
        "duplicate": (-.18, "你标记为重复内容"),
        "summary_wrong": (-.02, "摘要等待修正"),
        "source_unreliable": (-.12, "你标记来源不可靠"),
        "follow_up": (.1, "你要求持续关注"),
    }
    feedback_reasons = []
    for feedback_type in sorted(feedback_types):
        delta, text = feedback_weights[feedback_type]
        score += delta
        feedback_reasons.append({"code": f"feedback_{feedback_type}", "text": text, "delta": delta})
    reasons = feedback_reasons + reasons
    if auto_learning:
        if item.is_ignored:
            score -= .3; reasons.append({"code": "ignored", "text": "已忽略过，降低优先级", "delta": -.3})
        else:
            if item.is_saved: score += .1; reasons.append({"code": "saved", "text": "已收藏相关内容", "delta": .1})
            if item.is_read: score += .01; reasons.append({"code": "read", "text": "已阅读相关内容", "delta": .01})
        if item.tags:
            delta = min(len(item.tags), 3) * .02; score += delta; reasons.append({"code": "tagged", "text": "包含你维护的标签", "delta": delta})
        if cited: score += .08; reasons.append({"code": "report_cited", "text": "曾被报告引用", "delta": .08})
        if corrected: score += .04; reasons.append({"code": "corrected", "text": "你曾主动修正此内容", "delta": .04})
    if not reasons and score >= .75:
        reasons.append({"code": "base_importance", "text": "Hermes原始重要性较高", "delta": 0.0})
    return max(0.0, min(1.0, round(score, 4))), reasons[:4]


def recalculate(db: Session, item_ids: list[int] | None = None) -> int:
    config = settings(db)
    statement = select(IntelligenceItem).options(selectinload(IntelligenceItem.tags), selectinload(IntelligenceItem.topic_links).selectinload(ItemTopic.topic))
    if item_ids is not None:
        statement = statement.where(IntelligenceItem.id.in_(item_ids))
    items = list(db.scalars(statement).all())
    rules = list(db.scalars(select(HermesPreference).where(HermesPreference.active.is_(True), HermesPreference.scope.in_(("source", "topic")), HermesPreference.effect.in_(("prefer", "avoid")))).all())
    followed_topics = set(db.scalars(select(ItemTopic.topic_id).join(ItemTopic.topic).where(ItemTopic.topic.has(is_followed=True))).all())
    ids = [item.id for item in items]
    cited_ids = set(db.scalars(select(PublicationItem.item_id).join(HermesPublication).where(PublicationItem.item_id.in_(ids), HermesPublication.briefing_id.is_not(None))).all()) if ids else set()
    corrected_ids = set(db.scalars(select(ItemRevision.item_id).where(ItemRevision.item_id.in_(ids), ItemRevision.action.in_(("edited", "hermes_feedback", "change_corrected")))).all()) if ids else set()
    feedback_by_item: dict[int, set[str]] = {}
    if ids:
        for item_id, feedback_type in db.execute(select(ContentFeedback.item_id, ContentFeedback.feedback_type).where(ContentFeedback.item_id.in_(ids), ContentFeedback.active.is_(True))).all():
            if item_id is not None:
                feedback_by_item.setdefault(item_id, set()).add(feedback_type)
    for item in items:
        score, reasons = score_item(item, auto_learning=config.auto_learning_enabled, rules=rules, followed_topics=followed_topics, cited=item.id in cited_ids, corrected=item.id in corrected_ids, feedback_types=feedback_by_item.get(item.id, set()))
        item.personalized_score = score
        item.recommendation_reasons_json = json.dumps(reasons, ensure_ascii=False)
        item.personalization_version = config.algorithm_version
    db.flush()
    return len(items)
