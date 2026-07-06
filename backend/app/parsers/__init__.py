"""
Git Repository Parser using PyDriller
"""
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Generator, Optional

from pydriller import Repository

logger = logging.getLogger(__name__)

# Extension → Language mapping
EXTENSION_LANGUAGE_MAP: dict[str, str] = {
    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".py": "Python",
    ".go": "Go",
    ".rs": "Rust",
    ".php": "PHP",
    ".cs": "C#",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".dart": "Dart",
    ".html": "HTML",
    ".htm": "HTML",
    ".css": "CSS",
    ".scss": "CSS",
    ".less": "CSS",
    ".sql": "SQL",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".md": "Markdown",
    ".markdown": "Markdown",
    ".xml": "XML",
    ".sh": "Shell",
    ".bash": "Shell",
    ".rb": "Ruby",
    ".swift": "Swift",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".hpp": "C++",
    ".r": "R",
    ".scala": "Scala",
    ".lua": "Lua",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".toml": "TOML",
    ".ini": "INI",
    ".cfg": "INI",
    ".proto": "Protocol Buffers",
    ".graphql": "GraphQL",
    ".dockerfile": "Dockerfile",
    ".tf": "Terraform",
}


def detect_language(filename: str) -> str:
    """Detect programming language from file extension."""
    ext = Path(filename).suffix.lower()
    # Special case for Dockerfile
    if Path(filename).name.lower() == "dockerfile":
        return "Dockerfile"
    return EXTENSION_LANGUAGE_MAP.get(ext, "Other")


def extract_folder(filepath: str) -> str:
    """Extract the top-level folder from a file path."""
    parts = Path(filepath).parts
    if len(parts) > 1:
        return parts[0]
    return "/"


@dataclass
class ParsedFile:
    """Parsed file modification data."""
    filename: str
    folder: str
    extension: str
    language: str
    added_lines: int = 0
    deleted_lines: int = 0


@dataclass
class ParsedCommit:
    """Parsed commit data."""
    sha: str
    author_name: str
    author_email: str
    commit_time: datetime
    branch: str = ""
    message: str = ""
    insertions: int = 0
    deletions: int = 0
    files_changed: int = 0
    files: list[ParsedFile] = field(default_factory=list)


class GitParser:
    """Parse git repository using PyDriller."""

    def __init__(self, repo_path: str):
        self.repo_path = repo_path
        if not os.path.isdir(repo_path):
            raise FileNotFoundError(f"Repository not found: {repo_path}")

    def parse_commits(
        self,
        since: Optional[datetime] = None,
        branch: Optional[str] = None,
    ) -> Generator[ParsedCommit, None, None]:
        """
        Parse all commits from the repository.
        If `since` is provided, only parse commits after that date (for sync).
        """
        kwargs: dict = {"path_to_repo": self.repo_path}
        if since:
            kwargs["since"] = since
        if branch:
            kwargs["only_in_branch"] = branch

        logger.info(
            f"Parsing commits from {self.repo_path}"
            f"{f' since {since}' if since else ''}"
        )

        count = 0
        for commit in Repository(**kwargs).traverse_commits():
            try:
                parsed_files: list[ParsedFile] = []
                total_insertions = 0
                total_deletions = 0

                for mod in commit.modified_files:
                    filepath = mod.new_path or mod.old_path or ""
                    ext = Path(filepath).suffix.lower() if filepath else ""
                    language = detect_language(filepath) if filepath else "Other"
                    folder = extract_folder(filepath) if filepath else "/"

                    added = mod.added_lines or 0
                    deleted = mod.deleted_lines or 0
                    total_insertions += added
                    total_deletions += deleted

                    parsed_files.append(
                        ParsedFile(
                            filename=filepath,
                            folder=folder,
                            extension=ext,
                            language=language,
                            added_lines=added,
                            deleted_lines=deleted,
                        )
                    )

                parsed = ParsedCommit(
                    sha=commit.hash,
                    author_name=commit.author.name or "Unknown",
                    author_email=commit.author.email or "unknown@unknown.com",
                    commit_time=commit.author_date,
                    branch=commit.branches.pop() if commit.branches else "",
                    message=(commit.msg or "")[:500],
                    insertions=total_insertions,
                    deletions=total_deletions,
                    files_changed=len(parsed_files),
                    files=parsed_files,
                )
                count += 1
                yield parsed

            except Exception as e:
                logger.warning(f"Error parsing commit {commit.hash}: {e}")
                continue

        logger.info(f"Parsed {count} commits from {self.repo_path}")
