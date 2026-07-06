"""
REST API Routes
"""
import uuid
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database.session import get_db
from app.models import (
    Commit,
    CommitFile,
    DailyStatistic,
    Developer,
    DeveloperStatistic,
    MonthlyStatistic,
    Project,
    Repository,
)
from app.schemas import (
    ApiResponse,
    CommitListResponse,
    CommitResponse,
    DeveloperExclusionUpdate,
    DeveloperListResponse,
    DeveloperResponse,
    DailyStatResponse,
    FileReportItem,
    FolderReportItem,
    LanguageDistribution,
    MonthlyStatResponse,
    OverviewStatistics,
    ProjectCreate,
    ProjectListResponse,
    ProjectResponse,
    ProjectStatisticsResponse,
    RepositoryCreate,
    RepositoryListResponse,
    RepositoryResponse,
)
from app.services import ProjectService
from app.api.auth import get_current_user

router = APIRouter(dependencies=[Depends(get_current_user)])


# ─── Projects ──────────────────────────────────────────────────

@router.post("/projects", response_model=ProjectResponse, status_code=201)
async def create_project(
    data: ProjectCreate,
    db: AsyncSession = Depends(get_db),
):
    """Add a new project."""
    service = ProjectService(db)
    return await service.create_project(data)


@router.get("/projects", response_model=ProjectListResponse)
async def list_projects(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List all projects."""
    service = ProjectService(db)
    items, total = await service.project_repo.get_all(page, page_size)
    return ProjectListResponse(
        items=[ProjectResponse.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get project details."""
    service = ProjectService(db)
    return await service.get_project(project_id)


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delete a project."""
    service = ProjectService(db)
    await service.delete_project(project_id)


# ─── Repositories ──────────────────────────────────────────────

@router.post("/projects/{project_id}/repositories", response_model=RepositoryResponse, status_code=201)
async def add_repository(
    project_id: uuid.UUID,
    data: RepositoryCreate,
    db: AsyncSession = Depends(get_db),
):
    """Add a repository to a project."""
    service = ProjectService(db)
    return await service.add_repository(project_id, data)


@router.get("/projects/{project_id}/repositories", response_model=RepositoryListResponse)
async def list_repositories(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """List all repositories for a project."""
    service = ProjectService(db)
    repos = await service.repository_repo.get_by_project(project_id)
    return RepositoryListResponse(
        items=[RepositoryResponse.model_validate(r) for r in repos]
    )


@router.post("/repositories/{repository_id}/sync", response_model=RepositoryResponse)
async def sync_repository(
    repository_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Sync repository (git pull + parse new commits)."""
    service = ProjectService(db)
    return await service.sync_repository(repository_id)


class BranchUpdate(BaseModel):
    branch: str


@router.put("/repositories/{repository_id}/branch", response_model=RepositoryResponse)
async def update_repository_branch(
    repository_id: uuid.UUID,
    data: BranchUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update repository branch, triggering a clean re-clone and parse."""
    service = ProjectService(db)
    return await service.update_repository_branch(repository_id, data.branch)


@router.delete("/repositories/{repository_id}", status_code=204)
async def delete_repository(
    repository_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delete a repository."""
    service = ProjectService(db)
    await service.delete_repository(repository_id)


# ─── Developers ────────────────────────────────────────────────

@router.put("/developers/{developer_id}/exclusion", response_model=ApiResponse)
async def update_developer_exclusion(
    developer_id: uuid.UUID,
    data: DeveloperExclusionUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update global exclusion status for a developer."""
    result = await db.execute(select(Developer).where(Developer.id == developer_id))
    developer = result.scalar_one_or_none()
    if not developer:
        return ApiResponse(success=False, message="Developer not found")
    
    developer.is_excluded = data.is_excluded
    await db.commit()
    return ApiResponse(success=True, message=f"Developer exclusion set to {data.is_excluded}")


@router.get("/projects/{project_id}/developers", response_model=DeveloperListResponse)
async def get_project_developers(
    project_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
):
    """Get developers for a project dynamically from commits."""
    # Build base queries
    count_q = select(func.count(func.distinct(Commit.developer_id))).where(Commit.project_id == project_id)
    
    q = (
        select(
            Developer.id,
            Developer.name,
            Developer.email,
            Developer.is_excluded,
            func.count(Commit.id).label("commit_count"),
            func.coalesce(func.sum(Commit.insertions), 0).label("total_added_lines"),
            func.coalesce(func.sum(Commit.deletions), 0).label("total_deleted_lines"),
            func.coalesce(func.sum(Commit.files_changed), 0).label("total_files_changed"),
            func.min(Commit.commit_time).label("first_commit_date"),
            func.max(Commit.commit_time).label("last_commit_date"),
        )
        .join(Developer, Commit.developer_id == Developer.id)
        .where(Commit.project_id == project_id)
    )

    if start_date:
        count_q = count_q.where(Commit.commit_time >= start_date)
        q = q.where(Commit.commit_time >= start_date)
    if end_date:
        count_q = count_q.where(Commit.commit_time <= end_date)
        q = q.where(Commit.commit_time <= end_date)

    # Execute count
    total = (await db.execute(count_q)).scalar_one()

    # Execute main query
    offset = (page - 1) * page_size
    q = q.group_by(Developer.id, Developer.name, Developer.email, Developer.is_excluded).order_by(func.count(Commit.id).desc()).offset(offset).limit(page_size)
    result = await db.execute(q)

    items = []
    for row in result.all():
        items.append(DeveloperResponse(
            id=row.id,
            name=row.name,
            email=row.email,
            is_excluded=row.is_excluded,
            commit_count=row.commit_count,
            total_added=row.total_added_lines,
            total_deleted=row.total_deleted_lines,
            net_lines=row.total_added_lines - row.total_deleted_lines,
            total_files_changed=row.total_files_changed,
            first_commit=row.first_commit_date,
            last_commit=row.last_commit_date,
            avg_commits_per_day=0.0,
        ))

    return DeveloperListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


# ─── Commits ───────────────────────────────────────────────────

@router.get("/projects/{project_id}/commits", response_model=CommitListResponse)
async def get_project_commits(
    project_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    exclude_developer_ids: Optional[List[uuid.UUID]] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Get commits for a project."""
    count_q = select(func.count(Commit.id)).where(Commit.project_id == project_id)
    if start_date:
        count_q = count_q.where(Commit.commit_time >= start_date)
    if end_date:
        count_q = count_q.where(Commit.commit_time <= end_date)

    count_result = await db.execute(count_q)
    total = count_result.scalar_one()

    offset = (page - 1) * page_size
    q = (
        select(Commit, Developer)
        .join(Developer, Commit.developer_id == Developer.id)
        .where(Commit.project_id == project_id)
    )
    if start_date:
        q = q.where(Commit.commit_time >= start_date)
    if end_date:
        q = q.where(Commit.commit_time <= end_date)
        
    excluded_q = select(Developer.id).where(Developer.is_excluded == True)
    q = q.where(Commit.developer_id.notin_(excluded_q))
    count_q = count_q.where(Commit.developer_id.notin_(excluded_q))

    q = q.order_by(Commit.commit_time.desc()).offset(offset).limit(page_size)
    result = await db.execute(q)

    items = []
    for commit, dev in result.all():
        items.append(CommitResponse(
            id=commit.id,
            sha=commit.sha,
            branch=commit.branch,
            message=commit.message,
            commit_time=commit.commit_time,
            insertions=commit.insertions,
            deletions=commit.deletions,
            files_changed=commit.files_changed,
            developer_name=dev.name,
            developer_email=dev.email,
        ))

    return CommitListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


# ─── Statistics ────────────────────────────────────────────────

@router.get("/projects/{project_id}/statistics", response_model=ProjectStatisticsResponse)
async def get_project_statistics(
    project_id: uuid.UUID,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    exclude_developer_ids: Optional[List[uuid.UUID]] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Get full statistics for a project."""
    # Overview
    ov_q = select(
        func.count(Commit.id).label("total_commits"),
        func.count(func.distinct(Commit.developer_id)).label("total_devs"),
        func.coalesce(func.sum(Commit.insertions), 0).label("total_added"),
        func.coalesce(func.sum(Commit.deletions), 0).label("total_deleted"),
        func.coalesce(func.sum(Commit.files_changed), 0).label("total_files"),
    ).where(Commit.project_id == project_id)

    if start_date:
        ov_q = ov_q.where(Commit.commit_time >= start_date)
    if end_date:
        ov_q = ov_q.where(Commit.commit_time <= end_date)
        
    excluded_q = select(Developer.id).where(Developer.is_excluded == True)
    ov_q = ov_q.where(Commit.developer_id.notin_(excluded_q))

    overview_result = await db.execute(ov_q)
    ov = overview_result.one()

    # Count repositories
    repo_count = await db.execute(
        select(func.count(Repository.id))
        .where(Repository.project_id == project_id)
    )

    overview = OverviewStatistics(
        total_projects=repo_count.scalar_one(),
        total_commits=ov.total_commits,
        total_developers=ov.total_devs,
        total_added_lines=ov.total_added,
        total_deleted_lines=ov.total_deleted,
        total_files_changed=ov.total_files,
    )

    # Daily (Requires explicit join for filtering if derived from commits, but DailyStatistic is pre-aggregated!
    # Wait, DailyStatistic doesn't have developer_id! So it CANNOT be filtered dynamically here.
    # To filter dynamically, we MUST calculate it from Commits!
    daily_q = (
        select(
            func.date(Commit.commit_time).label("date"),
            func.count(Commit.id).label("total_commits"),
            func.coalesce(func.sum(Commit.insertions), 0).label("added_lines"),
            func.coalesce(func.sum(Commit.deletions), 0).label("deleted_lines"),
        )
        .where(Commit.project_id == project_id)
        .where(Commit.developer_id.notin_(excluded_q))
        .group_by(func.date(Commit.commit_time))
        .order_by(func.date(Commit.commit_time).asc())
    )
    if start_date:
        daily_q = daily_q.where(Commit.commit_time >= start_date)
    if end_date:
        daily_q = daily_q.where(Commit.commit_time <= end_date)

    daily_result = await db.execute(daily_q)
    daily = []
    for row in daily_result.all():
        daily.append(DailyStatResponse(
            date=datetime.combine(row.date, datetime.min.time()),
            total_commits=row.total_commits,
            added_lines=row.added_lines,
            deleted_lines=row.deleted_lines,
        ))

    # Monthly
    monthly_q = (
        select(
            func.extract('year', Commit.commit_time).label("year"),
            func.extract('month', Commit.commit_time).label("month"),
            func.count(Commit.id).label("total_commits"),
            func.coalesce(func.sum(Commit.insertions), 0).label("added_lines"),
            func.coalesce(func.sum(Commit.deletions), 0).label("deleted_lines"),
        )
        .where(Commit.project_id == project_id)
        .where(Commit.developer_id.notin_(excluded_q))
        .group_by(func.extract('year', Commit.commit_time), func.extract('month', Commit.commit_time))
        .order_by(func.extract('year', Commit.commit_time).asc(), func.extract('month', Commit.commit_time).asc())
    )
    if start_date:
        monthly_q = monthly_q.where(Commit.commit_time >= start_date)
    if end_date:
        monthly_q = monthly_q.where(Commit.commit_time <= end_date)

    monthly_result = await db.execute(monthly_q)
    monthly = []
    for row in monthly_result.all():
        monthly.append(MonthlyStatResponse(
            year=int(row.year),
            month=int(row.month),
            total_commits=row.total_commits,
            added_lines=row.added_lines,
            deleted_lines=row.deleted_lines,
        ))

    return ProjectStatisticsResponse(
        overview=overview, daily=daily, monthly=monthly
    )


# ─── Languages ─────────────────────────────────────────────────

@router.get("/projects/{project_id}/languages", response_model=list[LanguageDistribution])
async def get_project_languages(
    project_id: uuid.UUID,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
):
    """Get language distribution for a project."""
    q = (
        select(
            CommitFile.language,
            func.count(CommitFile.id).label("file_count"),
            func.coalesce(func.sum(CommitFile.added_lines), 0).label("added"),
            func.coalesce(func.sum(CommitFile.deleted_lines), 0).label("deleted"),
        )
        .join(Commit, CommitFile.commit_id == Commit.id)
        .where(Commit.project_id == project_id)
        .where(CommitFile.language.isnot(None))
        .where(CommitFile.language != "Other")
    )
    if start_date:
        q = q.where(Commit.commit_time >= start_date)
    if end_date:
        q = q.where(Commit.commit_time <= end_date)
        
    excluded_q = select(Developer.id).where(Developer.is_excluded == True)
    q = q.where(Commit.developer_id.notin_(excluded_q))
        
    q = q.group_by(CommitFile.language).order_by(func.count(CommitFile.id).desc())
    result = await db.execute(q)

    rows = result.all()
    total_files = sum(r.file_count for r in rows) or 1

    return [
        LanguageDistribution(
            language=r.language,
            file_count=r.file_count,
            added_lines=r.added,
            deleted_lines=r.deleted,
            percentage=round(r.file_count / total_files * 100, 2),
        )
        for r in rows
    ]


# ─── Files ─────────────────────────────────────────────────────

@router.get("/projects/{project_id}/files", response_model=list[FileReportItem])
async def get_project_files(
    project_id: uuid.UUID,
    limit: int = Query(100, ge=1, le=500),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
):
    """Get top modified files for a project."""
    q = (
        select(
            CommitFile.filename,
            CommitFile.folder,
            func.count(CommitFile.id).label("commit_count"),
            func.coalesce(func.sum(CommitFile.added_lines), 0).label("added"),
            func.coalesce(func.sum(CommitFile.deleted_lines), 0).label("deleted"),
        )
        .join(Commit, CommitFile.commit_id == Commit.id)
        .where(Commit.project_id == project_id)
    )
    if start_date:
        q = q.where(Commit.commit_time >= start_date)
    if end_date:
        q = q.where(Commit.commit_time <= end_date)
        
    excluded_q = select(Developer.id).where(Developer.is_excluded == True)
    q = q.where(Commit.developer_id.notin_(excluded_q))
        
    q = q.group_by(CommitFile.filename, CommitFile.folder).order_by(func.count(CommitFile.id).desc()).limit(limit)
    result = await db.execute(q)

    return [
        FileReportItem(
            filename=r.filename,
            folder=r.folder,
            commit_count=r.commit_count,
            added_lines=r.added,
            deleted_lines=r.deleted,
        )
        for r in result.all()
    ]


# ─── Folders ───────────────────────────────────────────────────

@router.get("/projects/{project_id}/folders", response_model=list[FolderReportItem])
async def get_project_folders(
    project_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
):
    """Get top modified folders for a project."""
    q = (
        select(
            CommitFile.folder,
            func.count(func.distinct(CommitFile.commit_id)).label("commit_count"),
            func.coalesce(func.sum(CommitFile.added_lines), 0).label("added"),
            func.coalesce(func.sum(CommitFile.deleted_lines), 0).label("deleted"),
        )
        .join(Commit, CommitFile.commit_id == Commit.id)
        .where(Commit.project_id == project_id)
        .where(CommitFile.folder.isnot(None))
    )
    
    if start_date:
        q = q.where(Commit.commit_time >= start_date)
    if end_date:
        q = q.where(Commit.commit_time <= end_date)
        
    excluded_q = select(Developer.id).where(Developer.is_excluded == True)
    q = q.where(Commit.developer_id.notin_(excluded_q))
        
    q = q.group_by(CommitFile.folder).order_by(func.count(func.distinct(CommitFile.commit_id)).desc()).limit(limit)
    result = await db.execute(q)

    return [
        FolderReportItem(
            folder=r.folder,
            commit_count=r.commit_count,
            added_lines=r.added,
            deleted_lines=r.deleted,
        )
        for r in result.all()
    ]
