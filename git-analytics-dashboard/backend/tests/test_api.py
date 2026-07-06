"""
Tests - Project API
"""
import pytest
from unittest.mock import patch, MagicMock
from httpx import AsyncClient, ASGITransport

from main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_health_check():
    """Test that the API is running."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/docs")
        assert response.status_code == 200


@pytest.mark.anyio
async def test_create_project_invalid_url():
    """Test creating a project with invalid URL returns 422."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post(
            "/api/projects",
            json={"git_url": "not-a-valid-url"},
        )
        assert response.status_code in (422, 400)


@pytest.mark.anyio
async def test_list_projects():
    """Test listing projects endpoint."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/projects")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
