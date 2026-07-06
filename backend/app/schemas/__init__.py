"""
Pydantic Schemas (DTOs) for API Request/Response
"""
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, HttpUrl


# ─── Project Schemas ───────────────────────────────────────────
class ProjectCreate(BaseModel):
    """Request body for creating a new project."""
    name: str = Field(..., description="Project display name")
    description: Optional[str] = Field(None, description="Project description")


class ProjectResponse(BaseModel):
    """Single project response."""
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RepositoryCreate(BaseModel):
    """Request body for adding a git repository."""
    git_url: str = Field(..., description="Git repository URL")
    name: Optional[str] = Field(None, description="Repository name")
    access_token: Optional[str] = Field(None, description="Personal Access Token for private repos")
    branch: Optional[str] = Field(None, description="Branch to checkout and analyze")


import urllib.parse
from pydantic import field_validator

class RepositoryResponse(BaseModel):
    """Single repository response."""
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    git_url: str
    default_branch: str
    status: str
    error_message: Optional[str] = None
    last_sync: Optional[datetime] = None
    created_at: datetime

    @field_validator("git_url")
    @classmethod
    def mask_git_url(cls, v: str) -> str:
        try:
            parsed = urllib.parse.urlparse(v)
            if parsed.username or parsed.password:
                # Mask credentials
                netloc = parsed.netloc
                if "@" in netloc:
                    netloc = "******@" + netloc.split("@")[-1]
                return parsed._replace(netloc=netloc).geturl()
        except Exception:
            pass
        return v

    model_config = {"from_attributes": True}


class RepositoryListResponse(BaseModel):
    """List of repositories."""
    items: List[RepositoryResponse]

    model_config = {"from_attributes": True}

 
class ProjectListResponse(BaseModel):
    """Paginated project list response."""
    items: List[ProjectResponse]
    total: int
    page: int
    page_size: int


# ─── Developer Schemas ─────────────────────────────────────────
class DeveloperExclusionUpdate(BaseModel):
    is_excluded: bool

class DeveloperResponse(BaseModel):
    """Developer info response."""
    id: uuid.UUID
    name: str
    email: str
    is_excluded: bool = False
    commit_count: int = 0
    total_added: int = 0
    total_deleted: int = 0
    net_lines: int = 0
    total_files_changed: int = 0
    first_commit: Optional[datetime] = None
    last_commit: Optional[datetime] = None
    avg_commits_per_day: float = 0.0

    model_config = {"from_attributes": True}


class DeveloperListResponse(BaseModel):
    """Paginated developer list response."""
    items: List[DeveloperResponse]
    total: int
    page: int
    page_size: int


# ─── Commit Schemas ────────────────────────────────────────────
class CommitResponse(BaseModel):
    """Commit info response."""
    id: uuid.UUID
    sha: str
    branch: Optional[str] = None
    message: Optional[str] = None
    commit_time: datetime
    insertions: int
    deletions: int
    files_changed: int
    developer_name: str = ""
    developer_email: str = ""

    model_config = {"from_attributes": True}


class CommitListResponse(BaseModel):
    """Paginated commit list response."""
    items: List[CommitResponse]
    total: int
    page: int
    page_size: int


# ─── Statistics Schemas ────────────────────────────────────────
class OverviewStatistics(BaseModel):
    """Dashboard overview statistics."""
    total_projects: int = 0
    total_commits: int = 0
    total_developers: int = 0
    total_added_lines: int = 0
    total_deleted_lines: int = 0
    total_files_changed: int = 0


class DailyStatResponse(BaseModel):
    """Daily statistics data point."""
    date: datetime
    total_commits: int
    added_lines: int
    deleted_lines: int


class MonthlyStatResponse(BaseModel):
    """Monthly statistics data point."""
    month: int
    year: int
    total_commits: int
    added_lines: int
    deleted_lines: int


class ProjectStatisticsResponse(BaseModel):
    """Full project statistics response."""
    overview: OverviewStatistics
    daily: List[DailyStatResponse] = []
    monthly: List[MonthlyStatResponse] = []


# ─── Language Schemas ──────────────────────────────────────────
class LanguageDistribution(BaseModel):
    """Language distribution data point."""
    language: str
    file_count: int
    added_lines: int
    deleted_lines: int
    percentage: float = 0.0


# ─── File Report Schemas ──────────────────────────────────────
class FileReportItem(BaseModel):
    """File report entry."""
    filename: str
    folder: Optional[str] = None
    top_developer: Optional[str] = None
    commit_count: int = 0
    added_lines: int = 0
    deleted_lines: int = 0


# ─── Folder Report Schemas ─────────────────────────────────────
class FolderReportItem(BaseModel):
    """Folder report entry."""
    folder: str
    commit_count: int = 0
    added_lines: int = 0
    deleted_lines: int = 0


# ─── Common ────────────────────────────────────────────────────
class ApiResponse(BaseModel):
    """Standard API response wrapper."""
    success: bool = True
    message: str = "OK"
    data: Optional[dict | list] = None
