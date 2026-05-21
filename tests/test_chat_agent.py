"""
Tests for Chat Agent
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from src.chat_agent import ChatAgent, ChatSession, ChatMessage


class TestChatMessage:
    """Tests for ChatMessage"""
    
    def test_to_dict(self):
        """Test message serialization"""
        message = ChatMessage(
            id="test-id",
            role="user",
            content="Hello",
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            output_type="text"
        )
        
        data = message.to_dict()
        
        assert data['id'] == "test-id"
        assert data['role'] == "user"
        assert data['content'] == "Hello"
        assert data['output_type'] == "text"


class TestChatSession:
    """Tests for ChatSession"""
    
    def test_add_message(self):
        """Test adding messages to session"""
        session = ChatSession(session_id="test-session")
        
        message = session.add_message("user", "Hello")
        
        assert len(session.messages) == 1
        assert session.messages[0].content == "Hello"
        assert session.messages[0].role == "user"
    
    def test_get_conversation_history(self):
        """Test getting conversation history"""
        session = ChatSession(session_id="test-session")
        session.add_message("user", "Message 1")
        session.add_message("assistant", "Response 1")
        session.add_message("user", "Message 2")
        
        history = session.get_conversation_history(limit=2)
        
        assert len(history) == 2
        assert history[0]['content'] == "Response 1"
        assert history[1]['content'] == "Message 2"


class TestChatAgent:
    """Tests for ChatAgent"""
    
    @pytest.fixture
    def config(self):
        return {
            'jira': {
                'url': 'https://test.atlassian.net',
                'email': 'test@test.com',
                'token': 'test-token',
                'project_key': 'TEST',
                'board_id': 1
            },
            'ai': {
                'provider': 'openai',
                'model': 'gpt-4',
                'api_key': 'test-key'
            }
        }
    
    @pytest.fixture
    def agent(self, config):
        with patch('src.chat_agent.JiraClient'), \
             patch('src.chat_agent.AIAnalyzer'):
            return ChatAgent(config)
    
    def test_get_or_create_session_new(self, agent):
        """Test creating new session"""
        session = agent.get_or_create_session()
        
        assert session is not None
        assert session.session_id in agent.sessions
    
    def test_get_or_create_session_existing(self, agent):
        """Test getting existing session"""
        session1 = agent.get_or_create_session("test-session")
        session2 = agent.get_or_create_session("test-session")
        
        assert session1 is session2
    
    def test_chat_empty_message(self, agent):
        """Test chat with empty message"""
        result = agent.chat("")
        
        assert result['response']['content'] == 'Vui lòng nhập câu hỏi của bạn.'
    
    def test_clear_session(self, agent):
        """Test clearing session"""
        agent.get_or_create_session("test-session")
        
        result = agent.clear_session("test-session")
        
        assert result is True
        assert "test-session" not in agent.sessions
    
    def test_clear_nonexistent_session(self, agent):
        """Test clearing non-existent session"""
        result = agent.clear_session("nonexistent")
        
        assert result is False
    
    def test_get_suggestions(self, agent):
        """Test getting suggestions"""
        suggestions = agent.get_suggestions()
        
        assert isinstance(suggestions, list)
        assert len(suggestions) > 0
