"""
Repository Layer - Data Access using Repository Pattern
"""
import uuid
from datetime import datetime
from typing import List, Optional, Sequence

from sqlalchemy import delete, func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Commit,
    CommitFile,
    DailyStatistic,
    Developer,
    DeveloperStatistic,
    MonthlyStatistic,
    Project,
    Repository,
    ProjectStatus,
)


class ProjectRepository:
    """Data access for projects."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, project: Project) -> Project:
        self.session.add(project)
        await self.session.flush()
        return project

    async def get_by_id(self, project_id: uuid.UUID) -> Optional[Project]:
        result = await self.session.execute(
            select(Project).where(Project.id == project_id)
        )
        return result.scalar_one_or_none()

    async def get_all(
        self, page: int = 1, page_size: int = 20
    ) -> tuple[Sequence[Project], int]:
        count_result = await self.session.execute(
            select(func.count(Project.id))
        )
        total = count_result.scalar_one()

        offset = (page - 1) * page_size
        result = await self.session.execute(
            select(Project)
            .order_by(Project.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        return result.scalars().all(), total

    async def delete(self, project_id: uuid.UUID) -> bool:
        result = await self.session.execute(
            delete(Project).where(Project.id == project_id)
        )
        return result.rowcount > 0


class RepositoryRepository:
    """Data access for repositories."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, repository: Repository) -> Repository:
        self.session.add(repository)
        await self.session.flush()
        return repository

    async def get_by_id(self, repository_id: uuid.UUID) -> Optional[Repository]:
        result = await self.session.execute(
            select(Repository).where(Repository.id == repository_id)
        )
        return result.scalar_one_or_none()

    async def get_by_project(self, project_id: uuid.UUID) -> Sequence[Repository]:
        result = await self.session.execute(
            select(Repository)
            .where(Repository.project_id == project_id)
            .order_by(Repository.created_at.desc())
        )
        return result.scalars().all()

    async def update_status(
        self,
        repository_id: uuid.UUID,
        status: ProjectStatus,
        error_message: Optional[str] = None,
    ) -> None:
        repository = await self.get_by_id(repository_id)
        if repository:
            repository.status = status
            repository.error_message = error_message
            # Updated_at not in Repository right now, but we can just commit

    async def delete(self, repository_id: uuid.UUID) -> bool:
        result = await self.session.execute(
            delete(Repository).where(Repository.id == repository_id)
        )
        return result.rowcount > 0


class DeveloperRepository:
    """Data access for developers."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create(self, name: str, email: str) -> Developer:
        result = await self.session.execute(
            select(Developer).where(Developer.email == email)
        )
        developer = result.scalar_one_or_none()
        if not developer:
            developer = Developer(name=name, email=email)
            self.session.add(developer)
            await self.session.flush()
        return developer

    async def get_by_project(
        self, project_id: uuid.UUID, page: int = 1, page_size: int = 20
    ) -> tuple[Sequence[DeveloperStatistic], int]:
        count_result = await self.session.execute(
            select(func.count(DeveloperStatistic.id)).where(
                DeveloperStatistic.project_id == project_id
            )
        )
        total = count_result.scalar_one()

        offset = (page - 1) * page_size
        result = await self.session.execute(
            select(DeveloperStatistic)
            .where(DeveloperStatistic.project_id == project_id)
            .order_by(DeveloperStatistic.commit_count.desc())
            .offset(offset)
            .limit(page_size)
        )
        return result.scalars().all(), total


class CommitRepository:
    """Data access for commits."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_project(
        self,
        project_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[Sequence[Commit], int]:
        count_result = await self.session.execute(
            select(func.count(Commit.id)).where(
                Commit.project_id == project_id
            )
        )
        total = count_result.scalar_one()

        offset = (page - 1) * page_size
        result = await self.session.execute(
            select(Commit)
            .where(Commit.project_id == project_id)
            .order_by(Commit.commit_time.desc())
            .offset(offset)
            .limit(page_size)
        )
        return result.scalars().all(), total


class CommitFileRepository:
    """Data access for commit files."""
    def __init__(self, session: AsyncSession):
        self.session = session


class StatisticsRepository:
    """Data access for statistics tables."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_daily_stats(
        self, project_id: uuid.UUID
    ) -> Sequence[DailyStatistic]:
        result = await self.session.execute(
            select(DailyStatistic)
            .where(DailyStatistic.project_id == project_id)
            .order_by(DailyStatistic.date.asc())
        )
        return result.scalars().all()

    async def get_monthly_stats(
        self, project_id: uuid.UUID
    ) -> Sequence[MonthlyStatistic]:
        result = await self.session.execute(
            select(MonthlyStatistic)
            .where(MonthlyStatistic.project_id == project_id)
            .order_by(MonthlyStatistic.year.asc(), MonthlyStatistic.month.asc())
        )
        return result.scalars().all()
