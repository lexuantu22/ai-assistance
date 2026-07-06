"""
SQLAlchemy Models
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Boolean,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(50), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)


class ProjectStatus(str, enum.Enum):
    """Project processing status."""
    PENDING = "pending"
    CLONING = "cloning"
    PARSING = "parsing"
    CALCULATING = "calculating"
    COMPLETED = "completed"
    FAILED = "failed"
    SYNCING = "syncing"


class Project(Base):
    __tablename__ = "projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    repositories = relationship("Repository", back_populates="project", cascade="all, delete-orphan")
    commits = relationship("Commit", back_populates="project", cascade="all, delete-orphan")
    daily_stats = relationship("DailyStatistic", back_populates="project", cascade="all, delete-orphan")
    monthly_stats = relationship("MonthlyStatistic", back_populates="project", cascade="all, delete-orphan")
    developer_stats = relationship("DeveloperStatistic", back_populates="project", cascade="all, delete-orphan")


class Repository(Base):
    __tablename__ = "repositories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = Column(String(255), nullable=False)
    git_url = Column(String(500), nullable=False)
    access_token = Column(String(255), nullable=True)
    default_branch = Column(String(100), default="main")
    status = Column(
        Enum(ProjectStatus),
        default=ProjectStatus.PENDING,
        nullable=False,
    )
    error_message = Column(Text, nullable=True)
    last_sync = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint('project_id', 'git_url', name='uix_project_git_url'),
    )

    # Relationships
    project = relationship("Project", back_populates="repositories")
    commits = relationship("Commit", back_populates="repository", cascade="all, delete-orphan")


class Developer(Base):
    __tablename__ = "developers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False, unique=True)
    is_excluded = Column(Boolean, default=False, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    commits = relationship("Commit", back_populates="developer")
    developer_stats = relationship("DeveloperStatistic", back_populates="developer")


class Commit(Base):
    __tablename__ = "commits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sha = Column(String(40), nullable=False)
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    repository_id = Column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
    )
    developer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("developers.id"),
        nullable=False,
    )
    branch = Column(String(255), nullable=True)
    message = Column(Text, nullable=True)
    commit_time = Column(DateTime(timezone=True), nullable=False)
    insertions = Column(Integer, default=0)
    deletions = Column(Integer, default=0)
    files_changed = Column(Integer, default=0)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint('repository_id', 'sha', name='uix_repository_sha'),
    )

    # Relationships
    project = relationship("Project", back_populates="commits")
    repository = relationship("Repository", back_populates="commits")
    developer = relationship("Developer", back_populates="commits")
    files = relationship("CommitFile", back_populates="commit", cascade="all, delete-orphan")


class CommitFile(Base):
    __tablename__ = "commit_files"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    commit_id = Column(
        UUID(as_uuid=True),
        ForeignKey("commits.id", ondelete="CASCADE"),
        nullable=False,
    )
    filename = Column(String(500), nullable=False)
    folder = Column(String(500), nullable=True)
    extension = Column(String(50), nullable=True)
    language = Column(String(100), nullable=True)
    added_lines = Column(Integer, default=0)
    deleted_lines = Column(Integer, default=0)

    # Relationships
    commit = relationship("Commit", back_populates="files")


class DailyStatistic(Base):
    __tablename__ = "daily_statistics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    date = Column(DateTime(timezone=True), nullable=False)
    total_commits = Column(Integer, default=0)
    added_lines = Column(Integer, default=0)
    deleted_lines = Column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint("project_id", "date", name="uq_daily_stat_project_date"),
    )

    project = relationship("Project", back_populates="daily_stats")


class MonthlyStatistic(Base):
    __tablename__ = "monthly_statistics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    month = Column(Integer, nullable=False)
    year = Column(Integer, nullable=False)
    total_commits = Column(Integer, default=0)
    added_lines = Column(Integer, default=0)
    deleted_lines = Column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint("project_id", "month", "year", name="uq_monthly_stat"),
    )

    project = relationship("Project", back_populates="monthly_stats")


class DeveloperStatistic(Base):
    __tablename__ = "developer_statistics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    developer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("developers.id"),
        nullable=False,
    )
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    commit_count = Column(Integer, default=0)
    total_added = Column(Integer, default=0)
    total_deleted = Column(Integer, default=0)
    total_files_changed = Column(Integer, default=0)
    first_commit = Column(DateTime(timezone=True), nullable=True)
    last_commit = Column(DateTime(timezone=True), nullable=True)
    avg_commits_per_day = Column(Float, default=0.0)

    __table_args__ = (
        UniqueConstraint("developer_id", "project_id", name="uq_dev_stat"),
    )

    developer = relationship("Developer", back_populates="developer_stats")
    project = relationship("Project", back_populates="developer_stats")
