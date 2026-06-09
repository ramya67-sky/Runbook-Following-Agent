import sqlite3
import json
from datetime import datetime


DB_PATH = "runbook-assistant/data/audit.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS executions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            runbook_name TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            status TEXT DEFAULT 'in_progress',
            summary TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS step_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            execution_id INTEGER NOT NULL,
            step_index INTEGER NOT NULL,
            step_title TEXT,
            step_command TEXT,
            risk_level TEXT,
            status TEXT,
            output TEXT,
            notes TEXT,
            logged_at TEXT NOT NULL,
            FOREIGN KEY (execution_id) REFERENCES executions(id)
        )
    """)
    conn.commit()
    conn.close()


def start_execution(runbook_name: str) -> int:
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO executions (runbook_name, started_at, status) VALUES (?, ?, 'in_progress')",
        (runbook_name, datetime.utcnow().isoformat())
    )
    conn.commit()
    eid = c.lastrowid
    conn.close()
    return eid


def complete_execution(execution_id: int, status: str, summary: str = ""):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "UPDATE executions SET completed_at=?, status=?, summary=? WHERE id=?",
        (datetime.utcnow().isoformat(), status, summary, execution_id)
    )
    conn.commit()
    conn.close()


def log_step(execution_id: int, step_index: int, step_title: str,
             step_command: str, risk_level: str, status: str,
             output: str = "", notes: str = ""):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO step_logs
            (execution_id, step_index, step_title, step_command, risk_level, status, output, notes, logged_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (execution_id, step_index, step_title, step_command, risk_level,
          status, output, notes, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()


def get_all_executions():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM executions ORDER BY started_at DESC")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_execution_steps(execution_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM step_logs WHERE execution_id=? ORDER BY step_index",
        (execution_id,)
    )
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows
