"""
Jobs - Calculate Statistics (no Celery, uses threading)
"""
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import create_engine, func, delete
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models import (
    Commit,
    DailyStatistic,
    DeveloperStatistic,
    MonthlyStatistic,
    Project,
    Repository,
    ProjectStatus,
)

logger = logging.getLogger(__name__)


def _get_sync_session():
    """Create a synchronous database session."""
    sync_url = settings.DATABASE_URL.replace(
        "postgresql+asyncpg", "postgresql+psycopg2"
    )
    engine = create_engine(sync_url)
    Session = sessionmaker(bind=engine)
    return Session()


def calculate_statistics(project_id: str) -> None:
    """Calculate aggregated statistics for a project using sync SQLAlchemy."""
    session = _get_sync_session()
    try:
        project = session.query(Project).filter(
            Project.id == uuid.UUID(project_id)
        ).first()

        if not project:
            return

        pid = uuid.UUID(project_id)
        logger.info(f"Calculating statistics for {project.name}")

        # Clear existing stats
        session.execute(delete(DailyStatistic).where(DailyStatistic.project_id == pid))
        session.execute(delete(MonthlyStatistic).where(MonthlyStatistic.project_id == pid))
        session.execute(delete(DeveloperStatistic).where(DeveloperStatistic.project_id == pid))
        session.flush()

        # ─── Daily stats ────────────────────────────────────────────────────────
        daily_rows = session.query(
            func.date_trunc("day", Commit.commit_time).label("day"),
            func.count(Commit.id).label("total_commits"),
            func.coalesce(func.sum(Commit.insertions), 0).label("added"),
            func.coalesce(func.sum(Commit.deletions), 0).label("deleted"),
        ).filter(
            Commit.project_id == pid
        ).group_by("day").order_by("day").all()

        for row in daily_rows:
            session.add(DailyStatistic(
                project_id=pid,
                date=row.day,
                total_commits=row.total_commits,
                added_lines=row.added,
                deleted_lines=row.deleted,
            ))

        # ─── Monthly stats ──────────────────────────────────────────────────────
        monthly_rows = session.query(
            func.extract("month", Commit.commit_time).label("month"),
            func.extract("year", Commit.commit_time).label("year"),
            func.count(Commit.id).label("total_commits"),
            func.coalesce(func.sum(Commit.insertions), 0).label("added"),
            func.coalesce(func.sum(Commit.deletions), 0).label("deleted"),
        ).filter(
            Commit.project_id == pid
        ).group_by("year", "month").order_by("year", "month").all()

        for row in monthly_rows:
            session.add(MonthlyStatistic(
                project_id=pid,
                month=int(row.month),
                year=int(row.year),
                total_commits=row.total_commits,
                added_lines=row.added,
                deleted_lines=row.deleted,
            ))

        # ─── Developer stats ────────────────────────────────────────────────────
        dev_rows = session.query(
            Commit.developer_id,
            func.count(Commit.id).label("commit_count"),
            func.coalesce(func.sum(Commit.insertions), 0).label("total_added"),
            func.coalesce(func.sum(Commit.deletions), 0).label("total_deleted"),
            func.coalesce(func.sum(Commit.files_changed), 0).label("total_files"),
            func.min(Commit.commit_time).label("first_commit"),
            func.max(Commit.commit_time).label("last_commit"),
        ).filter(
            Commit.project_id == pid
        ).group_by(Commit.developer_id).all()

        for row in dev_rows:
            days_active = 1
            if row.first_commit and row.last_commit:
                delta = row.last_commit - row.first_commit
                days_active = max(delta.days, 1)

            session.add(DeveloperStatistic(
                developer_id=row.developer_id,
                project_id=pid,
                commit_count=row.commit_count,
                total_added=row.total_added,
                total_deleted=row.total_deleted,
                total_files_changed=row.total_files,
                first_commit=row.first_commit,
                last_commit=row.last_commit,
            ))

        # Update all CALCULATING repositories in this project to COMPLETED
        repos = session.query(Repository).filter(
            Repository.project_id == pid,
            Repository.status == ProjectStatus.CALCULATING
        ).all()
        for r in repos:
            r.status = ProjectStatus.COMPLETED

        session.commit()

        logger.info(f"Statistics completed for {project.name}")

    except Exception as exc:
        logger.error(f"Statistics failed for {project_id}: {exc}")
        # Could mark repos as failed here but we might not know which one caused it
        session.rollback()
    finally:
        session.close()
