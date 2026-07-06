"""
Service Layer - Business Logic
"""
import logging
import re
import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException, NotFoundException, ValidationException
from app.models import Project, Repository, ProjectStatus
from app.repositories import ProjectRepository, RepositoryRepository
from app.schemas import (
    ProjectCreate,
    ProjectResponse,
    RepositoryCreate,
    RepositoryResponse,
)

logger = logging.getLogger(__name__)


class ProjectService:
    """Business logic for managing projects and repositories."""

    GIT_URL_PATTERN = re.compile(
        r"^https?://[\w.\-]+(?:/[\w.\-]+)+(\.git)?$"
    )

    def __init__(self, session: AsyncSession):
        self.session = session
        self.project_repo = ProjectRepository(session)
        self.repository_repo = RepositoryRepository(session)

    async def create_project(self, data: ProjectCreate) -> ProjectResponse:
        project = Project(
            name=data.name,
            description=data.description,
        )
        project = await self.project_repo.create(project)
        await self.session.commit()
        return ProjectResponse.model_validate(project)

    async def get_project(self, project_id: uuid.UUID) -> ProjectResponse:
        project = await self.project_repo.get_by_id(project_id)
        if not project:
            raise NotFoundException("Project not found")
        return ProjectResponse.model_validate(project)

    async def delete_project(self, project_id: uuid.UUID) -> None:
        deleted = await self.project_repo.delete(project_id)
        if not deleted:
            raise NotFoundException("Project not found")
        await self.session.commit()

    async def add_repository(self, project_id: uuid.UUID, data: RepositoryCreate) -> RepositoryResponse:
        project = await self.project_repo.get_by_id(project_id)
        if not project:
            raise NotFoundException("Project not found")

        if not self.GIT_URL_PATTERN.match(data.git_url):
            raise ValidationException("Invalid Git URL format")

        name = data.name
        if not name:
            name = data.git_url.split("/")[-1].replace(".git", "")

        try:
            repository = Repository(
                project_id=project_id,
                name=name,
                git_url=data.git_url,
                access_token=data.access_token,
                status=ProjectStatus.PENDING,
            )
            if data.branch:
                repository.default_branch = data.branch
            repository = await self.repository_repo.create(repository)
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise ConflictException("Repository with this URL already exists in project")

        # Trigger background job
        from app.core.background import run_in_background
        from app.jobs.clone_repository import clone_repository
        run_in_background(clone_repository, str(repository.id))
        logger.info(f"Repository added: {repository.name} ({repository.id})")

        return RepositoryResponse.model_validate(repository)

    async def sync_repository(self, repository_id: uuid.UUID) -> RepositoryResponse:
        repository = await self.repository_repo.get_by_id(repository_id)
        if not repository:
            raise NotFoundException("Repository not found")

        if repository.status in [
            ProjectStatus.CLONING,
            ProjectStatus.PARSING,
            ProjectStatus.CALCULATING,
            ProjectStatus.SYNCING,
        ]:
            raise ConflictException("Repository is already processing")

        await self.repository_repo.update_status(repository_id, ProjectStatus.SYNCING)
        await self.session.commit()

        from app.core.background import run_in_background
        from app.jobs.clone_repository import sync_repository
        run_in_background(sync_repository, str(repository_id))
        logger.info(f"Sync triggered for repository: {repository_id}")

        return RepositoryResponse.model_validate(repository)

    async def update_repository_branch(self, repository_id: uuid.UUID, branch: str) -> RepositoryResponse:
        repository = await self.repository_repo.get_by_id(repository_id)
        if not repository:
            raise NotFoundException("Repository not found")

        if repository.status in [
            ProjectStatus.CLONING,
            ProjectStatus.PARSING,
            ProjectStatus.CALCULATING,
            ProjectStatus.SYNCING,
        ]:
            raise ConflictException("Repository is already processing")

        # Update branch and status
        repository.default_branch = branch
        repository.status = ProjectStatus.CLONING
        repository.last_sync = None
        
        # Delete all existing commits for this repository.
        # This will cascade delete commit_files.
        from sqlalchemy import delete
        from app.models import Commit
        await self.session.execute(delete(Commit).where(Commit.repository_id == repository_id))
        
        await self.session.commit()

        # Re-clone and re-parse
        from app.core.background import run_in_background
        from app.jobs.clone_repository import clone_repository
        run_in_background(clone_repository, str(repository_id))
        logger.info(f"Branch updated to {branch}, re-cloning repository: {repository_id}")

        return RepositoryResponse.model_validate(repository)

    async def delete_repository(self, repository_id: uuid.UUID) -> None:
        deleted = await self.repository_repo.delete(repository_id)
        if not deleted:
            raise NotFoundException("Repository not found")
        await self.session.commit()
