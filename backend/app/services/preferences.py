from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import HermesPreference


class PreferenceNotFound(LookupError):
    pass


class PreferenceService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(self, *, active_only: bool = True, kind: str | None = None) -> list[HermesPreference]:
        statement = select(HermesPreference)
        if active_only:
            statement = statement.where(HermesPreference.active.is_(True))
        if kind and kind != "all":
            statement = statement.where(HermesPreference.kind.in_(("all", kind)))
        return list(
            self.db.scalars(
                statement.order_by(HermesPreference.scope, HermesPreference.effect, HermesPreference.id)
            ).all()
        )

    def save(
        self,
        *,
        scope: str,
        effect: str,
        value: str,
        kind: str = "all",
        note: str = "",
    ) -> tuple[HermesPreference, bool]:
        normalized_value = value.strip()
        normalized_note = note.strip()
        existing = self.db.scalar(
            select(HermesPreference).where(
                HermesPreference.scope == scope,
                HermesPreference.effect == effect,
                HermesPreference.value == normalized_value,
                HermesPreference.kind == kind,
            )
        )
        if existing is not None:
            existing.note = normalized_note
            existing.active = True
            self.db.commit()
            self.db.refresh(existing)
            return existing, False

        record = HermesPreference(
            scope=scope,
            effect=effect,
            value=normalized_value,
            kind=kind,
            note=normalized_note,
            active=True,
        )
        self.db.add(record)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            existing = self.db.scalar(
                select(HermesPreference).where(
                    HermesPreference.scope == scope,
                    HermesPreference.effect == effect,
                    HermesPreference.value == normalized_value,
                    HermesPreference.kind == kind,
                )
            )
            if existing is None:
                raise
            existing.note = normalized_note
            existing.active = True
            self.db.commit()
            self.db.refresh(existing)
            return existing, False
        self.db.refresh(record)
        return record, True

    def remove(self, preference_id: int) -> HermesPreference:
        record = self.db.get(HermesPreference, preference_id)
        if record is None:
            raise PreferenceNotFound("Hermes偏好不存在")
        record.active = False
        self.db.commit()
        self.db.refresh(record)
        return record

    def filters_source(self, source: str, kind: str) -> bool:
        folded = source.casefold()
        return any(
            rule.value.casefold() in folded
            for rule in self.list(kind=kind)
            if rule.scope == "source" and rule.effect == "avoid"
        )

    def adjust_importance(self, source: str, kind: str, importance: float) -> float:
        folded = source.casefold()
        preferred = any(
            rule.value.casefold() in folded
            for rule in self.list(kind=kind)
            if rule.scope == "source" and rule.effect == "prefer"
        )
        return min(1.0, importance + 0.12) if preferred else importance
