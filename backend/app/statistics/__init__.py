"""
Statistics Calculation Module
"""
import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Commit,
    CommitFile,
    DailyStatistic,
    DeveloperStatistic,
    MonthlyStatistic,
)
from app.repositories import StatisticsRepository

logger = logging.getLogger(__name__)


class StatisticsCalculator:
    """Calculate and persist aggregated statistics for a project."""

    def __init__(self, session: AsyncSession, project_id: uuid.UUID):
        self.session = session
        self.project_id = project_id
        self.stats_repo = StatisticsRepository(session)

    async def calculate_all(self) -> None:
        """Run all statistics calculations."""
        logger.info(f"Calculating statistics for project {self.project_id}")

        # Clear existing stats
        await self.stats_repo.delete_project_stats(self.project_id)
        await self.session.flush()

        await self._calculate_daily_stats()
        await self._calculate_monthly_stats()
        await self._calculate_developer_stats()

        await self.session.commit()
        logger.info(f"Statistics calculated for project {self.project_id}")

    async def _calculate_daily_stats(self) -> None:
        """Aggregate commits by day."""
        result = await self.session.execute(
            select(
                func.date_trunc("day", Commit.commit_time).label("day"),
                func.count(Commit.id).label("total_commits"),
                func.coalesce(func.sum(Commit.insertions), 0).label("added"),
                func.coalesce(func.sum(Commit.deletions), 0).label("deleted"),
            )
            .where(Commit.project_id == self.project_id)
            .group_by("day")
            .order_by("day")
        )

        for row in result.all():
            stat = DailyStatistic(
                project_id=self.project_id,
                date=row.day,
                total_commits=row.total_commits,
                added_lines=row.added,
                deleted_lines=row.deleted,
            )
            self.session.add(stat)
        await self.session.flush()

    async def _calculate_monthly_stats(self) -> None:
        """Aggregate commits by month."""
        result = await self.session.execute(
            select(
                func.extract("month", Commit.commit_time).label("month"),
                func.extract("year", Commit.commit_time).label("year"),
                func.count(Commit.id).label("total_commits"),
                func.coalesce(func.sum(Commit.insertions), 0).label("added"),
                func.coalesce(func.sum(Commit.deletions), 0).label("deleted"),
            )
            .where(Commit.project_id == self.project_id)
            .group_by("year", "month")
            .order_by("year", "month")
        )

        for row in result.all():
            stat = MonthlyStatistic(
                project_id=self.project_id,
                month=int(row.month),
                year=int(row.year),
                total_commits=row.total_commits,
                added_lines=row.added,
                deleted_lines=row.deleted,
            )
            self.session.add(stat)
        await self.session.flush()

    async def _calculate_developer_stats(self) -> None:
        """Aggregate commits by developer."""
        result = await self.session.execute(
            select(
                Commit.developer_id,
                func.count(Commit.id).label("commit_count"),
                func.coalesce(func.sum(Commit.insertions), 0).label("total_added"),
                func.coalesce(func.sum(Commit.deletions), 0).label("total_deleted"),
                func.coalesce(func.sum(Commit.files_changed), 0).label("total_files"),
                func.min(Commit.commit_time).label("first_commit"),
                func.max(Commit.commit_time).label("last_commit"),
            )
            .where(Commit.project_id == self.project_id)
            .group_by(Commit.developer_id)
        )

        for row in result.all():
            # Calculate average commits per day
            days_active = 1
            if row.first_commit and row.last_commit:
                delta = row.last_commit - row.first_commit
                days_active = max(delta.days, 1)

            stat = DeveloperStatistic(
                developer_id=row.developer_id,
                project_id=self.project_id,
                commit_count=row.commit_count,
                total_added=row.total_added,
                total_deleted=row.total_deleted,
                total_files_changed=row.total_files,
                first_commit=row.first_commit,
                last_commit=row.last_commit,
                avg_commits_per_day=round(row.commit_count / days_active, 2),
            )
            self.session.add(stat)
        await self.session.flush()
