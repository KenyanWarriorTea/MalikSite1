"""Database configuration and session management"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from models import Base

# Database URL from environment or default
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@db:5432/tasks_db")

engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,  # Verify connections before using them
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    """Dependency for getting database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database tables"""
    Base.metadata.create_all(bind=engine)
