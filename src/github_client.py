"""
GitHub Client - Fetches LOC (Lines of Code) statistics per contributor from GitHub repositories.
"""
import os
import sys
import requests
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from .file_classifier import is_test_file, is_generated_or_non_source


class GitHubClientError(Exception):
    """Custom exception for GitHub API errors"""
    pass


class GitHubClient:
    """Client for GitHub REST API & GraphQL - focused on LOC/commit statistics"""

    def __init__(self, token: str = None, verify_ssl: bool = True, api_url: str = None):
        self.api_base = (api_url or os.environ.get("GITHUB_API_URL", "https://api.github.com")).rstrip("/")
        self.graphql_url = f"{self.api_base}/graphql"
        self.token = token or os.environ.get("GITHUB_TOKEN", "")
        self.session = requests.Session()
        self.session.verify = verify_ssl
        if self.token:
            self.session.headers.update({
                "Authorization": f"token {self.token}",
                "Accept": "application/vnd.github.v3+json",
            })

    def set_token(self, token: str):
        self.token = token
        self.session.headers.update({
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        })

    def test_connection(self) -> bool:
        """Test if the token is valid"""
        if not self.token:
            return False
        try:
            resp = self.session.get(f"{self.api_base}/user", timeout=10)
            import sys
            print(f"[GitHubClient] test_connection status={resp.status_code} verify={self.session.verify}", file=sys.stderr, flush=True)
            return resp.status_code == 200
        except Exception as e:
            import sys
            print(f"[GitHubClient] test_connection error: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
            return False

    def get_user_info(self) -> Dict[str, Any]:
        """Get authenticated user info"""
        resp = self.session.get(f"{self.api_base}/user", timeout=10)
        if resp.status_code != 200:
            raise GitHubClientError(f"Failed to get user info: {resp.status_code}")
        return resp.json()

    def list_repos(self, owner: str = None) -> List[Dict[str, str]]:
        """List repos for an owner (user or org). If no owner, list authenticated user's repos."""
        repos = []
        if owner:
            url = f"{self.api_base}/users/{owner}/repos"
        else:
            url = f"{self.api_base}/user/repos"

        page = 1
        while True:
            resp = self.session.get(url, params={"per_page": 100, "page": page, "sort": "updated"}, timeout=15)
            if resp.status_code != 200:
                break
            data = resp.json()
            if not data:
                break
            for r in data:
                repos.append({
                    "full_name": r["full_name"],
                    "name": r["name"],
                    "owner": r["owner"]["login"],
                    "default_branch": r.get("default_branch", "main"),
                    "private": r.get("private", False),
                })
            if len(data) < 100:
                break
            page += 1
        return repos

    def search_repos(self, owner: str) -> List[Dict[str, str]]:
        """Search repos for an org/user - works for both users and orgs"""
        repos = []
        # Try org repos first, then user repos
        for endpoint in [f"/orgs/{owner}/repos", f"/users/{owner}/repos"]:
            url = f"{self.api_base}{endpoint}"
            page = 1
            while True:
                resp = self.session.get(url, params={"per_page": 100, "page": page, "sort": "updated"}, timeout=15)
                if resp.status_code != 200:
                    break
                data = resp.json()
                if not data:
                    break
                for r in data:
                    repos.append({
                        "full_name": r["full_name"],
                        "name": r["name"],
                        "owner": r["owner"]["login"],
                        "default_branch": r.get("default_branch", "main"),
                        "private": r.get("private", False),
                    })
                if len(data) < 100:
                    break
                page += 1
            if repos:
                break
        return repos

    def get_contributor_stats(self, owner: str, repo: str, max_retries: int = 10) -> List[Dict[str, Any]]:
        """
        Get contributor statistics using GitHub Stats API.
        Returns weekly additions/deletions/commits per contributor.
        Note: GitHub may return 202 (computing) on first call - needs retries.
        """
        import time
        url = f"{self.api_base}/repos/{owner}/{repo}/stats/contributors"
        for attempt in range(max_retries):
            resp = self.session.get(url, timeout=30)
            if resp.status_code == 200:
                return resp.json() or []
            if resp.status_code == 202:
                # Stats are being computed, wait with backoff (3s, 3s, 5s, 5s, 8s, ...)
                wait = 3 if attempt < 2 else 5 if attempt < 4 else 8
                time.sleep(wait)
                continue
            if resp.status_code == 204:
                return []
            raise GitHubClientError(f"Failed to get stats for {owner}/{repo}: {resp.status_code}")
        # Return None to signal that stats never became available
        return None

    def get_loc_report(
        self,
        owner: str,
        repo: str,
        since: Optional[str] = None,
        until: Optional[str] = None,
        branch: str = None,
    ) -> Dict[str, Any]:
        """
        Generate LOC report per member for a repo within a date range.

        Args:
            owner: Repository owner
            repo: Repository name
            since: Start date (YYYY-MM-DD)
            until: End date (YYYY-MM-DD)
            branch: Branch name (default: repo's default branch)

        Returns:
            Dict with 'members' list and 'summary' stats
        """
        # Parse dates for validation
        if since:
            datetime.strptime(since, "%Y-%m-%d")  # validate format
        if until:
            datetime.strptime(until, "%Y-%m-%d")  # validate format

        # Strategy: use commits API with per-commit stats for accurate per-author LOC
        members = {}
        page = 1
        params = {"per_page": 100, "page": page}
        if since:
            params["since"] = f"{since}T00:00:00Z"
        if until:
            params["until"] = f"{until}T23:59:59Z"
        if branch:
            params["sha"] = branch

        while True:
            params["page"] = page
            url = f"{self.api_base}/repos/{owner}/{repo}/commits"
            resp = self.session.get(url, params=params, timeout=20)

            if resp.status_code != 200:
                if resp.status_code == 409:
                    # Empty repo
                    return {"members": [], "summary": {"total_additions": 0, "total_deletions": 0, "total_net": 0, "total_commits": 0, "total_files_changed": 0, "total_members": 0}}
                raise GitHubClientError(f"Failed to fetch commits: {resp.status_code} - {resp.text[:200]}")

            commits = resp.json()
            if not commits:
                break

            for commit in commits:
                # Skip merge commits (more than 1 parent)
                if len(commit.get("parents", [])) > 1:
                    continue

                # Get detailed commit info with stats
                sha = commit["sha"]
                author_login = commit.get("author", {}).get("login") if commit.get("author") else None
                author_name = commit.get("commit", {}).get("author", {}).get("name", "Unknown")
                author_email = commit.get("commit", {}).get("author", {}).get("email", "")

                # Use login as key, fallback to name
                member_key = author_login or author_name

                if member_key not in members:
                    members[member_key] = {
                        "login": author_login or "",
                        "name": author_name,
                        "email": author_email,
                        "avatar_url": commit.get("author", {}).get("avatar_url", "") if commit.get("author") else "",
                        "additions": 0,
                        "deletions": 0,
                        "commits": 0,
                        "files_changed": 0,
                    }

                # Fetch per-commit stats
                detail_resp = self.session.get(
                    f"{self.api_base}/repos/{owner}/{repo}/commits/{sha}",
                    timeout=15
                )
                if detail_resp.status_code == 200:
                    detail = detail_resp.json()
                    stats = detail.get("stats", {})
                    members[member_key]["additions"] += stats.get("additions", 0)
                    members[member_key]["deletions"] += stats.get("deletions", 0)
                    members[member_key]["commits"] += 1
                    members[member_key]["files_changed"] += len(detail.get("files", []))

            if len(commits) < 100:
                break
            page += 1

        # Build result
        member_list = sorted(members.values(), key=lambda m: m["additions"] + m["deletions"], reverse=True)
        total_additions = sum(m["additions"] for m in member_list)
        total_deletions = sum(m["deletions"] for m in member_list)
        total_commits = sum(m["commits"] for m in member_list)
        total_files = sum(m["files_changed"] for m in member_list)

        return {
            "repo": f"{owner}/{repo}",
            "since": since,
            "until": until,
            "branch": branch,
            "members": member_list,
            "summary": {
                "total_additions": total_additions,
                "total_deletions": total_deletions,
                "total_net": total_additions - total_deletions,
                "total_commits": total_commits,
                "total_files_changed": total_files,
                "total_members": len(member_list),
            },
        }

    def get_loc_report_fast(
        self,
        owner: str,
        repo: str,
        since: Optional[str] = None,
        until: Optional[str] = None,
        branch: str = None,
        split_test: bool = False,
    ) -> Dict[str, Any]:
        """
        Fast LOC report - tries GraphQL first (efficient), falls back to Stats API.
        """
        # Try GraphQL first - most efficient and reliable
        try:
            return self.get_loc_report_graphql(owner, repo, since=since, until=until, branch=branch, split_test=split_test)
        except GitHubClientError as e:
            print(f"[GitHubClient] GraphQL failed: {e}, trying Stats API...", file=sys.stderr, flush=True)

        # Fallback: Stats API (weekly granularity)
        stats = self.get_contributor_stats(owner, repo, max_retries=5)
        if stats is None or not stats:
            return self._empty_report(owner, repo, since, until)
            return {
                "repo": f"{owner}/{repo}",
                "since": since,
                "until": until,
                "members": [],
                "summary": {"total_additions": 0, "total_deletions": 0, "total_net": 0, "total_commits": 0, "total_members": 0},
            }

        since_ts = int(datetime.strptime(since, "%Y-%m-%d").timestamp()) if since else 0
        until_ts = int(datetime.strptime(until, "%Y-%m-%d").replace(hour=23, minute=59, second=59).timestamp()) if until else int(datetime.now().timestamp())

        member_list = []
        for contributor in stats:
            author = contributor.get("author", {})
            additions = 0
            deletions = 0
            commits = 0

            for week in contributor.get("weeks", []):
                week_ts = week["w"]
                # Week spans 7 days from week_ts
                if week_ts >= since_ts and week_ts <= until_ts:
                    additions += week["a"]
                    deletions += week["d"]
                    commits += week["c"]

            if commits > 0:
                member_list.append({
                    "login": author.get("login", ""),
                    "name": author.get("login", "Unknown"),
                    "email": "",
                    "avatar_url": author.get("avatar_url", ""),
                    "additions": additions,
                    "deletions": deletions,
                    "commits": commits,
                    "files_changed": 0,
                })

        member_list.sort(key=lambda m: m["additions"] + m["deletions"], reverse=True)
        total_additions = sum(m["additions"] for m in member_list)
        total_deletions = sum(m["deletions"] for m in member_list)
        total_commits = sum(m["commits"] for m in member_list)

        return {
            "repo": f"{owner}/{repo}",
            "since": since,
            "until": until,
            "members": member_list,
            "summary": {
                "total_additions": total_additions,
                "total_deletions": total_deletions,
                "total_net": total_additions - total_deletions,
                "total_commits": total_commits,
                "total_members": len(member_list),
            },
        }

    def get_loc_report_graphql(
        self,
        owner: str,
        repo: str,
        since: Optional[str] = None,
        until: Optional[str] = None,
        branch: str = None,
        split_test: bool = False,
    ) -> Dict[str, Any]:
        """
        LOC report using GitHub GraphQL API - efficient batch fetching.
        Gets 100 commits per request with additions/deletions included.
        If split_test=True, fetches per-file details to separate test vs code LOC.
        """
        since_iso = f"{since}T00:00:00Z" if since else None
        until_iso = f"{until}T23:59:59Z" if until else None

        query = """
        query($owner: String!, $repo: String!, $first: Int!, $cursor: String, $since: GitTimestamp, $until: GitTimestamp) {
          repository(owner: $owner, name: $repo) {
            defaultBranchRef {
              target {
                ... on Commit {
                  history(first: $first, after: $cursor, since: $since, until: $until) {
                    totalCount
                    pageInfo {
                      hasNextPage
                      endCursor
                    }
                    nodes {
                      oid
                      additions
                      deletions
                      changedFilesIfAvailable
                      parents {
                        totalCount
                      }
                      author {
                        name
                        email
                        user {
                          login
                          avatarUrl
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """

        # If branch is specified, use ref query instead
        if branch:
            query = """
            query($owner: String!, $repo: String!, $first: Int!, $cursor: String, $since: GitTimestamp, $until: GitTimestamp, $branch: String!) {
              repository(owner: $owner, name: $repo) {
                ref(qualifiedName: $branch) {
                  target {
                    ... on Commit {
                      history(first: $first, after: $cursor, since: $since, until: $until) {
                        totalCount
                        pageInfo {
                          hasNextPage
                          endCursor
                        }
                        nodes {
                          oid
                          additions
                          deletions
                          changedFilesIfAvailable
                          parents {
                            totalCount
                          }
                          author {
                            name
                            email
                            user {
                              login
                              avatarUrl
                            }
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
            """

        members = {}
        commit_shas = []  # (oid, member_key) for test/code split
        cursor = None
        total_fetched = 0

        while True:
            variables = {
                "owner": owner,
                "repo": repo,
                "first": 100,
                "cursor": cursor,
                "since": since_iso,
                "until": until_iso,
            }
            if branch:
                variables["branch"] = f"refs/heads/{branch}"

            resp = self.session.post(
                self.graphql_url,
                json={"query": query, "variables": variables},
                headers={"Authorization": f"bearer {self.token}"},
                timeout=30,
            )

            if resp.status_code != 200:
                raise GitHubClientError(f"GraphQL request failed: {resp.status_code} - {resp.text[:300]}")

            result = resp.json()

            if "errors" in result:
                error_msg = result["errors"][0].get("message", "Unknown GraphQL error")
                raise GitHubClientError(f"GraphQL error: {error_msg}")

            repo_data = result.get("data", {}).get("repository")
            if not repo_data:
                raise GitHubClientError("Repository not found or not accessible")

            if branch:
                ref_data = repo_data.get("ref")
                if not ref_data:
                    raise GitHubClientError(f"Branch '{branch}' not found")
                history = ref_data["target"]["history"]
            else:
                default_ref = repo_data.get("defaultBranchRef")
                if not default_ref:
                    return self._empty_report(owner, repo, since, until, branch)
                history = default_ref["target"]["history"]

            nodes = history.get("nodes", [])
            page_info = history.get("pageInfo", {})

            for node in nodes:
                # Skip merge commits (more than 1 parent)
                if node.get("parents", {}).get("totalCount", 1) > 1:
                    continue

                author_info = node.get("author", {})
                user_info = author_info.get("user") or {}
                login = user_info.get("login", "")
                name = author_info.get("name", "Unknown")
                email = author_info.get("email", "")
                avatar = user_info.get("avatarUrl", "")

                member_key = login or name

                if member_key not in members:
                    members[member_key] = {
                        "login": login,
                        "name": name,
                        "email": email,
                        "avatar_url": avatar,
                        "additions": 0,
                        "deletions": 0,
                        "commits": 0,
                        "files_changed": 0,
                    }

                members[member_key]["additions"] += node.get("additions", 0)
                members[member_key]["deletions"] += node.get("deletions", 0)
                members[member_key]["commits"] += 1
                members[member_key]["files_changed"] += node.get("changedFilesIfAvailable", 0) or 0

                if split_test:
                    commit_shas.append((node.get("oid", ""), member_key))

            total_fetched += len(nodes)
            print(f"[GraphQL] Fetched {total_fetched} commits...", file=sys.stderr, flush=True)

            if page_info.get("hasNextPage") and page_info.get("endCursor"):
                cursor = page_info["endCursor"]
            else:
                break

        # Test/Code split: fetch file details for each commit
        if split_test and commit_shas:
            for m in members.values():
                m["code_additions"] = 0
                m["code_deletions"] = 0
                m["test_additions"] = 0
                m["test_deletions"] = 0

            from concurrent.futures import ThreadPoolExecutor, as_completed

            def _fetch_files(sha):
                try:
                    r = self.session.get(
                        f"{self.api_base}/repos/{owner}/{repo}/commits/{sha}",
                        timeout=15
                    )
                    if r.status_code == 200:
                        return r.json().get("files", [])
                except Exception:
                    pass
                return []

            print(f"[GraphQL] Fetching file details for {len(commit_shas)} commits...", file=sys.stderr, flush=True)
            with ThreadPoolExecutor(max_workers=10) as executor:
                future_map = {
                    executor.submit(_fetch_files, sha): member_key
                    for sha, member_key in commit_shas
                }
                done = 0
                for future in as_completed(future_map):
                    member_key = future_map[future]
                    files = future.result()
                    for f in files:
                        fname = f.get("filename", "")
                        if self._is_generated_or_non_source(fname):
                            continue
                        adds = f.get("additions", 0)
                        dels = f.get("deletions", 0)
                        if self._is_test_file(fname):
                            members[member_key]["test_additions"] += adds
                            members[member_key]["test_deletions"] += dels
                        else:
                            members[member_key]["code_additions"] += adds
                            members[member_key]["code_deletions"] += dels
                    done += 1
                    if done % 20 == 0:
                        print(f"[GraphQL] File details: {done}/{len(commit_shas)}...", file=sys.stderr, flush=True)
            print(f"[GraphQL] File details complete.", file=sys.stderr, flush=True)

        # Build result
        member_list = sorted(members.values(), key=lambda m: m["additions"] + m["deletions"], reverse=True)
        total_additions = sum(m["additions"] for m in member_list)
        total_deletions = sum(m["deletions"] for m in member_list)
        total_commits = sum(m["commits"] for m in member_list)
        total_files = sum(m["files_changed"] for m in member_list)

        summary = {
            "total_additions": total_additions,
            "total_deletions": total_deletions,
            "total_net": total_additions - total_deletions,
            "total_commits": total_commits,
            "total_files_changed": total_files,
            "total_members": len(member_list),
        }

        if split_test:
            summary["total_code_additions"] = sum(m.get("code_additions", 0) for m in member_list)
            summary["total_code_deletions"] = sum(m.get("code_deletions", 0) for m in member_list)
            summary["total_test_additions"] = sum(m.get("test_additions", 0) for m in member_list)
            summary["total_test_deletions"] = sum(m.get("test_deletions", 0) for m in member_list)

        return {
            "repo": f"{owner}/{repo}",
            "since": since,
            "until": until,
            "branch": branch,
            "split_test": split_test,
            "members": member_list,
            "summary": summary,
        }
        return {
            "repo": f"{owner}/{repo}",
            "since": since,
            "until": until,
            "branch": branch,
            "members": [],
            "summary": {
                "total_additions": 0, "total_deletions": 0, "total_net": 0,
                "total_commits": 0, "total_files_changed": 0, "total_members": 0,
            },
        }

    @staticmethod
    def _is_test_file(filepath: str) -> bool:
        return is_test_file(filepath)

    @staticmethod
    def _is_generated_or_non_source(filepath: str) -> bool:
        return is_generated_or_non_source(filepath)

    def get_branches(self, owner: str, repo: str) -> List[str]:
        """List branches for a repository"""
        branches = []
        page = 1
        while True:
            resp = self.session.get(
                f"{self.api_base}/repos/{owner}/{repo}/branches",
                params={"per_page": 100, "page": page},
                timeout=15
            )
            if resp.status_code != 200:
                break
            data = resp.json()
            if not data:
                break
            branches.extend([b["name"] for b in data])
            if len(data) < 100:
                break
            page += 1
        return branches

    def get_member_commits(
        self,
        owner: str,
        repo: str,
        author: str,
        since: Optional[str] = None,
        until: Optional[str] = None,
        branch: str = None,
        split_test: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Get list of commits for a specific author with details.
        Skips merge commits (consistent with LOC report).

        Args:
            owner: Repository owner
            repo: Repository name
            author: Author login or name
            since: Start date (YYYY-MM-DD)
            until: End date (YYYY-MM-DD)
            branch: Branch name

        Returns:
            List of commit details
        """
        since_iso = f"{since}T00:00:00Z" if since else None
        until_iso = f"{until}T23:59:59Z" if until else None

        query = """
        query($owner: String!, $repo: String!, $first: Int!, $cursor: String, $since: GitTimestamp, $until: GitTimestamp, $branch: String!) {
          repository(owner: $owner, name: $repo) {
            ref(qualifiedName: $branch) {
              target {
                ... on Commit {
                  history(first: $first, after: $cursor, since: $since, until: $until) {
                    pageInfo { hasNextPage endCursor }
                    nodes {
                      oid
                      messageHeadline
                      message
                      committedDate
                      additions
                      deletions
                      changedFilesIfAvailable
                      url
                      parents { totalCount }
                      author {
                        name
                        email
                        user { login avatarUrl }
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """

        query_default = """
        query($owner: String!, $repo: String!, $first: Int!, $cursor: String, $since: GitTimestamp, $until: GitTimestamp) {
          repository(owner: $owner, name: $repo) {
            defaultBranchRef {
              target {
                ... on Commit {
                  history(first: $first, after: $cursor, since: $since, until: $until) {
                    pageInfo { hasNextPage endCursor }
                    nodes {
                      oid
                      messageHeadline
                      message
                      committedDate
                      additions
                      deletions
                      changedFilesIfAvailable
                      url
                      parents { totalCount }
                      author {
                        name
                        email
                        user { login avatarUrl }
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """

        commits = []
        cursor = None
        use_branch = bool(branch)

        while True:
            variables = {
                "owner": owner,
                "repo": repo,
                "first": 100,
                "cursor": cursor,
                "since": since_iso,
                "until": until_iso,
            }
            if use_branch:
                variables["branch"] = f"refs/heads/{branch}"

            resp = self.session.post(
                self.graphql_url,
                json={"query": query if use_branch else query_default, "variables": variables},
                headers={"Authorization": f"bearer {self.token}"},
                timeout=30,
            )

            if resp.status_code != 200:
                raise GitHubClientError(f"GraphQL request failed: {resp.status_code}")

            result = resp.json()
            if "errors" in result:
                raise GitHubClientError(f"GraphQL error: {result['errors'][0].get('message', '')}")

            repo_data = result.get("data", {}).get("repository")
            if not repo_data:
                break

            if use_branch:
                ref_data = repo_data.get("ref")
                if not ref_data:
                    raise GitHubClientError(f"Branch '{branch}' not found")
                history = ref_data["target"]["history"]
            else:
                default_ref = repo_data.get("defaultBranchRef")
                if not default_ref:
                    break
                history = default_ref["target"]["history"]

            nodes = history.get("nodes", [])
            page_info = history.get("pageInfo", {})

            for node in nodes:
                # Skip merge commits
                if node.get("parents", {}).get("totalCount", 1) > 1:
                    continue

                author_info = node.get("author", {})
                user_info = author_info.get("user") or {}
                login = user_info.get("login", "")
                name = author_info.get("name", "")

                # Match by login or name
                if login != author and name != author:
                    continue

                commits.append({
                    "sha": node.get("oid", ""),
                    "message": node.get("messageHeadline", ""),
                    "full_message": node.get("message", ""),
                    "date": node.get("committedDate", ""),
                    "additions": node.get("additions", 0),
                    "deletions": node.get("deletions", 0),
                    "files_changed": node.get("changedFilesIfAvailable", 0) or 0,
                    "url": node.get("url", ""),
                    "author_login": login,
                    "author_name": name,
                    "avatar_url": user_info.get("avatarUrl", ""),
                })

            if page_info.get("hasNextPage") and page_info.get("endCursor"):
                cursor = page_info["endCursor"]
            else:
                break

        if split_test and commits:
            from concurrent.futures import ThreadPoolExecutor, as_completed

            def _fetch_files(sha):
                try:
                    r = self.session.get(
                        f"{self.api_base}/repos/{owner}/{repo}/commits/{sha}",
                        timeout=15,
                    )
                    if r.status_code == 200:
                        return r.json().get("files", [])
                except Exception:
                    pass
                return []

            print(f"[member-commits] Fetching file details for {len(commits)} commits...", file=sys.stderr, flush=True)
            with ThreadPoolExecutor(max_workers=10) as executor:
                future_map = {
                    executor.submit(_fetch_files, c["sha"]): idx
                    for idx, c in enumerate(commits)
                }
                for future in as_completed(future_map):
                    idx = future_map[future]
                    files = future.result()
                    code_add = code_del = test_add = test_del = 0
                    for f in files:
                        fname = f.get("filename", "")
                        if self._is_generated_or_non_source(fname):
                            continue
                        adds = f.get("additions", 0)
                        dels = f.get("deletions", 0)
                        if self._is_test_file(fname):
                            test_add += adds
                            test_del += dels
                        else:
                            code_add += adds
                            code_del += dels
                    commits[idx]["code_additions"] = code_add
                    commits[idx]["code_deletions"] = code_del
                    commits[idx]["test_additions"] = test_add
                    commits[idx]["test_deletions"] = test_del
            print(f"[member-commits] File details complete.", file=sys.stderr, flush=True)

        return commits
