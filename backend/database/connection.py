"""
Database connection and session management.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import NullPool
from contextlib import contextmanager
import os
from typing import Generator

from .models import Base


class Database:
    """Database connection manager (Singleton pattern for DRY)."""
    
    _instance = None
    _engine = None
    _session_factory = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Database, cls).__new__(cls)
        return cls._instance

    def initialize(self, database_url: str, echo: bool = False):
        """Initialize database connection."""
        if self._engine is None:
            self._engine = create_engine(
                database_url,
                echo=echo,
                pool_pre_ping=True,  # Verify connections before using
                pool_size=10,
                max_overflow=20
            )
            self._session_factory = scoped_session(
                sessionmaker(
                    bind=self._engine,
                    autocommit=False,
                    autoflush=False
                )
            )

    def create_all(self):
        """Create all tables."""
        if self._engine is None:
            raise RuntimeError("Database not initialized")
        Base.metadata.create_all(self._engine)

    def drop_all(self):
        """Drop all tables (use with caution!)."""
        if self._engine is None:
            raise RuntimeError("Database not initialized")
        Base.metadata.drop_all(self._engine)

    @contextmanager
    def get_session(self) -> Generator:
        """Get database session with automatic cleanup."""
        if self._session_factory is None:
            raise RuntimeError("Database not initialized")
        
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def close(self):
        """Close database connections."""
        if self._session_factory:
            self._session_factory.remove()
        if self._engine:
            self._engine.dispose()


# Global database instance
db = Database()


def get_database_url() -> str:
    """Get database URL from environment variables."""
    host = os.getenv('DB_HOST', 'localhost')
    port = os.getenv('DB_PORT', '5432')
    user = os.getenv('DB_USER', 'merge_assist')
    password = os.getenv('DB_PASSWORD', 'password')
    database = os.getenv('DB_NAME', 'merge_assist')
    
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"
