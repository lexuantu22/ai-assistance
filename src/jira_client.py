"""
JIRA Client - Handles all JIRA API interactions
"""
import os
from datetime import datetime, date
from dataclasses import dataclass, field
from typing import Optional, Literal, List, Dict, Any
import requests
from requests.auth import HTTPBasicAuth


@dataclass
class JiraIssue:
    """Represents a JIRA issue"""
    key: str
    summary: str
    issue_type: str
    status: str
    priority: str
    assignee: Optional[str]
    reporter: str
    sprint: Optional[str]
    epic: Optional[str]
    created_date: datetime
    due_date: Optional[datetime]
    resolved_date: Optional[datetime]
    labels: List[str] = field(default_factory=list)
    components: List[str] = field(default_factory=list)
    defect_type: Optional[str] = None
    
    @property
    def is_overdue(self) -> bool:
        """True if due_date < today and status != Done"""
        if not self.due_date:
            return False
        if self.status.lower() in ['done', 'closed', 'resolved']:
            return False
        return self.due_date.date() < date.today()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'key': self.key,
            'summary': self.summary,
            'issue_type': self.issue_type,
            'status': self.status,
            'priority': self.priority,
            'assignee': self.assignee,
            'reporter': self.reporter,
            'sprint': self.sprint,
            'epic': self.epic,
            'created_date': self.created_date.isoformat() if self.created_date else None,
            'due_date': self.due_date.isoformat() if self.due_date else None,
            'resolved_date': self.resolved_date.isoformat() if self.resolved_date else None,
            'labels': self.labels,
            'components': self.components,
            'defect_type': self.defect_type,
            'is_overdue': self.is_overdue
        }


