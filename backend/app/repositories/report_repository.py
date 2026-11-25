from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.report import Report, ReportHistory


class ReportRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def add(self, report: Report) -> Report:
        self._db.add(report)
        self._db.flush()
        return report

    def add_history(
        self,
        report_id: int,
        actor_user_id: int,
        action: str,
        note: str | None = None,
    ) -> ReportHistory:
        history = ReportHistory(
            report_id=report_id,
            actor_user_id=actor_user_id,
            action=action,
            note=note,
        )
        self._db.add(history)
        self._db.flush()
        return history

    def list_for_tenant(self, tenant_id: int) -> list[Report]:
        statement = (
            select(Report)
            .where(Report.tenant_id == tenant_id)
            .order_by(Report.created_at.desc(), Report.report_id.desc())
        )
        return list(self._db.scalars(statement).all())

    def list_for_admin(
        self,
        status_filter: str | None = None,
    ) -> list[Report]:
        statement = select(Report)
        if status_filter is not None:
            statement = statement.where(Report.status == status_filter)
        statement = statement.order_by(
            Report.created_at.desc(),
            Report.report_id.desc(),
        )
        return list(self._db.scalars(statement).all())

    def get_by_id(
        self,
        report_id: int,
        *,
        for_update: bool = False,
    ) -> Report | None:
        statement = select(Report).where(Report.report_id == report_id)
        if for_update:
            statement = statement.with_for_update()
        return self._db.scalar(statement)

    def get_active_lead_dispute(
        self,
        lead_id: int,
        *,
        for_update: bool = False,
    ) -> Report | None:
        statement = (
            select(Report)
            .where(
                Report.lead_id == lead_id,
                Report.status.in_(("open", "under_review")),
            )
            .order_by(Report.created_at.desc(), Report.report_id.desc())
            .limit(1)
        )
        if for_update:
            statement = statement.with_for_update()
        return self._db.scalar(statement)

    def list_history(self, report_id: int) -> list[ReportHistory]:
        statement = (
            select(ReportHistory)
            .where(ReportHistory.report_id == report_id)
            .order_by(ReportHistory.created_at, ReportHistory.history_id)
        )
        return list(self._db.scalars(statement).all())

    def has_recent_duplicate(
        self,
        tenant_id: int,
        listing_id: int | None,
        target_user_id: int | None,
        reason: str,
        since: datetime,
        lead_id: int | None = None,
    ) -> bool:
        statement = select(Report.report_id).where(
            Report.tenant_id == tenant_id,
            Report.listing_id == listing_id,
            Report.target_user_id == target_user_id,
            Report.lead_id == lead_id,
            Report.reason == reason,
            Report.created_at >= since,
        ).limit(1)
        return self._db.scalar(statement) is not None

    def count_submissions_since(
        self,
        tenant_id: int,
        since: datetime,
    ) -> int:
        statement = select(func.count()).select_from(Report).where(
            Report.tenant_id == tenant_id,
            Report.created_at >= since,
        )
        return int(self._db.scalar(statement) or 0)
