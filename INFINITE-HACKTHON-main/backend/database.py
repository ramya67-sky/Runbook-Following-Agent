from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, scoped_session
from datetime import datetime
import os

Base = declarative_base()

class RunbookRun(Base):
    __tablename__ = 'runbook_runs'

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    status = Column(String(50), default='PENDING') # PENDING, RUNNING, COMPLETED, FAILED, PARTIAL
    started_at = Column(DateTime, default=None, nullable=True)
    completed_at = Column(DateTime, default=None, nullable=True)
    total_steps = Column(Integer, default=0)
    executed_steps = Column(Integer, default=0)
    skipped_steps = Column(Integer, default=0)
    errors_count = Column(Integer, default=0)
    audit_summary = Column(Text, default=None, nullable=True)

    # Relationship to the individual steps of the run
    steps = relationship('RunbookStep', back_populates='run', cascade="all, delete-orphan", order_by="RunbookStep.step_number")

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'status': self.status,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'total_steps': self.total_steps,
            'executed_steps': self.executed_steps,
            'skipped_steps': self.skipped_steps,
            'errors_count': self.errors_count,
            'audit_summary': self.audit_summary
        }

class RunbookStep(Base):
    __tablename__ = 'runbook_steps'

    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey('runbook_runs.id', ondelete="CASCADE"), nullable=False)
    step_number = Column(Integer, nullable=False)
    description = Column(Text, nullable=True)
    command = Column(Text, nullable=True)
    has_command = Column(Boolean, default=False)
    step_type = Column(String(20), default='SHELL')  # SHELL, REST_API, DB_QUERY, CLOUD_CLI
    risk_level = Column(String(20), default='SAFE')  # SAFE, MEDIUM, HIGH
    explanation = Column(Text, nullable=True)
    recommendation = Column(Text, nullable=True)
    status = Column(String(50), default='PENDING')  # PENDING, RUNNING, SUCCESS, FAILED, SKIPPED, WAITING_APPROVAL, DENIED
    output = Column(Text, default="", nullable=True)
    corrected_command = Column(Text, default=None, nullable=True)
    executed_at = Column(DateTime, default=None, nullable=True)

    # Back-relationship
    run = relationship('RunbookRun', back_populates='steps')

    def to_dict(self):
        return {
            'id': self.id,
            'run_id': self.run_id,
            'step_number': self.step_number,
            'description': self.description,
            'command': self.command,
            'has_command': self.has_command,
            'step_type': self.step_type or 'SHELL',
            'risk_level': self.risk_level,
            'explanation': self.explanation,
            'recommendation': self.recommendation,
            'status': self.status,
            'output': self.output,
            'corrected_command': self.corrected_command,
            'executed_at': self.executed_at.isoformat() if self.executed_at else None
        }

# Database helper initialization
DEFAULT_SQLITE_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), "antigravity.db")
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DEFAULT_SQLITE_PATH}")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Session = scoped_session(session_factory)

def init_db():
    Base.metadata.create_all(bind=engine)
    # Check if corrected_command column exists, if not add it
    db = Session()
    try:
        from sqlalchemy import text
        res = db.execute(text("PRAGMA table_info(runbook_steps);")).fetchall()
        cols = [r[1] for r in res]
        if "corrected_command" not in cols:
            db.execute(text("ALTER TABLE runbook_steps ADD COLUMN corrected_command TEXT;"))
            db.commit()
    except Exception as e:
        print(f"Error migrating database: {e}")
    finally:
        db.close()

def get_db():
    return Session()
