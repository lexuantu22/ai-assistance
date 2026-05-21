"""
GitLab Client - Fetches LOC (Lines of Code) statistics per contributor from GitLab repositories.
"""
import os
import sys
import requests
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote as url_quote

from .file_classifier import is_test_file, is_generated_or_non_source


class GitLabClientError(Exception):
    """Custom exception for GitLab API errors"""
    pass


class GitLabClient:
    """Client for GitLab REST API - focused on LOC/commit statistics"""

    def __init__(self, token: str = None, base_url: str = None, verify_ssl: bool = True):
        self.base_url = (base_url or os.environ.get("GITLAB_URL", "https://gitlab.com")).rstrip("/")
        self.api_base = f"{self.base_url}/api/v4"
        self.token = token or os.environ.get("GITLAB_TOKEN", "")
        self.session = requests.Session()
        self.session.verify = verify_ssl
        if self.token:
            self.session.headers.update({
                "PRIVATE-TOKEN": self.token,
                "Content-Type": "application/json",
            })

    def set_token(self, token: str):
        self.token = token
        self.session.headers.update({
            "PRIVATE-TOKEN": self.token,
        })

    def test_connection(self) -> bool:
        """Test if the token is valid"""
        if not self.token:
            return False
        try:
            resp = self.session.get(f"{self.api_base}/user", timeout=10)
            print(f"[GitLabClient] test_connection status={resp.status_code} verify={self.session.verify}", file=sys.stderr, flush=True)
            return resp.status_code == 200
        except Exception as e:
            print(f"[GitLabClient] test_connection error: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
            return False

    def get_user_info(self) -> Dict[str, Any]:
        """Get authenticated user info"""
        resp = self.session.get(f"{self.api_base}/user", timeout=10)
        if resp.status_code != 200:
            raise GitLabClientError(f"Failed to get user info: {resp.status_code}")
        data = resp.json()
        return {
            "login": data.get("username", ""),
            "name": data.get("name", ""),
            "avatar_url": data.get("avatar_url", ""),
            "email": data.get("email", ""),
        }

    def _encode_project(self, owner: str, repo: str) -> str:
        """Encode owner/repo as URL-encoded project path for GitLab API"""
        return url_quote(f"{owner}/{repo}", safe="")

    def search_repos(self, owner: str) -> List[Dict[str, Any]]:
        """Search repos by group or user. Tries group first, then user."""
        # Try as group
        repos = self._list_group_projects(owner)
        if repos is not None:
            return repos
        # Try as user
        return self._list_user_projects(owner)

    def list_repos(self) -> List[Dict[str, Any]]:
        """List projects accessible by the authenticated user"""
        repos = []
        page = 1
        while page <= 5:  # limit pages
            resp = self.session.get(
                f"{self.api_base}/projects",
                params={"membership": True, "per_page": 100, "page": page, "order_by": "last_activity_at"},
                timeout=15,
            )
            if resp.status_code != 200:
                break
            data = resp.json()
            if not data:
                break
            for p in data:
                repos.append(self._format_project(p))
            page += 1
        return repos

    def _list_group_projects(self, group: str) -> Optional[List[Dict[str, Any]]]:
        """List projects in a group"""
        encoded = url_quote(group, safe="")
        resp = self.session.get(
            f"{self.api_base}/groups/{encoded}/projects",
            params={"per_page": 100, "include_subgroups": True, "order_by": "last_activity_at"},
            timeout=15,
        )
        if resp.status_code == 404:
            return None  # Not a group
        if resp.status_code != 200:
            raise GitLabClientError(f"Failed to list group projects: {resp.status_code}")
        return [self._format_project(p) for p in resp.json()]

    def _list_user_projects(self, username: str) -> List[Dict[str, Any]]:
        """List projects of a user"""
        resp = self.session.get(
            f"{self.api_base}/users/{url_quote(username, safe='')}/projects",
            params={"per_page": 100, "order_by": "last_activity_at"},
            timeout=15,
        )
        if resp.status_code != 200:
            raise GitLabClientError(f"Failed to list user projects: {resp.status_code}")
        return [self._format_project(p) for p in resp.json()]

    def _format_project(self, p: Dict) -> Dict[str, Any]:
        """Format a GitLab project into a standard repo dict"""
        path_parts = p.get("path_with_namespace", "").split("/", 1)
        return {
            "name": p.get("path", ""),
            "full_name": p.get("path_with_namespace", ""),
            "owner": path_parts[0] if len(path_parts) > 1 else "",
            "default_branch": p.get("default_branch", "main"),
            "private": p.get("visibility", "private") == "private",
            "id": p.get("id"),
        }

    def get_branches(self, owner: str, repo: str) -> List[str]:
        """List branches for a repository"""
        project_path = self._encode_project(owner, repo)
        branches = []
        page = 1
        while True:
            resp = self.session.get(
                f"{self.api_base}/projects/{project_path}/repository/branches",
                params={"per_page": 100, "page": page},
                timeout=15,
            )
            if resp.status_code != 200:
                if resp.status_code == 404:
                    raise GitLabClientError(f"Project '{owner}/{repo}' not found")
                raise GitLabClientError(f"Failed to list branches: {resp.status_code}")
            data = resp.json()
            if not data:
                break
            for b in data:
                branches.append(b.get("name", ""))
            page += 1
        return branches

    def get_loc_report_fast(
        self, owner: str, repo: str,
        since: Optional[str] = None, until: Optional[str] = None,
        branch: Optional[str] = None, split_test: bool = False,
    ) -> Dict[str, Any]:
        """
        Generate LOC report by paginating commits with stats.
        GitLab supports with_stats=true which returns additions/deletions per commit.
        """
        project_path = self._encode_project(owner, repo)

        # Collect all commits with stats
        commits_by_author = {}  # key: author_email -> aggregated data
        page = 1
        total_fetched = 0

        params = {"per_page": 100, "with_stats": True, "first_parent": True}
        if since:
            params["since"] = f"{since}T00:00:00Z"
        if until:
            params["until"] = f"{until}T23:59:59Z"
        if branch:
            params["ref_name"] = branch

        while True:
            params["page"] = page
            resp = self.session.get(
                f"{self.api_base}/projects/{project_path}/repository/commits",
                params=params,
                timeout=30,
            )
            if resp.status_code == 404:
                raise GitLabClientError(f"Project '{owner}/{repo}' not found")
            if resp.status_code != 200:
                raise GitLabClientError(f"Failed to fetch commits: {resp.status_code}")

            data = resp.json()
            if not data:
                break

            for commit in data:
                # Skip merge commits
                parent_ids = commit.get("parent_ids", [])
                if len(parent_ids) > 1:
                    continue

                email = commit.get("author_email", "").lower()
                name = commit.get("author_name", "")
                stats = commit.get("stats") or {}

                if email not in commits_by_author:
                    commits_by_author[email] = {
                        "login": email.split("@")[0] if email else name,
                        "name": name,
                        "email": email,
                        "avatar_url": "",
                        "additions": 0,
                        "deletions": 0,
                        "commits": 0,
                        "files_changed": 0,
                        "commit_shas": [],
                    }

                author = commits_by_author[email]
                author["additions"] += stats.get("additions", 0)
                author["deletions"] += stats.get("deletions", 0)
                author["commits"] += 1
                author["commit_shas"].append(commit.get("id", ""))

            total_fetched += len(data)
            print(f"[GitLab] Fetched {total_fetched} commits...", file=sys.stderr, flush=True)

            # Check next page
            next_page = resp.headers.get("x-next-page", "")
            if not next_page:
                break
            page = int(next_page)

        # If split_test, fetch file diffs for each commit to classify
        if split_test and commits_by_author:
            self._apply_split_test(project_path, commits_by_author)

        # Build member list
        members = []
        for author_data in commits_by_author.values():
            member = {
                "login": author_data["login"],
                "name": author_data["name"],
                "email": author_data["email"],
                "avatar_url": author_data["avatar_url"],
                "additions": author_data["additions"],
                "deletions": author_data["deletions"],
                "commits": author_data["commits"],
                "files_changed": author_data["files_changed"],
            }
            if split_test:
                member["code_additions"] = author_data.get("code_additions", author_data["additions"])
                member["code_deletions"] = author_data.get("code_deletions", author_data["deletions"])
                member["test_additions"] = author_data.get("test_additions", 0)
                member["test_deletions"] = author_data.get("test_deletions", 0)
            members.append(member)

        members.sort(key=lambda x: x["additions"] + x["deletions"], reverse=True)

        summary = {
            "total_additions": sum(m["additions"] for m in members),
            "total_deletions": sum(m["deletions"] for m in members),
            "total_net": sum(m["additions"] - m["deletions"] for m in members),
            "total_commits": sum(m["commits"] for m in members),
            "total_files_changed": sum(m["files_changed"] for m in members),
            "total_members": len(members),
        }
        if split_test:
            summary["total_code_additions"] = sum(m.get("code_additions", 0) for m in members)
            summary["total_code_deletions"] = sum(m.get("code_deletions", 0) for m in members)
            summary["total_test_additions"] = sum(m.get("test_additions", 0) for m in members)
            summary["total_test_deletions"] = sum(m.get("test_deletions", 0) for m in members)

        return {
            "repo": f"{owner}/{repo}",
            "since": since,
            "until": until,
            "branch": branch,
            "split_test": split_test,
            "members": members,
            "summary": summary,
        }

    def _apply_split_test(self, project_path: str, commits_by_author: Dict):
        """Fetch commit diffs and classify files as test/code for each author."""
        # Collect all commit SHAs with their author
        sha_to_email = {}
        for email, data in commits_by_author.items():
            for sha in data.get("commit_shas", []):
                sha_to_email[sha] = email
            # Initialize split fields
            data["code_additions"] = 0
            data["code_deletions"] = 0
            data["test_additions"] = 0
            data["test_deletions"] = 0

        all_shas = list(sha_to_email.keys())
        print(f"[GitLab] Fetching file details for {len(all_shas)} commits...", file=sys.stderr, flush=True)

        def _fetch_diff(sha):
            try:
                r = self.session.get(
                    f"{self.api_base}/projects/{project_path}/repository/commits/{sha}/diff",
                    params={"per_page": 200},
                    timeout=15,
                )
                if r.status_code == 200:
                    return sha, r.json()
            except Exception:
                pass
            return sha, []

        # We also need per-file additions/deletions - GitLab diff doesn't give line counts directly.
        # Instead, fetch the commit detail which has stats per commit (not per file).
        # For split_test accuracy, we need to fetch each commit with stats and parse the diff
        # to count lines in the diff content.
        def _fetch_commit_with_diff(sha):
            """Fetch commit diff and count additions/deletions per file from diff content."""
            try:
                r = self.session.get(
                    f"{self.api_base}/projects/{project_path}/repository/commits/{sha}/diff",
                    params={"per_page": 200},
                    timeout=15,
                )
                if r.status_code == 200:
                    files = []
                    for f in r.json():
                        diff_text = f.get("diff", "")
                        adds = diff_text.count("\n+") - diff_text.count("\n+++")
                        dels = diff_text.count("\n-") - diff_text.count("\n---")
                        if adds < 0:
                            adds = 0
                        if dels < 0:
                            dels = 0
                        files.append({
                            "filename": f.get("new_path") or f.get("old_path", ""),
                            "additions": adds,
                            "deletions": dels,
                        })
                    return sha, files
            except Exception:
                pass
            return sha, []

        done = 0
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_map = {
                executor.submit(_fetch_commit_with_diff, sha): sha
                for sha in all_shas
            }
            for future in as_completed(future_map):
                sha = future_map[future]
                _, files = future.result()
                email = sha_to_email[sha]
                author_data = commits_by_author[email]

                for f in files:
                    fname = f.get("filename", "")
                    if is_generated_or_non_source(fname):
                        continue
                    adds = f.get("additions", 0)
                    dels = f.get("deletions", 0)
                    if is_test_file(fname):
                        author_data["test_additions"] += adds
                        author_data["test_deletions"] += dels
                    else:
                        author_data["code_additions"] += adds
                        author_data["code_deletions"] += dels

                done += 1
                if done % 20 == 0:
                    print(f"[GitLab] File details: {done}/{len(all_shas)}...", file=sys.stderr, flush=True)

        # Recalculate total additions/deletions from split data
        for email, data in commits_by_author.items():
            if data["code_additions"] + data["test_additions"] > 0:
                data["additions"] = data["code_additions"] + data["test_additions"]
                data["deletions"] = data["code_deletions"] + data["test_deletions"]

        print(f"[GitLab] File details complete.", file=sys.stderr, flush=True)

    def get_member_commits(
        self, owner: str, repo: str, author: str,
        since: Optional[str] = None, until: Optional[str] = None,
        branch: Optional[str] = None, split_test: bool = False,
    ) -> List[Dict[str, Any]]:
        """Get commits for a specific member."""
        project_path = self._encode_project(owner, repo)
        commits = []
        page = 1

        params = {"per_page": 100, "with_stats": True, "first_parent": True}
        if since:
            params["since"] = f"{since}T00:00:00Z"
        if until:
            params["until"] = f"{until}T23:59:59Z"
        if branch:
            params["ref_name"] = branch

        while True:
            params["page"] = page
            resp = self.session.get(
                f"{self.api_base}/projects/{project_path}/repository/commits",
                params=params,
                timeout=30,
            )
            if resp.status_code != 200:
                raise GitLabClientError(f"Failed to fetch commits: {resp.status_code}")

            data = resp.json()
            if not data:
                break

            for commit in data:
                # Skip merge commits
                if len(commit.get("parent_ids", [])) > 1:
                    continue

                # Match by author name or email
                c_name = commit.get("author_name", "")
                c_email = commit.get("author_email", "")
                if author.lower() not in (c_name.lower(), c_email.lower(), c_email.split("@")[0].lower()):
                    continue

                stats = commit.get("stats") or {}
                commits.append({
                    "sha": commit.get("id", ""),
                    "message": commit.get("title", ""),
                    "full_message": commit.get("message", ""),
                    "date": commit.get("committed_date", ""),
                    "additions": stats.get("additions", 0),
                    "deletions": stats.get("deletions", 0),
                    "files_changed": stats.get("total", 0),
                    "url": commit.get("web_url", ""),
                    "author_login": c_email.split("@")[0] if c_email else c_name,
                    "author_name": c_name,
                    "avatar_url": "",
                })

            next_page = resp.headers.get("x-next-page", "")
            if not next_page:
                break
            page = int(next_page)

        # Apply split_test if needed
        if split_test and commits:
            self._apply_split_test_commits(project_path, commits)

        return commits

    def _apply_split_test_commits(self, project_path: str, commits: List[Dict]):
        """Apply test/code split to individual commits."""
        print(f"[GitLab-member] Fetching file details for {len(commits)} commits...", file=sys.stderr, flush=True)

        def _fetch_commit_diff(sha):
            try:
                r = self.session.get(
                    f"{self.api_base}/projects/{project_path}/repository/commits/{sha}/diff",
                    params={"per_page": 200},
                    timeout=15,
                )
                if r.status_code == 200:
                    files = []
                    for f in r.json():
                        diff_text = f.get("diff", "")
                        adds = diff_text.count("\n+") - diff_text.count("\n+++")
                        dels = diff_text.count("\n-") - diff_text.count("\n---")
                        if adds < 0:
                            adds = 0
                        if dels < 0:
                            dels = 0
                        files.append({
                            "filename": f.get("new_path") or f.get("old_path", ""),
                            "additions": adds,
                            "deletions": dels,
                        })
                    return files
            except Exception:
                pass
            return []

        with ThreadPoolExecutor(max_workers=10) as executor:
            future_map = {
                executor.submit(_fetch_commit_diff, c["sha"]): idx
                for idx, c in enumerate(commits)
            }
            for future in as_completed(future_map):
                idx = future_map[future]
                files = future.result()
                code_add = code_del = test_add = test_del = 0
                for f in files:
                    fname = f.get("filename", "")
                    if is_generated_or_non_source(fname):
                        continue
                    adds = f.get("additions", 0)
                    dels = f.get("deletions", 0)
                    if is_test_file(fname):
                        test_add += adds
                        test_del += dels
                    else:
                        code_add += adds
                        code_del += dels
                commits[idx]["code_additions"] = code_add
                commits[idx]["code_deletions"] = code_del
                commits[idx]["test_additions"] = test_add
                commits[idx]["test_deletions"] = test_del

        print(f"[GitLab-member] File details complete.", file=sys.stderr, flush=True)
