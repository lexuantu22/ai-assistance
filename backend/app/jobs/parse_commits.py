"""
Jobs - Parse Commits (no Celery, uses threading)
"""
import logging
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models import (
    Commit,
    CommitFile,
    Developer,
    Repository,
    ProjectStatus,
)
from app.parsers import GitParser

logger = logging.getLogger(__name__)


def _get_sync_session():
    """Create a synchronous database session."""
    sync_url = settings.DATABASE_URL.replace(
        "postgresql+asyncpg", "postgresql+psycopg2"
    )
    engine = create_engine(sync_url)
    Session = sessionmaker(bind=engine)
    return Session()


def parse_commits(repository_id: str, sync_mode: bool = False) -> None:
    """Parse all commits from a cloned repository using PyDriller."""
    session = _get_sync_session()
    try:
        repository = session.query(Repository).filter(
            Repository.id == uuid.UUID(repository_id)
        ).first()

        if not repository:
            return

        clone_dir = os.path.join(settings.CLONE_BASE_DIR, str(repository.project_id), repository_id)
        parser = GitParser(clone_dir)

        # In sync mode, get the latest commit time
        since = None
        if sync_mode:
            result = session.query(func.max(Commit.commit_time)).filter(
                Commit.repository_id == uuid.UUID(repository_id)
            ).scalar()
            if result:
                since = result

        logger.info(
            f"Parsing commits for {repository.name}"
            f"{f' since {since}' if since else ' (full parse)'}"
        )

        commit_count = 0
        batch_size = 100

        for parsed_commit in parser.parse_commits(since=since):
            # Check if commit already exists
            existing = session.query(Commit.id).filter(
                Commit.sha == parsed_commit.sha,
                Commit.repository_id == uuid.UUID(repository_id),
            ).first()

            if existing:
                continue

            # Get or create developer
            developer = session.query(Developer).filter(
                Developer.email == parsed_commit.author_email
            ).first()

            if not developer:
                developer = Developer(
                    name=parsed_commit.author_name,
                    email=parsed_commit.author_email,
                )
                session.add(developer)
                session.flush()

            # Create commit
            commit = Commit(
                sha=parsed_commit.sha,
                project_id=repository.project_id,
                repository_id=uuid.UUID(repository_id),
                developer_id=developer.id,
                branch=parsed_commit.branch,
                message=parsed_commit.message,
                commit_time=parsed_commit.commit_time,
                insertions=parsed_commit.insertions,
                deletions=parsed_commit.deletions,
                files_changed=parsed_commit.files_changed,
            )
            session.add(commit)
            session.flush()

            # Create commit files
            for parsed_file in parsed_commit.files:
                commit_file = CommitFile(
                    commit_id=commit.id,
                    filename=parsed_file.filename,
                    folder=parsed_file.folder,
                    extension=parsed_file.extension,
                    language=parsed_file.language,
                    added_lines=parsed_file.added_lines,
                    deleted_lines=parsed_file.deleted_lines,
                )
                session.add(commit_file)

            commit_count += 1

            if commit_count % batch_size == 0:
                session.commit()
                logger.info(f"Processed {commit_count} commits...")

        session.commit()
        logger.info(f"Total commits parsed: {commit_count}")

        # Update repository
        repository.status = ProjectStatus.CALCULATING
        repository.last_sync = datetime.now(timezone.utc)
        session.commit()

        # Calculate statistics
        from app.jobs.calculate_statistics import calculate_statistics
        calculate_statistics(str(repository.project_id))

    except Exception as exc:
        logger.error(f"Parse failed for {repository_id}: {exc}")
        try:
            repository = session.query(Repository).filter(
                Repository.id == uuid.UUID(repository_id)
            ).first()
            if repository:
                repository.status = ProjectStatus.FAILED
                repository.error_message = str(exc)[:500]
                session.commit()
        except Exception:
            pass
    finally:
        session.close()
