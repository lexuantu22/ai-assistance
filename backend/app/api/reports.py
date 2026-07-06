"""
Global Reports API Routes
"""
import uuid
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.models import Commit, Developer, Project
from app.schemas import DeveloperResponse
from app.api.auth import get_current_user

router = APIRouter(dependencies=[Depends(get_current_user)])

class ReportDeveloperResponse(DeveloperResponse):
    project_names: List[str]


class ProjectReportResponse(BaseModel):
    project_id: uuid.UUID
    project_name: str
    total_commits: int
    total_added: int
    total_deleted: int
    active_developers: int


@router.get("/developers", response_model=dict)
async def get_global_developers_report(
    project_ids: Optional[List[uuid.UUID]] = Query(None),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Get aggregated developer statistics across all or filtered projects."""
    # Build count query
    count_q = select(func.count(func.distinct(Commit.developer_id)))
    
    # Build main query
    q = (
        select(
            Developer.id,
            Developer.name,
            Developer.email,
            func.count(Commit.id).label("commit_count"),
            func.coalesce(func.sum(Commit.insertions), 0).label("total_added_lines"),
            func.coalesce(func.sum(Commit.deletions), 0).label("total_deleted_lines"),
            func.coalesce(func.sum(Commit.files_changed), 0).label("total_files_changed"),
            func.min(Commit.commit_time).label("first_commit_date"),
            func.max(Commit.commit_time).label("last_commit_date"),
            func.array_agg(func.distinct(Project.name)).label("project_names")
        )
        .join(Developer, Commit.developer_id == Developer.id)
        .join(Project, Commit.project_id == Project.id)
        .where(Developer.is_excluded == False)
    )

    if project_ids:
        count_q = count_q.where(Commit.project_id.in_(project_ids))
        q = q.where(Commit.project_id.in_(project_ids))
        
    excluded_q = select(Developer.id).where(Developer.is_excluded == True)
    count_q = count_q.where(Commit.developer_id.notin_(excluded_q))
    if start_date:
        count_q = count_q.where(Commit.commit_time >= start_date)
        q = q.where(Commit.commit_time >= start_date)
    if end_date:
        count_q = count_q.where(Commit.commit_time <= end_date)
        q = q.where(Commit.commit_time <= end_date)

    total = (await db.execute(count_q)).scalar_one()

    offset = (page - 1) * page_size
    q = q.group_by(Developer.id, Developer.name, Developer.email).order_by(func.count(Commit.id).desc()).offset(offset).limit(page_size)
    result = await db.execute(q)

    items = []
    for row in result.all():
        items.append({
            "id": row.id,
            "name": row.name,
            "email": row.email,
            "commit_count": row.commit_count,
            "total_added": row.total_added_lines,
            "total_deleted": row.total_deleted_lines,
            "net_lines": row.total_added_lines - row.total_deleted_lines,
            "total_files_changed": row.total_files_changed,
            "first_commit": row.first_commit_date,
            "last_commit": row.last_commit_date,
            "avg_commits_per_day": 0.0,
            "project_names": row.project_names if isinstance(row.project_names, list) else [row.project_names]
        })

    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/projects", response_model=list[ProjectReportResponse])
async def get_global_projects_report(
    project_ids: Optional[List[uuid.UUID]] = Query(None),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
):
    """Compare all projects."""
    q = (
        select(
            Project.id,
            Project.name,
            func.count(Commit.id).label("total_commits"),
            func.coalesce(func.sum(Commit.insertions), 0).label("total_added"),
            func.coalesce(func.sum(Commit.deletions), 0).label("total_deleted"),
            func.count(func.distinct(Commit.developer_id)).label("active_developers")
        )
        .outerjoin(Commit, Project.id == Commit.project_id)
        .group_by(Project.id, Project.name)
        .order_by(func.count(Commit.id).desc())
    )

    if project_ids:
        q = q.where(Project.id.in_(project_ids))
    if start_date:
        q = q.where(Commit.commit_time >= start_date)
    if end_date:
        q = q.where(Commit.commit_time <= end_date)
        
    excluded_q = select(Developer.id).where(Developer.is_excluded == True)
    q = q.where((Commit.id.is_(None)) | (Commit.developer_id.notin_(excluded_q)))

    result = await db.execute(q)
    items = []
    for row in result.all():
        items.append(ProjectReportResponse(
            project_id=row.id,
            project_name=row.name,
            total_commits=row.total_commits,
            total_added=row.total_added,
            total_deleted=row.total_deleted,
            active_developers=row.active_developers
        ))

    return items
