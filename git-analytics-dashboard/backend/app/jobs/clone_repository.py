"""
Jobs - Clone Repository (no Celery, uses threading)
"""
import logging
import os
import shutil
import uuid
import urllib.parse

from git import Repo
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models import Repository, ProjectStatus

logger = logging.getLogger(__name__)


def _get_sync_session():
    """Create a synchronous database session."""
    sync_url = settings.DATABASE_URL.replace(
        "postgresql+asyncpg", "postgresql+psycopg2"
    )
    engine = create_engine(sync_url)
    Session = sessionmaker(bind=engine)
    return Session()


def _get_auth_url(git_url: str, access_token: str | None) -> str:
    """Inject access token into git url if provided."""
    if not access_token:
        return git_url
    
    # Example: https://github.com/owner/repo.git -> https://oauth2:token@github.com/owner/repo.git
    parsed = urllib.parse.urlparse(git_url)
    if not parsed.scheme in ["http", "https"]:
        return git_url # SSH or other not supported this way easily
        
    netloc = parsed.netloc
    if "@" in netloc:
        netloc = netloc.split("@")[1]
    
    auth_netloc = f"oauth2:{access_token}@{netloc}"
    return parsed._replace(netloc=auth_netloc).geturl()


def clone_repository(repository_id: str) -> None:
    """Clone a git repository to local disk, then trigger parsing."""
    session = _get_sync_session()
    try:
        repository = session.query(Repository).filter(
            Repository.id == uuid.UUID(repository_id)
        ).first()

        if not repository:
            logger.error(f"Repository {repository_id} not found")
            return

        repository.status = ProjectStatus.CLONING
        session.commit()

        clone_dir = os.path.join(settings.CLONE_BASE_DIR, str(repository.project_id), repository_id)

        if os.path.exists(clone_dir):
            shutil.rmtree(clone_dir)

        os.makedirs(clone_dir, exist_ok=True)

        auth_url = _get_auth_url(repository.git_url, repository.access_token)

        logger.info(f"Cloning {repository.git_url} -> {clone_dir}")
        if repository.default_branch and repository.default_branch != "main":
            Repo.clone_from(auth_url, clone_dir, branch=repository.default_branch)
        else:
            Repo.clone_from(auth_url, clone_dir)
        logger.info(f"Clone completed: {repository.git_url}")

        # Detect default branch if not specified
        if not repository.default_branch or repository.default_branch == "main":
            repo = Repo(clone_dir)
            try:
                repository.default_branch = repo.active_branch.name
            except Exception:
                repository.default_branch = "main"

        repository.status = ProjectStatus.PARSING
        session.commit()

        # Parse commits directly (same thread)
        from app.jobs.parse_commits import parse_commits
        parse_commits(repository_id)

    except Exception as exc:
        logger.error(f"Clone failed for {repository_id}: {exc}")
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


def sync_repository(repository_id: str) -> None:
    """Sync repository: git fetch + pull, then parse only new commits."""
    session = _get_sync_session()
    try:
        repository = session.query(Repository).filter(
            Repository.id == uuid.UUID(repository_id)
        ).first()

        if not repository:
            return

        clone_dir = os.path.join(settings.CLONE_BASE_DIR, str(repository.project_id), repository_id)

        if not os.path.exists(clone_dir):
            logger.info("Repo not found on disk, doing full clone")
            session.close()
            return clone_repository(repository_id)

        repository.status = ProjectStatus.SYNCING
        session.commit()

        # Update auth url for remote just in case token changed
        auth_url = _get_auth_url(repository.git_url, repository.access_token)
        repo = Repo(clone_dir)
        origin = repo.remotes.origin
        origin.set_url(auth_url)

        logger.info(f"Fetching updates for {repository.git_url}")
        origin.fetch()
        repo.git.pull('origin', repository.default_branch)

        repository.status = ProjectStatus.PARSING
        session.commit()

        from app.jobs.parse_commits import parse_commits
        parse_commits(repository_id)

    except Exception as exc:
        logger.error(f"Sync failed for {repository_id}: {exc}")
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
