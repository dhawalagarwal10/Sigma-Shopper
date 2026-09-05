import json
import threading
from datetime import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
import config

class AuditEntry(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    session_id: str
    action: str
    actor: str
    details: Dict[str, Any]
    reasoning: str
    guardrail_result: str = 'n/a'
    mandate_id: Optional[str] = None
    outcome: str = ''

_log_lock = threading.Lock()

def log_event(session_id: str, action: str, actor: str, details: Dict[str, Any], reasoning: str, guardrail_result: str = 'n/a', mandate_id: Optional[str] = None, outcome: str = '') -> AuditEntry:
    """Logs an event to the audit file."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    entry = AuditEntry(
        session_id=session_id,
        action=action,
        actor=actor,
        details=details,
        reasoning=reasoning,
        guardrail_result=guardrail_result,
        mandate_id=mandate_id,
        outcome=outcome
    )
    
    with _log_lock:
        with open(config.AUDIT_LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(entry.model_dump_json() + '\n')
            
    return entry

def get_session_log(session_id: str) -> List[AuditEntry]:
    """Reads file, filters by session."""
    if not config.AUDIT_LOG_PATH.exists():
        return []
        
    logs = []
    with _log_lock:
        with open(config.AUDIT_LOG_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip(): continue
                try:
                    data = json.loads(line)
                    if data.get('session_id') == session_id:
                        logs.append(AuditEntry(**data))
                except json.JSONDecodeError:
                    pass
    return logs

def get_all_logs(limit: int = 50) -> List[AuditEntry]:
    """Returns most recent N entries."""
    if not config.AUDIT_LOG_PATH.exists():
        return []
        
    logs = []
    with _log_lock:
        with open(config.AUDIT_LOG_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip(): continue
                try:
                    logs.append(AuditEntry(**json.loads(line)))
                except json.JSONDecodeError:
                    pass
    return logs[-limit:]

def clear_logs() -> None:
    """Empties the audit log file."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _log_lock:
        with open(config.AUDIT_LOG_PATH, 'w', encoding='utf-8') as f:
            pass
