"""HTTP layer: one POST endpoint per ElevenLabs server tool.

Run:  uvicorn app.main:app --port 8000   (from the api/ folder)
Auth: Authorization: Bearer $ENTIN_TOOL_SECRET  (a second key, $ENTIN_TOOL_SECRET_NEXT, allows rotation)
"""
import hmac
import os

from fastapi import Depends, FastAPI, Header, HTTPException, Request

from . import db
from .service import Tools

TOOL_NAMES = ["assess_request", "verify_caller", "find_transactions", "get_transaction_status", "get_card_status",
              "block_card", "get_digital_access_status", "create_ticket", "create_dispute", "get_ticket_status",
              "report_security_event", "request_human_handoff", "find_branch_or_atm"]

app = FastAPI(title="ENTIN Support API (synthetic demo)", version="0.1.0",
              description="Fictional bank. Synthetic data only. Never accepts PIN, OTP, password, CVV or card numbers.")

_path = os.environ.get("ENTIN_DB", "entin.db")
if not os.path.exists(_path):
    db.fresh(_path).close()
tools = Tools(db.connect(_path))


def auth(authorization: str = Header(default="")) -> None:
    keys = [k for k in (os.environ.get("ENTIN_TOOL_SECRET"), os.environ.get("ENTIN_TOOL_SECRET_NEXT")) if k]
    if not keys:
        raise HTTPException(500, "ENTIN_TOOL_SECRET not configured")
    supplied = authorization.removeprefix("Bearer ").strip()
    if not any(hmac.compare_digest(supplied, k) for k in keys):
        raise HTTPException(401, "unauthorized")


@app.get("/health")
def health() -> dict:
    return {"ok": True, "synthetic": True}


@app.get("/v1/events")
def pending_events(_: None = Depends(auth), mark_delivered: bool = True) -> dict:
    """Polled by n8n. Returns undelivered events (handoffs, card blocks, security cases, SLA breaches)."""
    rows = [dict(r) for r in tools.db.execute("SELECT * FROM events_outbox WHERE delivered=0 ORDER BY id LIMIT 100")]
    if mark_delivered and rows:
        tools.db.execute(f"UPDATE events_outbox SET delivered=1 WHERE id IN ({','.join(str(r['id']) for r in rows)})")
        tools.db.commit()
    return {"events": rows}


@app.get("/v1/reports/daily")
def daily_report(_: None = Depends(auth)) -> dict:
    """Last-24h counts for the n8n QA digest."""
    return tools.daily_report()


@app.post("/v1/sessions/{conversation_id}/outcome")
def post_call_outcome(conversation_id: str, body: dict, _: None = Depends(auth)) -> dict:
    """Called by n8n after ElevenLabs post-call webhook (already HMAC-verified and redacted by n8n)."""
    tools._session(conversation_id)
    tools.db.execute("UPDATE call_sessions SET secret_detected = MAX(secret_detected, ?) WHERE conversation_id=?",
                     (int(bool(body.get("secret_detected"))), conversation_id))
    tools._audit(conversation_id, "post_call_outcome", None, "ok", {k: v for k, v in body.items() if k != "transcript"})
    return {"ok": True}


def _make(name: str):
    async def endpoint(request: Request, _: None = Depends(auth)) -> dict:
        body = await request.json()
        return tools.call(name, body if isinstance(body, dict) else {})
    endpoint.__name__ = name
    return endpoint


for _name in TOOL_NAMES:
    app.post(f"/v1/tools/{_name}", name=_name)(_make(_name))