class JiraClient:
    """Handles all JIRA API interactions"""
    
    def __init__(self, config: dict):
        """
        Initialize JIRA client
        
        Config needs:
        - jira_url: str (e.g., "https://company.atlassian.net")
        - jira_email: str
        - jira_token: str
        - project_key: str (e.g., "PROJ")
        """
        jira_config = config.get('jira', {})
        self.base_url = os.getenv('JIRA_URL', jira_config.get('url', ''))
        self.username = os.getenv('JIRA_USERNAME', jira_config.get('username', ''))
        self.password = os.getenv('JIRA_PASSWORD', jira_config.get('password', ''))
        self.project_key = jira_config.get('project_key', '')
        self.board_id = jira_config.get('board_id')
        
        self.auth = HTTPBasicAuth(self.username, self.password)
        self.headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
    
    def update_credentials(self, url: str, username: str, password: str):
        """Update JIRA connection credentials at runtime"""
        self.base_url = url
        self.username = username
        self.password = password
        self.auth = HTTPBasicAuth(self.username, self.password)
    
    def set_project_key(self, project_key: str):
        """Update the active project key"""
        self.project_key = project_key
    
    def get_projects(self) -> List[Dict[str, str]]:
        """Get list of projects accessible by the current user"""
        try:
            result = self._make_request('GET', 'project', params={'recent': 50})
            projects = []
            for p in result:
                projects.append({
                    'key': p.get('key', ''),
                    'name': p.get('name', ''),
                })
            projects.sort(key=lambda x: x['key'])
            return projects
        except Exception:
            return []
    
    def _make_request(self, method: str, endpoint: str, params: dict = None, json_data: dict = None) -> dict:
        """Make an API request to JIRA"""
        url = f"{self.base_url}/rest/api/2/{endpoint}"
        
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=self.headers,
                auth=self.auth,
                params=params,
                json=json_data,
                timeout=30
            )
            response.raise_for_status()
            return response.json() if response.text else {}
        except requests.exceptions.RequestException as e:
            raise JiraConnectionError(f"Failed to connect to JIRA: {str(e)}")
    
    def _make_agile_request(self, method: str, endpoint: str, params: dict = None) -> dict:
        """Make an API request to JIRA Agile API"""
        url = f"{self.base_url}/rest/agile/1.0/{endpoint}"
        
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=self.headers,
                auth=self.auth,
                params=params,
                timeout=30
            )
            response.raise_for_status()
            return response.json() if response.text else {}
        except requests.exceptions.RequestException as e:
            raise JiraConnectionError(f"Failed to connect to JIRA Agile API: {str(e)}")
    
    def _parse_issue(self, issue_data: dict) -> JiraIssue:
        """Parse JIRA API response into JiraIssue object"""
        fields = issue_data.get('fields', {})
        
        # Parse dates
        created_date = None
        if fields.get('created'):
            created_date = datetime.fromisoformat(fields['created'].replace('Z', '+00:00'))
        
        due_date = None
        if fields.get('duedate'):
            due_date = datetime.strptime(fields['duedate'], '%Y-%m-%d')
        
        resolved_date = None
        if fields.get('resolutiondate'):
            resolved_date = datetime.fromisoformat(fields['resolutiondate'].replace('Z', '+00:00'))
        
        # Parse sprint from customfield_10100
        sprint = None
        sprint_field = fields.get('customfield_10100') or fields.get('sprint')
        if sprint_field:
            if isinstance(sprint_field, list) and len(sprint_field) > 0:
                sprint_info = sprint_field[-1]  # Get the latest sprint
                if isinstance(sprint_info, dict):
                    sprint = sprint_info.get('name')
                elif isinstance(sprint_info, str):
                    # Parse sprint name from string format
                    import re
                    match = re.search(r'name=([^,\]]+)', sprint_info)
                    if match:
                        sprint = match.group(1)
        
        # Parse epic
        epic = fields.get('parent', {}).get('key') if fields.get('parent') else None
        if not epic:
            epic = fields.get('customfield_10014')  # Epic link field
        
        # Parse components
        components = []
        if fields.get('components'):
            components = [c.get('name', '') for c in fields['components'] if isinstance(c, dict)]
        
        # Parse defect type (customfield - may vary by JIRA instance)
        defect_type = None
        # Try common defect type custom fields (excluding customfield_10100 which is sprint)
        for cf in ['customfield_10200', 'customfield_10300', 'customfield_11700']:
            if fields.get(cf):
                dt_field = fields[cf]
                if isinstance(dt_field, dict):
                    defect_type = dt_field.get('value') or dt_field.get('name')
                elif isinstance(dt_field, str):
                    defect_type = dt_field
                if defect_type:
                    break
        
        return JiraIssue(
            key=issue_data.get('key', ''),
            summary=fields.get('summary', ''),
            issue_type=fields.get('issuetype', {}).get('name', ''),
            status=fields.get('status', {}).get('name', ''),
            priority=fields.get('priority', {}).get('name', 'Medium') if fields.get('priority') else 'Medium',
            assignee=fields.get('assignee', {}).get('displayName') if fields.get('assignee') else None,
            reporter=fields.get('reporter', {}).get('displayName', '') if fields.get('reporter') else '',
            sprint=sprint,
            epic=epic,
            created_date=created_date,
            due_date=due_date,
            resolved_date=resolved_date,
            labels=fields.get('labels', []),
            components=components,
            defect_type=defect_type
        )
    
    def search_issues(self, jql: str, fields: List[str] = None, max_results: int = 100) -> List[JiraIssue]:
        """
        Execute JQL search and return list of JiraIssue
        
        Example JQL: 'project = PROJ AND type = Bug AND status = Open'
        """
        if fields is None:
            fields = [
                'summary', 'issuetype', 'status', 'priority', 'assignee',
                'reporter', 'created', 'duedate', 'resolutiondate', 'labels',
                'parent', 'customfield_10100', 'customfield_10014',  # sprint (customfield_10100), epic link
                'components',  # components
                'customfield_10200', 'customfield_10300', 'customfield_11700'  # defect type candidates
            ]
        
        all_issues = []
        start_at = 0
        
        while True:
            params = {
                'jql': jql,
                'fields': ','.join(fields),
                'maxResults': min(100, max_results - len(all_issues)),
                'startAt': start_at
            }
            
            response = self._make_request('GET', 'search', params=params)
            issues = response.get('issues', [])
            
            for issue_data in issues:
                all_issues.append(self._parse_issue(issue_data))
            
            # Check if we have more results
            total = response.get('total', 0)
            if len(all_issues) >= total or len(all_issues) >= max_results:
                break
            
            start_at += len(issues)
        
        return all_issues
    
    def get_sprints(self, board_id: int = None, state: str = "active") -> List[dict]:
        """Get list of sprints for a board"""
        board_id = board_id or self.board_id
        if not board_id:
            return []
        
        params = {'state': state}
        response = self._make_agile_request('GET', f'board/{board_id}/sprint', params=params)
        return response.get('values', [])
    
    def get_current_sprint(self, board_id: int = None) -> Optional[dict]:
        """Get the current active sprint"""
        sprints = self.get_sprints(board_id, state='active')
        return sprints[0] if sprints else None
    
    def get_issue(self, issue_key: str) -> JiraIssue:
        """Get details of a single issue"""
        response = self._make_request('GET', f'issue/{issue_key}')
        return self._parse_issue(response)
    
    def get_project_statuses(self) -> List[str]:
        """Get all statuses for the project"""
        response = self._make_request('GET', f'project/{self.project_key}/statuses')
        statuses = set()
        for issue_type in response:
            for status in issue_type.get('statuses', []):
                statuses.add(status.get('name'))
        return list(statuses)
    
    def get_project_id(self) -> Optional[int]:
        """Get numeric project ID from project key"""
        try:
            result = self._make_request('GET', f'project/{self.project_key}')
            return int(result.get('id', 0)) or None
        except Exception:
            return None

    def test_connection(self) -> bool:
        """Test if JIRA connection is working"""
        try:
            self._make_request('GET', 'myself')
            return True
        except:
            return False


class JiraConnectionError(Exception):
    """Raised when JIRA connection fails"""
    pass
