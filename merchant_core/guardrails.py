import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
import config

class GuardrailResult(BaseModel):
    allowed: bool
    reason: str
    action: str
    details: Dict[str, Any]

class Mandate(BaseModel):
    mandate_id: str
    session_id: str
    items: List[Dict[str, Any]]
    total_paise: int
    currency: str
    created_at: datetime
    status: str
    reason: str

_mandates: Dict[str, Mandate] = {}

def check_spend_limit(session_id: str, proposed_total_paise: int) -> GuardrailResult:
    """Checks if the proposed total exceeds the maximum session spend."""
    if proposed_total_paise > config.MAX_SESSION_SPEND:
        return GuardrailResult(
            allowed=False,
            reason=f"Exceeds max session spend of {config.MAX_SESSION_SPEND} paise.",
            action="block",
            details={"proposed": proposed_total_paise, "limit": config.MAX_SESSION_SPEND}
        )
    return GuardrailResult(
        allowed=True,
        reason="Within spend limits.",
        action="allow",
        details={}
    )

def gate_action(session_id: str, action: str, details: Dict[str, Any]) -> GuardrailResult:
    """Gates specific actions based on predefined rules."""
    if action == 'checkout':
        return GuardrailResult(
            allowed=False,
            reason="Checkout always requires confirmation.",
            action="requires_confirmation",
            details=details
        )
    elif action == 'add_item':
        qty = details.get('quantity', 1)
        if qty > config.MAX_ITEMS_PER_ADD:
            return GuardrailResult(
                allowed=False,
                reason=f"Cannot add more than {config.MAX_ITEMS_PER_ADD} items at once.",
                action="requires_confirmation",
                details=details
            )
    elif action == 'apply_discount':
        return GuardrailResult(
            allowed=False,
            reason="Applying discounts requires confirmation.",
            action="requires_confirmation",
            details=details
        )
    return GuardrailResult(allowed=True, reason="Action permitted.", action="allow", details=details)

def create_mandate(session_id: str, cart_items: List[Dict[str, Any]], total_paise: int, reason: str) -> Mandate:
    """Generates a mandate object with pending status."""
    mandate_id = str(uuid.uuid4())
    mandate = Mandate(
        mandate_id=mandate_id,
        session_id=session_id,
        items=cart_items,
        total_paise=total_paise,
        currency=config.CURRENCY,
        created_at=datetime.utcnow(),
        status="pending_confirmation",
        reason=reason
    )
    _mandates[mandate_id] = mandate
    return mandate

def confirm_mandate(mandate_id: str) -> Optional[Mandate]:
    """Updates mandate status to confirmed."""
    mandate = _mandates.get(mandate_id)
    if mandate:
        mandate.status = "confirmed"
        return mandate
    return None

def get_mandate(mandate_id: str) -> Optional[Mandate]:
    """Retrieves a mandate by ID."""
    return _mandates.get(mandate_id)
