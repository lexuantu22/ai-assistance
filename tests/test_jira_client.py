"""
Tests for JIRA Client
"""
import pytest
from unittest.mock import Mock, patch
from datetime import datetime

from src.jira_client import JiraClient, JiraIssue, JiraConnectionError


class TestJiraIssue:
    """Tests for JiraIssue dataclass"""
    
    def test_is_overdue_no_due_date(self):
        """Issue without due date is not overdue"""
        issue = JiraIssue(
            key="TEST-1",
            summary="Test issue",
            issue_type="Bug",
            status="Open",
            priority="High",
            assignee="John",
            reporter="Jane",
            sprint=None,
            epic=None,
            created_date=datetime.now(),
            due_date=None,
            resolved_date=None,
            labels=[]
        )
        assert issue.is_overdue is False
    
    def test_is_overdue_done_status(self):
        """Done issues are not overdue"""
        issue = JiraIssue(
            key="TEST-1",
            summary="Test issue",
            issue_type="Bug",
            status="Done",
            priority="High",
            assignee="John",
            reporter="Jane",
            sprint=None,
            epic=None,
            created_date=datetime.now(),
            due_date=datetime(2020, 1, 1),  # Past date
            resolved_date=datetime.now(),
            labels=[]
        )
        assert issue.is_overdue is False
    
    def test_to_dict(self):
        """Test issue serialization"""
        issue = JiraIssue(
            key="TEST-1",
            summary="Test issue",
            issue_type="Bug",
            status="Open",
            priority="High",
            assignee="John",
            reporter="Jane",
            sprint="Sprint 1",
            epic="EPIC-1",
            created_date=datetime(2024, 1, 1),
            due_date=datetime(2024, 2, 1),
            resolved_date=None,
            labels=["urgent"]
        )
        
        data = issue.to_dict()
        
        assert data['key'] == "TEST-1"
        assert data['summary'] == "Test issue"
        assert data['issue_type'] == "Bug"
        assert data['sprint'] == "Sprint 1"
        assert data['labels'] == ["urgent"]


class TestJiraClient:
    """Tests for JiraClient"""
    
    @pytest.fixture
    def config(self):
        return {
            'jira': {
                'url': 'https://test.atlassian.net',
                'email': 'test@test.com',
                'token': 'test-token',
                'project_key': 'TEST',
                'board_id': 1
            }
        }
    
    @pytest.fixture
    def client(self, config):
        return JiraClient(config)
    
    def test_init(self, client, config):
        """Test client initialization"""
        assert client.project_key == 'TEST'
        assert client.board_id == 1
    
    @patch('src.jira_client.requests.request')
    def test_search_issues(self, mock_request, client):
        """Test JQL search"""
        mock_response = Mock()
        mock_response.json.return_value = {
            'issues': [
                {
                    'key': 'TEST-1',
                    'fields': {
                        'summary': 'Test bug',
                        'issuetype': {'name': 'Bug'},
                        'status': {'name': 'Open'},
                        'priority': {'name': 'High'},
                        'assignee': {'displayName': 'John'},
                        'reporter': {'displayName': 'Jane'},
                        'created': '2024-01-01T00:00:00.000+0000',
                        'duedate': '2024-02-01',
                        'labels': []
                    }
                }
            ],
            'total': 1
        }
        mock_response.raise_for_status = Mock()
        mock_response.text = 'response'
        mock_request.return_value = mock_response
        
        issues = client.search_issues('project = TEST')
        
        assert len(issues) == 1
        assert issues[0].key == 'TEST-1'
        assert issues[0].issue_type == 'Bug'
    
    @patch('src.jira_client.requests.request')
    def test_test_connection_success(self, mock_request, client):
        """Test successful connection"""
        mock_response = Mock()
        mock_response.json.return_value = {'accountId': 'test'}
        mock_response.raise_for_status = Mock()
        mock_response.text = 'response'
        mock_request.return_value = mock_response
        
        assert client.test_connection() is True
    
    @patch('src.jira_client.requests.request')
    def test_test_connection_failure(self, mock_request, client):
        """Test failed connection"""
        mock_request.side_effect = Exception("Connection failed")
        
        assert client.test_connection() is False
