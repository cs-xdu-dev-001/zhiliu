import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Briefing, ContentFeedback, HermesPreference, HermesPublication, IntelligenceItem, ItemTopic, PublicationItem, Topic
from app.services.personalization import recalculate
from app.services.preferences import PreferenceService

CONFLICTS = {
    "useful": {"irrelevant", "duplicate", "source_unreliable"},
    "follow_up": {"irrelevant"},
    "irrelevant": {"useful", "follow_up"},
    "duplicate": {"useful"},
    "source_unreliable": {"useful"},
    "summary_wrong": set(),
}


class FeedbackNotFound(LookupError):
    pass


class FeedbackConflict(ValueError):
    pass


class FeedbackVersionConflict(ValueError):
    pass


class FeedbackService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(self, *, item_id: int | None = None, briefing_id: int | None = None) -> list[ContentFeedback]:
        statement = select(ContentFeedback)
        if item_id is not None:
            statement = statement.where(ContentFeedback.item_id == item_id)
        if briefing_id is not None:
            statement = statement.where(ContentFeedback.briefing_id == briefing_id)
        return list(self.db.scalars(statement.order_by(ContentFeedback.created_at.desc(), ContentFeedback.id.desc())).all())

    def create(
        self,
        *,
        target_type: str,
        target_id: int,
        feedback_type: str,
        note: str,
        idempotency_key: str,
        apply_long_term: bool,
    ) -> tuple[ContentFeedback, bool]:
        request_hash = self._request_hash(target_type, target_id, feedback_type, note, apply_long_term)
        existing = self.db.scalar(select(ContentFeedback).where(ContentFeedback.idempotency_key == idempotency_key))
        if existing is not None:
            if existing.request_hash != request_hash:
                raise FeedbackConflict("idempotencyKey已用于另一条反馈")
            return existing, False
        item, briefing = self._target(target_type, target_id)
        if apply_long_term and briefing is not None:
            raise FeedbackConflict("报告反馈只影响当前报告；请在具体来源情报上设置长期偏好")
        topic = self._topic_for(item)
        replaced_types = CONFLICTS[feedback_type] | {feedback_type}
        for record in self.db.scalars(
            select(ContentFeedback).where(
                ContentFeedback.active.is_(True),
                ContentFeedback.item_id == (item.id if item else None),
                ContentFeedback.briefing_id == (briefing.id if briefing else None),
                ContentFeedback.feedback_type.in_(replaced_types),
            )
        ).all():
            self._revoke_effect(record)
            record.version += 1
        before = {
            "isIgnored": item.is_ignored if item else None,
            "topicFollowed": topic.is_followed if topic else None,
        }
        record = ContentFeedback(
            item_id=item.id if item else None,
            briefing_id=briefing.id if briefing else None,
            topic_id=topic.id if topic and feedback_type == "follow_up" else None,
            feedback_type=feedback_type,
            impact_scope="topic" if feedback_type == "follow_up" and topic else "current",
            note=note.strip(),
            effect_before_json=json.dumps(before),
            request_hash=request_hash,
            idempotency_key=idempotency_key,
        )
        self.db.add(record)
        try:
            self.db.flush()
        except IntegrityError as error:
            self.db.rollback()
            existing = self.db.scalar(select(ContentFeedback).where(ContentFeedback.idempotency_key == idempotency_key))
            if existing is not None and existing.request_hash == request_hash:
                return existing, False
            raise FeedbackConflict("idempotencyKey已用于另一条反馈") from error
        self._apply_current_effect(record, item, topic)
        if apply_long_term:
            self._enable_long_term(record, item or self._source_item(briefing), topic)
        self._recalculate(record, item, topic)
        self.db.commit()
        self.db.refresh(record)
        return record, True

    def update(self, feedback_id: int, *, version: int, note: str | None, apply_long_term: bool | None) -> ContentFeedback:
        record = self._record(feedback_id)
        if not record.active and apply_long_term is not None:
            raise FeedbackConflict("请先恢复反馈，再调整长期偏好")
        record = self._claim_version(record, version)
        if note is not None:
            if record.feedback_type == "summary_wrong" and not note.strip():
                raise FeedbackConflict("摘要有误时请说明需要修正的内容")
            record.note = note.strip()
        item = self.db.get(IntelligenceItem, record.item_id) if record.item_id else self._source_item(self.db.get(Briefing, record.briefing_id))
        topic = self.db.get(Topic, record.topic_id) if record.topic_id else self._topic_for(item)
        if apply_long_term is True and record.preference_id is None:
            if record.feedback_type not in {"source_unreliable", "follow_up"}:
                raise FeedbackConflict("该反馈不能形成长期偏好")
            self._enable_long_term(record, item, topic)
        elif apply_long_term is True and record.preference_id is not None:
            preference = self.db.get(HermesPreference, record.preference_id)
            if preference is None:
                raise FeedbackConflict("关联的Hermes偏好不存在")
            record.preference_was_active = preference.active
            PreferenceService(self.db).restore(record.preference_id, commit=False)
            record.impact_scope = "long_term"
        elif apply_long_term is False and record.preference_id is not None:
            if not record.preference_was_active:
                PreferenceService(self.db).remove(record.preference_id, commit=False)
            record.impact_scope = "topic" if record.feedback_type == "follow_up" and topic else "current"
        self._recalculate(record, item, topic)
        self.db.commit()
        self.db.refresh(record)
        return record

    def revoke(self, feedback_id: int, *, version: int) -> ContentFeedback:
        record = self._record(feedback_id)
        self._check_version(record, version)
        if record.active:
            record = self._claim_version(record, version)
            self._revoke_effect(record)
            item = self.db.get(IntelligenceItem, record.item_id) if record.item_id else None
            topic = self.db.get(Topic, record.topic_id) if record.topic_id else self._topic_for(item)
            self._recalculate(record, item, topic)
            self.db.commit()
            self.db.refresh(record)
        return record

    def restore(self, feedback_id: int, *, version: int) -> ContentFeedback:
        record = self._record(feedback_id)
        self._check_version(record, version)
        if not record.active:
            record = self._claim_version(record, version)
            item = self.db.get(IntelligenceItem, record.item_id) if record.item_id else self._source_item(self.db.get(Briefing, record.briefing_id))
            topic = self.db.get(Topic, record.topic_id) if record.topic_id else self._topic_for(item)
            replaced_types = CONFLICTS[record.feedback_type] | {record.feedback_type}
            for conflicting in self.db.scalars(
                select(ContentFeedback).where(
                    ContentFeedback.id != record.id,
                    ContentFeedback.active.is_(True),
                    ContentFeedback.item_id == record.item_id,
                    ContentFeedback.briefing_id == record.briefing_id,
                    ContentFeedback.feedback_type.in_(replaced_types),
                )
            ).all():
                self._revoke_effect(conflicting)
                conflicting.version += 1
            record.active = True
            record.revoked_at = None
            self._apply_current_effect(record, item, topic)
            if record.preference_id is not None and not record.preference_was_active:
                PreferenceService(self.db).restore(record.preference_id, commit=False)
            self._recalculate(record, item, topic)
            self.db.commit()
            self.db.refresh(record)
        return record

    def _target(self, target_type: str, target_id: int) -> tuple[IntelligenceItem | None, Briefing | None]:
        if target_type == "item":
            item = self.db.get(IntelligenceItem, target_id)
            if item is None:
                raise FeedbackNotFound("情报不存在")
            return item, None
        briefing = self.db.get(Briefing, target_id)
        if briefing is None:
            raise FeedbackNotFound("报告不存在")
        return None, briefing

    def _record(self, feedback_id: int) -> ContentFeedback:
        record = self.db.get(ContentFeedback, feedback_id)
        if record is None:
            raise FeedbackNotFound("反馈不存在")
        return record

    @staticmethod
    def _check_version(record: ContentFeedback, version: int) -> None:
        if record.version != version:
            raise FeedbackVersionConflict("反馈已被修改，请刷新后重试")

    def _claim_version(self, record: ContentFeedback, version: int) -> ContentFeedback:
        self._check_version(record, version)
        result = self.db.execute(
            update(ContentFeedback)
            .where(ContentFeedback.id == record.id, ContentFeedback.version == version)
            .values(version=version + 1)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            self.db.rollback()
            raise FeedbackVersionConflict("反馈已被修改，请刷新后重试")
        self.db.refresh(record)
        return record

    def _topic_for(self, item: IntelligenceItem | None) -> Topic | None:
        if item is None:
            return None
        return self.db.scalar(
            select(Topic).join(ItemTopic, ItemTopic.topic_id == Topic.id).where(
                ItemTopic.item_id == item.id,
                Topic.merged_into_id.is_(None),
            ).order_by(Topic.is_followed.desc(), Topic.is_pinned.desc(), Topic.id).limit(1)
        )

    def _source_item(self, briefing: Briefing | None) -> IntelligenceItem | None:
        if briefing is None:
            return None
        return self.db.scalar(
            select(IntelligenceItem)
            .join(PublicationItem, PublicationItem.item_id == IntelligenceItem.id)
            .join(HermesPublication, HermesPublication.id == PublicationItem.publication_id)
            .where(HermesPublication.briefing_id == briefing.id)
            .order_by(PublicationItem.ordinal)
            .limit(1)
        )

    def _apply_current_effect(self, record: ContentFeedback, item: IntelligenceItem | None, topic: Topic | None) -> None:
        if record.feedback_type == "irrelevant" and item is not None:
            item.is_ignored = True
        if record.feedback_type == "follow_up" and topic is not None:
            topic.is_followed = True

    def _enable_long_term(self, record: ContentFeedback, item: IntelligenceItem | None, topic: Topic | None) -> None:
        if record.feedback_type == "source_unreliable" and item is not None:
            existing = self.db.scalar(select(HermesPreference).where(
                HermesPreference.scope == "source",
                HermesPreference.effect == "avoid",
                HermesPreference.value == item.source,
                HermesPreference.kind == item.kind,
            ))
            record.preference_was_active = bool(existing and existing.active)
            if existing is not None:
                preference = PreferenceService(self.db).restore(existing.id, commit=False)
            else:
                preference, _ = PreferenceService(self.db).save(
                    scope="source", effect="avoid", value=item.source, kind=item.kind,
                    note=f"由反馈#{record.id}形成，可在知流撤销",
                    commit=False,
                )
        elif record.feedback_type == "follow_up" and topic is not None:
            existing = self.db.scalar(select(HermesPreference).where(
                HermesPreference.scope == "topic",
                HermesPreference.effect == "prefer",
                HermesPreference.value == topic.name,
                HermesPreference.kind == "all",
            ))
            record.preference_was_active = bool(existing and existing.active)
            if existing is not None:
                preference = PreferenceService(self.db).restore(existing.id, commit=False)
            else:
                preference, _ = PreferenceService(self.db).save(
                    scope="topic", effect="prefer", value=topic.name, kind="all",
                    note=f"由反馈#{record.id}形成，可在知流撤销",
                    commit=False,
                )
        else:
            raise FeedbackConflict("当前内容缺少可形成长期偏好的来源或主题")
        record.preference_id = preference.id
        record.impact_scope = "long_term"

    def _revoke_effect(self, record: ContentFeedback) -> None:
        before = json.loads(record.effect_before_json or "{}")
        if record.item_id and record.feedback_type == "irrelevant":
            item = self.db.get(IntelligenceItem, record.item_id)
            if item is not None:
                item.is_ignored = bool(before.get("isIgnored"))
        if record.topic_id and record.feedback_type == "follow_up":
            topic = self.db.get(Topic, record.topic_id)
            if topic is not None:
                topic.is_followed = bool(before.get("topicFollowed"))
        if record.preference_id is not None and not record.preference_was_active:
            PreferenceService(self.db).remove(record.preference_id, commit=False)
        record.active = False
        record.revoked_at = datetime.now(timezone.utc)

    def _recalculate(self, record: ContentFeedback, item: IntelligenceItem | None, topic: Topic | None) -> None:
        if record.feedback_type == "source_unreliable" and record.preference_id is not None:
            recalculate(self.db)
            return
        if record.feedback_type == "follow_up" and topic is not None:
            item_ids = list(self.db.scalars(select(ItemTopic.item_id).where(ItemTopic.topic_id == topic.id)).all())
            recalculate(self.db, item_ids=item_ids)
            return
        if item is not None:
            recalculate(self.db, item_ids=[item.id])

    @staticmethod
    def _request_hash(target_type: str, target_id: int, feedback_type: str, note: str, apply_long_term: bool) -> str:
        payload = json.dumps([target_type, target_id, feedback_type, note.strip(), apply_long_term], ensure_ascii=False)
        return hashlib.sha256(payload.encode()).hexdigest()
