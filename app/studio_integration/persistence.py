"""Isolated Agent Studio SQLite storage under this installation's existing data/."""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone

MAX_AGENT = 128_000
MAX_RESULT = 48_000


class StudioStorage:
    def __init__(self, data_dir: Path):
        self.directory = Path(data_dir).resolve() / 'agent-studio'
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / 'studio.sqlite3'
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS workflows (
                    owner TEXT NOT NULL, id TEXT NOT NULL,
                    payload TEXT NOT NULL, updated_at TEXT NOT NULL,
                    PRIMARY KEY(owner,id)
                );
                CREATE TABLE IF NOT EXISTS results (
                    owner TEXT NOT NULL, id TEXT NOT NULL,
                    payload TEXT NOT NULL, created_at TEXT NOT NULL,
                    PRIMARY KEY(owner,id)
                );
            ''')
        if __import__('os').name != 'nt':
            self.directory.chmod(0o700)
            self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(str(self.path), timeout=10)
        db.execute('PRAGMA busy_timeout=10000')
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def save_workflow(self, owner: str, workflow: dict):
        if not isinstance(workflow,dict) or workflow.get('format') != 'agent-studio/workflow' or workflow.get('version') != 1:
            raise ValueError('Export and save an Agent Studio v1 workflow.')
        if not isinstance(workflow.get('steps'),list) or not 3 <= len(workflow['steps']) <= 30:
            raise ValueError('Workflow must have 3–30 steps.')
        payload = json.dumps(workflow, ensure_ascii=False)
        if len(payload.encode('utf-8')) > MAX_AGENT:
            raise ValueError('Workflow exceeds 128 KB.')
        stamp = datetime.now(timezone.utc).isoformat()
        with self.connect() as db:
            db.execute('INSERT INTO workflows(owner,id,payload,updated_at) VALUES (?,?,?,?) '
                       'ON CONFLICT(owner,id) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at',
                       (owner, 'latest', payload, stamp))
            db.commit()
        return stamp

    def load_workflow(self, owner: str):
        with self.connect() as db:
            row=db.execute('SELECT payload,updated_at FROM workflows WHERE owner=? AND id=?',(owner,'latest')).fetchone()
        return {'workflow':json.loads(row[0]),'updated_at':row[1]} if row else {'workflow':None}

    def save_result(self, owner: str, result: dict):
        if not isinstance(result,dict) or not isinstance(result.get('id'),str) or not 1 <= len(result['id']) <= 100:
            raise ValueError('Result must include a valid id.')
        if not isinstance(result.get('output'),str) or len(result['output'])>30000:
            raise ValueError('Result must contain at most 30,000 characters.')
        payload=json.dumps(result,ensure_ascii=False)
        if len(payload.encode('utf-8'))>MAX_RESULT:
            raise ValueError('Result exceeds 48 KB.')
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO results(owner,id,payload,created_at) VALUES(?,?,?,?)',
                       (owner,result['id'],payload,datetime.now(timezone.utc).isoformat()))
            db.execute('DELETE FROM results WHERE owner=? AND id NOT IN '
                       '(SELECT id FROM results WHERE owner=? ORDER BY created_at DESC LIMIT 100)',(owner,owner))
            db.commit()

    def results(self,owner):
        with self.connect() as db:
            rows=db.execute('SELECT payload FROM results WHERE owner=? ORDER BY created_at DESC LIMIT 100',(owner,)).fetchall()
        return [json.loads(r[0]) for r in rows]
