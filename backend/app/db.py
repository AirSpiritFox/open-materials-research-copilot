import os
import uuid
from datetime import datetime, timezone
from sqlalchemy import JSON, Column, ForeignKey, String, Text, create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool
Base = declarative_base()
def now():
    return datetime.now(timezone.utc).isoformat()
class Project(Base):
    __tablename__ = "projects"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(200), nullable=False)
    question = Column(Text, nullable=False, default="")
    notes = Column(Text, nullable=False, default="")
    created_at = Column(String(64), nullable=False, default=now)
class PaperRecord(Base):
    __tablename__ = "papers"
    id = Column(String(80), primary_key=True)
    canonical_id = Column(String(500), nullable=False, index=True)
    doi = Column(String(300), index=True)
    payload = Column(JSON, nullable=False)
    created_at = Column(String(64), nullable=False, default=now)
class ProjectPaper(Base):
    __tablename__ = "project_papers"
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    paper_id = Column(String(80), ForeignKey("papers.id"), primary_key=True)
    linked_at = Column(String(64), nullable=False, default=now)
class SearchRecord(Base):
    __tablename__ = "saved_searches"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    question = Column(Text, nullable=False)
    queries = Column(JSON, nullable=False)
    created_at = Column(String(64), nullable=False, default=now)
class Setting(Base):
    __tablename__ = "settings"
    key = Column(String(100), primary_key=True)
    encrypted_value = Column(Text, nullable=False)
def make_engine(url=None):
    url = url or os.getenv("DATABASE_URL", "sqlite:///./copilot.db")
    kwargs = {}
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in url or url == "sqlite://":
            kwargs["poolclass"] = StaticPool
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return engine
def make_session(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)
