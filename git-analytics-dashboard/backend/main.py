"""
Git Analytics Dashboard - FastAPI Application Entry Point
"""
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.database.session import engine
from app.models import Base
from app.api import router as api_router


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown events."""
    logger.info("🚀 Starting Git Analytics Dashboard API...")
    # Create tables if they don't exist (dev only; use Alembic in prod)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    from app.database.session import async_session_factory
    from app.models import User
    from app.core.security import get_password_hash
    from sqlalchemy import select
    
    async with async_session_factory() as db:
        result = await db.execute(select(User).where(User.username == "admin"))
        if not result.scalar_one_or_none():
            admin_user = User(username="admin", hashed_password=get_password_hash("admin123"))
            db.add(admin_user)
            await db.commit()
            
    logger.info("✅ Database tables ready & admin user seeded")
    yield
    logger.info("🛑 Shutting down Git Analytics Dashboard API...")
    await engine.dispose()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.APP_NAME,
        description="Git Repository Analytics Dashboard API",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    from app.api.reports import router as reports_router
    from app.api.auth import router as auth_router
    
    app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
    app.include_router(api_router, prefix="/api")
    app.include_router(reports_router, prefix="/api/reports", tags=["reports"])
    return app


app = create_app()
