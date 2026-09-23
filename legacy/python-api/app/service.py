"""ENTIN support tools. Framework-free so it is unit-testable; main.py exposes it over HTTP.

Every tool takes a request dict and returns the standard envelope:
{ok, data, say, risk_level, next_actions, error}
"""
import hashlib
import json
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Callable

from . import policy
from .guard import factor_hash, redact, scan_payload

TOKEN_TTL = timedelta(minutes=15)
MAX_VERIFY_FAILURES = 2


class ToolError(Exception):
    def __init__(self, code: str, say: str, retryable: bool = False):
        super().__init__(code)
        self.code, self.say, self.retryable = code, say, retryable


def naira(kobo: int) -> str:
    n = kobo // 100
    return f"{n:,} naira"


def spoken_ref(ref: str) -> str:
    prefix, _, num = ref.partition("-")
    digits = " ".join(num)
    return f"{' '.join(prefix)}, {digits}"


def spoken_when(ts: str, now: datetime) -> str:
    dt = datetime.fromisoformat(ts)
    delta = now - dt
    if delta < timedelta(hours=1):
        return f"about {max(1, int(delta.total_seconds() // 60))} minutes ago"
    if dt.date() == now.date():
        return f"today at about {dt.strftime('%-I %p')}"
    if (now.date() - dt.date()).days == 1:
        return f"yesterday at about {dt.strftime('%-I %p')}"
    return dt.strftime("%A %-d %B")


class Tools:
    def __init__(self, conn: sqlite3.Connection, clock: Callable[[], datetime] | None = None):
        self.db = conn
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    # ---------- plumbing ----------
    def call(self, name: str, req: dict) -> dict:
        fn = getattr(self, f"t_{name}", None)
        if fn is None:
            return self._err("NOT_FOUND", "Sorry, I can't do that here.")
        conv = req.get("conversation_id") or "anonymous"
        try:
            kind = scan_payload(req)
            if kind:
                self._session(conv)
                self._security_case(conv, "sensitive_disclosure", kind)
                raise ToolError("SENSITIVE_DATA_REJECTED",
                                "For your safety, please don't share that. ENTIN Bank will never ask for your PIN, OTP, password or card number.")
            self._validate_shapes(req)
            out = fn(req)
            self._audit(conv, name, (out.get("data") or {}).get("id"), "ok" if out["ok"] else out["error"]["code"], req)
            return out
        except ToolError as e:
            self._audit(conv, name, None, e.code, req)
            return self._err(e.code, e.say, e.retryable, conv)

    def _validate_shapes(self, req: dict) -> None:
        shapes = {"account_last4": r"\d{4}", "phone_last4": r"\d{4}", "card_last4": r"\d{4}",
                  "date_of_birth": r"\d{4}-\d{2}-\d{2}"}
        for field, pattern in shapes.items():
            if req.get(field) not in (None, "") and not re.fullmatch(pattern, str(req[field])):
                raise ToolError("VALIDATION_ERROR", "Sorry, I didn't get that in the right format. Could you say it again?")

    def _now(self) -> str:
        return self.clock().replace(microsecond=0).isoformat()

    def _ok(self, data: dict, say: str = "", conv: str | None = None, next_actions: list | None = None) -> dict:
        return {"ok": True, "data": data, "say": say, "risk_level": self._risk(conv),
                "next_actions": next_actions or [], "error": None}

    def _err(self, code: str, say: str, retryable: bool = False, conv: str | None = None) -> dict:
        return {"ok": False, "data": None, "say": say, "risk_level": self._risk(conv),
                "next_actions": ["offer_human"] if code != "VALIDATION_ERROR" else [],
                "error": {"code": code, "retryable": retryable, "say": say}}

    def _session(self, conv: str) -> sqlite3.Row:
        row = self.db.execute("SELECT * FROM call_sessions WHERE conversation_id=?", (conv,)).fetchone()
        if not row:
            self.db.execute("INSERT INTO call_sessions (conversation_id, verification_tier, started_at) VALUES (?,?,?)",
                            (conv, "T0", self._now()))
            self.db.commit()
            row = self.db.execute("SELECT * FROM call_sessions WHERE conversation_id=?", (conv,)).fetchone()
        return row

    def _risk(self, conv: str | None) -> str:
        if not conv:
            return "LOW"
        row = self.db.execute("SELECT max_risk FROM call_sessions WHERE conversation_id=?", (conv,)).fetchone()
        return row["max_risk"] if row else "LOW"

    def _raise_risk(self, conv: str, level: str, intent: str | None = None) -> str:
        s = self._session(conv)
        new = policy.max_level(s["max_risk"], level)
        intents = s["intents"]
        if intent and intent not in intents.split(","):
            intents = ",".join(filter(None, [intents, intent]))
        self.db.execute("UPDATE call_sessions SET max_risk=?, intents=? WHERE conversation_id=?", (new, intents, conv))
        self.db.commit()
        return new

    def _audit(self, conv, action, object_id, result, req) -> None:
        safe = {k: ("***" if k in ("verification_token", "full_name", "date_of_birth", "account_last4", "phone_last4", "caller_id") else
                    redact(v) if isinstance(v, str) else v) for k, v in req.items()}
        self.db.execute("INSERT INTO audit_log (ts, actor, conversation_id, action, object_id, result, meta) VALUES (?,?,?,?,?,?,?)",
                        (self._now(), "agent", conv, action, object_id, result, json.dumps(safe)))
        self.db.commit()

    def _event(self, type_: str, payload: dict) -> None:
        self.db.execute("INSERT INTO events_outbox (type, payload, created_at) VALUES (?,?,?)",
                        (type_, json.dumps(payload), self._now()))

    def _next_id(self, table: str, col: str, prefix: str, start: int) -> str:
        n = self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        return f"{prefix}-{start + n + 1:06d}"

    def _security_case(self, conv: str, type_: str, secret_kind: str | None = None, customer_id: str | None = None) -> str:
        case_id = self._next_id("security_cases", "case_id", "SEC", 300000)
        self.db.execute("INSERT INTO security_cases VALUES (?,?,?,?,?,?,?)",
                        (case_id, conv, customer_id, type_, secret_kind, "HIGH", self._now()))
        if type_ == "sensitive_disclosure":
            self.db.execute("UPDATE call_sessions SET secret_detected=1 WHERE conversation_id=?", (conv,))
        self._event("security_case_opened", {"case_id": case_id, "conversation_id": conv, "type": type_, "secret_kind": secret_kind})
        self.db.commit()
        self._raise_risk(conv, "HIGH", "SENSITIVE_INFO_DISCLOSED" if type_ == "sensitive_disclosure" else None)
        return case_id

    def _require(self, req: dict, need: str) -> sqlite3.Row:
        conv = req.get("conversation_id") or ""
        s = self._session(conv)
        if s["locked"]:
            raise ToolError("VERIFICATION_LOCKED", "I'm not able to access account details on this call. Let me connect you to a colleague.")
        token = req.get("verification_token")
        if not token or token == "none":
            raise ToolError("VERIFICATION_REQUIRED", "Before I can check that, I need to confirm who I'm speaking with.")
        row = self.db.execute("SELECT * FROM verification_tokens WHERE token_hash=?",
                              (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
        if not row or row["conversation_id"] != conv:
            raise ToolError("UNAUTHORIZED", "I need to confirm who I'm speaking with first.")
        if row["expires_at"] < self._now():
            raise ToolError("TOKEN_EXPIRED", "For your security I need to confirm your details again.", retryable=True)
        if not policy.tier_ok(row["tier"], need):
            raise ToolError("VERIFICATION_REQUIRED", "To look at that I need a couple more details to confirm it's you.")
        return row

    def _accounts(self, customer_id: str) -> list[str]:
        return [r["account_id"] for r in self.db.execute("SELECT account_id FROM accounts WHERE customer_id=?", (customer_id,))]

    def _account_hold(self, customer_id: str) -> str | None:
        r = self.db.execute("SELECT status FROM accounts WHERE customer_id=? AND status IN ('restricted','fraud_hold')", (customer_id,)).fetchone()
        return r["status"] if r else None

    def daily_report(self) -> dict:
        since = (self.clock() - timedelta(days=1)).replace(microsecond=0).isoformat()
        q = lambda sql: self.db.execute(sql, (since,)).fetchone()[0]  # noqa: E731
        return {
            "calls": q("SELECT COUNT(*) FROM call_sessions WHERE started_at>=?"),
            "by_risk": {r[0]: r[1] for r in self.db.execute(
                "SELECT max_risk, COUNT(*) FROM call_sessions WHERE started_at>=? GROUP BY max_risk", (since,))},
            "secret_detected": q("SELECT COUNT(*) FROM call_sessions WHERE secret_detected=1 AND started_at>=?"),
            "handoffs": q("SELECT COUNT(*) FROM handoffs WHERE created_at>=?"),
            "tickets_created": q("SELECT COUNT(*) FROM tickets WHERE created_by='voice_agent' AND created_at>=?"),
            "disputes": q("SELECT COUNT(*) FROM disputes d JOIN tickets t USING(ticket_id) WHERE t.created_at>=?"),
            "security_cases": q("SELECT COUNT(*) FROM security_cases WHERE created_at>=?"),
            "sla_breached_open": self.db.execute(
                "SELECT COUNT(*) FROM tickets WHERE sla_due_at<? AND status NOT IN ('resolved','closed')",
                (self._now(),)).fetchone()[0],
        }

    # ---------- tools ----------
    def t_assess_request(self, req: dict) -> dict:
        conv, intent = req.get("conversation_id") or "", req.get("intent")
        if intent not in policy.INTENTS:
            raise ToolError("VALIDATION_ERROR", "Could you tell me a little more about what you need help with?")
        base, tier, queue = policy.INTENTS[intent]
        level = base
        if set(req.get("signals") or []) & policy.HIGH_SIGNALS:
            level = "HIGH"
        if (req.get("amount_naira") or 0) * 100 >= policy.HIGH_AMOUNT_KOBO:
            level = "HIGH"
        s = self._session(conv)
        if s["customer_id"] and self._account_hold(s["customer_id"]):
            level = "HIGH"
        level = self._raise_risk(conv, level, intent)
        must_escalate = level == "HIGH" or intent == "HUMAN_AGENT_REQUEST"
        return self._ok({"intent": intent, "risk_level": level, "required_tier": tier,
                         "allowed_tools": policy.allowed_tools(tier), "must_escalate": must_escalate,
                         "escalation_queue": queue}, conv=conv,
                        next_actions=(["request_human_handoff"] if must_escalate else []) + ([] if tier == "T0" else ["verify_caller"]))

    def t_verify_caller(self, req: dict) -> dict:
        conv = req.get("conversation_id") or ""
        s = self._session(conv)
        if s["locked"]:
            raise ToolError("VERIFICATION_LOCKED", "I'm not able to verify you on this call. Let me connect you to a colleague who can help.")
        name = " ".join((req.get("full_name") or "").lower().split())
        provided = {k: req.get(k) for k in ("date_of_birth", "account_last4", "phone_last4", "caller_id") if req.get(k)}
        match, tier = None, "T0"
        for c in self.db.execute("SELECT * FROM customers WHERE name_norm=?", (name,)):
            acct_hashes = {r["nuban_last4_hash"] for r in self.db.execute("SELECT nuban_last4_hash FROM accounts WHERE customer_id=?", (c["customer_id"],))}
            checks = {
                "date_of_birth": lambda v: factor_hash(v) == c["dob_hash"],
                "account_last4": lambda v: factor_hash(v) in acct_hashes,
                "phone_last4": lambda v: factor_hash(v) == c["phone_last4_hash"],
                "caller_id": lambda v: factor_hash(v) == c["phone_hash"],
            }
            if provided and all(checks[k](v) for k, v in provided.items()):
                has_phone = "phone_last4" in provided or "caller_id" in provided
                if {"date_of_birth", "account_last4"} <= provided.keys() and has_phone:
                    tier = "T2"
                elif "account_last4" in provided or has_phone:
                    tier = "T1"
                if tier != "T0":
                    match = c
                    break
        if not match:
            failures = s["verification_failures"] + 1
            locked = int(failures >= MAX_VERIFY_FAILURES)
            self.db.execute("UPDATE call_sessions SET verification_failures=?, locked=? WHERE conversation_id=?", (failures, locked, conv))
            self.db.commit()
            if locked:
                self._raise_risk(conv, "HIGH", "VERIFICATION_FAILED")
                self._security_case(conv, "verification_failed")
                return self._ok({"result": "locked", "tier": "T0", "attempts_remaining": 0, "must_escalate": True},
                                "I'm sorry, I couldn't confirm those details, so I can't access the account on this call. I'll connect you to a colleague.",
                                conv, ["request_human_handoff"])
            return self._ok({"result": "failed", "tier": "T0", "attempts_remaining": MAX_VERIFY_FAILURES - failures},
                            "Sorry, those details don't match our records. Let's try once more.", conv, ["verify_caller"])
        token = secrets.token_urlsafe(24)
        self.db.execute("INSERT INTO verification_tokens VALUES (?,?,?,?,?)",
                        (hashlib.sha256(token.encode()).hexdigest(), conv, match["customer_id"], tier,
                         (self.clock() + TOKEN_TTL).replace(microsecond=0).isoformat()))
        self.db.execute("UPDATE call_sessions SET customer_id=?, verification_tier=? WHERE conversation_id=?", (match["customer_id"], tier, conv))
        self.db.commit()
        if self._account_hold(match["customer_id"]):
            self._raise_risk(conv, "HIGH")
        return self._ok({"result": "verified" if tier == "T2" else "partial", "tier": tier,
                         "verification_token": token, "attempts_remaining": MAX_VERIFY_FAILURES - s["verification_failures"],
                         "first_name": match["full_name"].split()[0]},
                        f"Thank you, {match['full_name'].split()[0]}.", conv)

    def t_find_transactions(self, req: dict) -> dict:
        tok = self._require(req, "T2")
        conv, now = req["conversation_id"], self.clock()
        accts = self._accounts(tok["customer_id"])
        q = f"SELECT * FROM transactions WHERE account_id IN ({','.join('?' * len(accts))})"
        args: list = list(accts)
        date_from = req.get("date_from") or (now - timedelta(days=7)).date().isoformat()
        date_to = req.get("date_to") or now.date().isoformat()
        q += " AND substr(created_at,1,10) BETWEEN ? AND ?"
        args += [date_from, date_to]
        channel_map = {"transfer": ("NIP", "INTRA"), "pos": ("POS",), "atm": ("ATM",), "card_online": ("WEB",), "ussd": ("USSD",)}
        if req.get("channel") in channel_map:
            chans = channel_map[req["channel"]]
            q += f" AND channel IN ({','.join('?' * len(chans))})"
            args += list(chans)
        rows = self.db.execute(q + " ORDER BY created_at DESC", args).fetchall()
        if req.get("amount_naira_approx"):
            target = float(req["amount_naira_approx"]) * 100
            rows = [r for r in rows if abs(r["amount_kobo"] - target) <= max(0.1 * target, 100_00)]
        if not rows:
            return self._ok({"matches": []}, "I couldn't find a transaction matching that. Could you give me the rough date and amount again?", conv)
        if len(rows) > 3:
            return self._err("AMBIGUOUS_MATCH", "I can see a few transactions like that. Do you remember roughly which day, or the exact amount?", False, conv)
        matches = [{"txn_id": r["txn_id"], "date_spoken": spoken_when(r["created_at"], now), "amount_naira": r["amount_kobo"] // 100,
                    "amount_spoken": naira(r["amount_kobo"]), "channel": r["channel"],
                    "counterparty": r["counterparty_name_masked"], "counterparty_bank": r["counterparty_bank"], "status": r["status"]}
                   for r in rows]
        kinds = {"NIP": "a transfer", "INTRA": "a transfer", "POS": "a POS payment", "ATM": "an ATM withdrawal",
                 "WEB": "an online card payment", "USSD": "a USSD transaction"}
        m0 = matches[0]
        to = f" to {m0['counterparty']}" if m0["counterparty"] else ""
        say = "" if len(matches) > 1 else f"I can see {m0['amount_spoken']} {m0['date_spoken']}, {kinds.get(m0['channel'], 'a transaction')}{to}."
        return self._ok({"matches": matches}, say, conv, ["confirm_with_caller", "get_transaction_status"])

    def _own_txn(self, tok, txn_id) -> sqlite3.Row:
        r = self.db.execute("SELECT t.* FROM transactions t JOIN accounts a USING(account_id) WHERE t.txn_id=? AND a.customer_id=?",
                            (txn_id, tok["customer_id"])).fetchone()
        if not r:
            raise ToolError("NOT_FOUND", "I couldn't find that transaction on your account.")
        return r

    def _repeat_contacts(self, customer_id: str, txn_id: str) -> int:
        since = (self.clock() - timedelta(days=7)).isoformat()
        return self.db.execute("SELECT COUNT(*) FROM tickets WHERE customer_id=? AND linked_txn_id=? AND created_at>=?",
                               (customer_id, txn_id, since)).fetchone()[0]

    def t_get_transaction_status(self, req: dict) -> dict:
        tok = self._require(req, "T2")
        conv, now = req["conversation_id"], self.clock()
        t = self._own_txn(tok, req.get("txn_id"))
        rev = self.db.execute("SELECT * FROM reversals WHERE txn_id=?", (t["txn_id"],)).fetchone()
        key = ("ATM_ON_US" if t["on_us"] else "ATM_NOT_ON_US") if t["channel"] == "ATM" else t["channel"]
        window_h = policy.WINDOW_HOURS.get(key, 72)
        deadline = datetime.fromisoformat(t["created_at"]) + timedelta(hours=window_h)
        within = now <= deadline
        data = {"txn_id": t["txn_id"], "status": t["status"], "debited": bool(t["debited"]),
                "beneficiary_credited": None if t["beneficiary_credited"] is None else bool(t["beneficiary_credited"]),
                "within_policy_window": within, "policy_window_hours": window_h, "policy_ref": "KB-03-transfers-and-reversals"}
        if rev:
            data["reversal"] = {"status": rev["status"], "expected_by": rev["expected_by"], "completed_at": rev["completed_at"]}
        action, say = "none", ""
        amt = naira(t["amount_kobo"])
        if t["status"] == "failed" and not t["debited"]:
            say = f"That transfer of {amt} failed, but the good news is no money left your account. You can try again."
        elif rev and rev["status"] == "completed":
            say = f"The {amt} was reversed to your account {spoken_when(rev['completed_at'], now)}."
        elif rev and rev["expected_by"] and rev["expected_by"] < now.isoformat():
            action, say = "create_ticket", f"The reversal of {amt} is overdue. I'm sorry about that. I'll log a complaint so it's escalated."
        elif t["channel"] == "ATM" and t["debited"]:
            action, say = "create_dispute", f"I can see the {amt} ATM debit. I'll log a dispute so it's investigated and refunded if the cash wasn't dispensed."
        elif t["channel"] == "POS" and t["debited"]:
            action, say = "create_dispute", f"I can see the {amt} POS debit. If you were charged twice or the payment failed, I can log a dispute."
        elif t["status"] in ("pending", "reversal_pending") and t["debited"] and not t["beneficiary_credited"]:
            if within:
                action = "wait"
                say = (f"Your {amt} transfer is still being processed. Under CBN guidelines it should either reach the recipient "
                       f"or come back to you within {window_h} hours of the transfer.")
            else:
                action, say = "create_ticket", f"Your {amt} transfer has been pending longer than it should. I'll raise a complaint so it's escalated."
        elif t["status"] == "successful" and t["beneficiary_credited"]:
            say = f"That {amt} transfer was successful and the receiving bank confirmed the credit."
        if t["amount_kobo"] >= policy.HIGH_AMOUNT_KOBO or self._repeat_contacts(tok["customer_id"], t["txn_id"]) >= policy.REPEAT_CONTACT_THRESHOLD:
            self._raise_risk(conv, "HIGH")
            action = "escalate"
            say += " Because of the amount or how many times you've had to contact us, I'm going to get a senior colleague to handle this."
        data["recommended_action"] = action
        return self._ok(data, say.strip(), conv, [action] if action != "none" else [])

    def t_get_card_status(self, req: dict) -> dict:
        tok = self._require(req, "T2")
        conv = req["conversation_id"]
        cards = self.db.execute("SELECT c.* FROM cards c JOIN accounts a USING(account_id) WHERE a.customer_id=?", (tok["customer_id"],)).fetchall()
        if req.get("card_last4"):
            cards = [c for c in cards if c["pan_last4"] == req["card_last4"]]
        if not cards:
            raise ToolError("NOT_FOUND", "I couldn't find a card ending in those digits.")
        card = cards[0]
        auth = self.db.execute("SELECT * FROM card_authorizations WHERE card_id=? AND result='declined' ORDER BY created_at DESC", (card["card_id"],)).fetchone()
        safe = {"INSUFFICIENT_FUNDS": "insufficient_funds", "CARD_BLOCKED": "card_blocked", "ONLINE_DISABLED": "online_disabled",
                "LIMIT_EXCEEDED": "limit_reached", "EXPIRED": "expired", "FRAUD_RULE": "needs_review", "ISSUER_UNAVAILABLE": "temporary_issue"}
        phrases = {"insufficient_funds": "there weren't enough available funds for that payment",
                   "card_blocked": "the card is currently blocked", "online_disabled": "online payments are switched off on the card. You can switch them on in the ENTIN app under Cards",
                   "limit_reached": "it went over your daily card limit", "expired": "the card has expired",
                   "needs_review": "the payment needs a review by our team", "temporary_issue": "there was a temporary system issue"}
        data = {"card_last4": card["pan_last4"], "status": card["status"], "online_enabled": bool(card["online_enabled"])}
        say = f"Your card ending {' '.join(card['pan_last4'])} is {card['status'].replace('_', ' ')}."
        nxt = []
        if auth:
            cat = safe.get(auth["decline_code"], "needs_review")
            data["latest_decline"] = {"date_spoken": spoken_when(auth["created_at"], self.clock()), "merchant": auth["merchant_name"], "reason_category": cat}
            say = f"The payment was declined because {phrases[cat]}."
            if cat == "needs_review":
                self._raise_risk(conv, "HIGH")
                data["must_escalate"] = True
                nxt = ["request_human_handoff"]
        return self._ok(data, say, conv, nxt)

    def t_block_card(self, req: dict) -> dict:
        tok = self._require(req, "T1")
        conv = req["conversation_id"]
        if req.get("caller_confirmed") is not True:
            raise ToolError("VALIDATION_ERROR", "Before I block it, can you confirm you want the card blocked? It can't be used again once blocked.")
        reason = req.get("reason")
        if reason not in ("lost", "stolen", "suspected_fraud"):
            raise ToolError("VALIDATION_ERROR", "Is the card lost, stolen, or are you worried about fraud?")
        cards = self.db.execute("SELECT c.* FROM cards c JOIN accounts a USING(account_id) WHERE a.customer_id=? AND c.status='active'", (tok["customer_id"],)).fetchall()
        if not req.get("all_cards"):
            cards = [c for c in cards if c["pan_last4"] == req.get("card_last4")]
        if not cards:
            raise ToolError("NOT_FOUND", "I couldn't find an active card with those last four digits.")
        status = {"lost": "blocked_lost", "stolen": "blocked_stolen", "suspected_fraud": "blocked_fraud"}[reason]
        for c in cards:
            self.db.execute("UPDATE cards SET status=?, blocked_at=?, block_reason=? WHERE card_id=?", (status, self._now(), reason, c["card_id"]))
            self.db.execute("INSERT INTO notification_outbox (customer_id, template, channel, created_at) VALUES (?,?,?,?)",
                            (tok["customer_id"], "card_blocked", "sms", self._now()))
        block_ref = self._next_id("audit_log", "id", "BLK", 500000)
        ticket = self._new_ticket(tok["customer_id"], "CARD_LOST_STOLEN", None, f"Replacement for {len(cards)} blocked card(s), reason {reason}", "P2", conv, req.get("idempotency_key"))
        self._event("card_blocked", {"conversation_id": conv, "customer_id": tok["customer_id"], "cards": [c["pan_last4"] for c in cards], "reason": reason, "block_ref": block_ref})
        self.db.commit()
        self._raise_risk(conv, "HIGH", "CARD_LOST_STOLEN")
        last4s = ", ".join(" ".join(c["pan_last4"]) for c in cards)
        return self._ok({"id": block_ref, "blocked": True, "block_ref": block_ref, "cards_blocked": [c["pan_last4"] for c in cards],
                         "replacement_ticket_id": ticket},
                        f"Done. I've blocked the card{'s' if len(cards) > 1 else ''} ending {last4s}. Nobody can use {'them' if len(cards) > 1 else 'it'} now.",
                        conv, ["offer_human"] if reason != "lost" else [])

    def t_get_digital_access_status(self, req: dict) -> dict:
        tok = self._require(req, "T1")
        conv = req["conversation_id"]
        p = self.db.execute("SELECT * FROM digital_profiles WHERE customer_id=?", (tok["customer_id"],)).fetchone()
        ev = self.db.execute("SELECT status, COUNT(*) n FROM otp_delivery_events WHERE customer_id=? AND created_at>=? GROUP BY status",
                             (tok["customer_id"], (self.clock() - timedelta(days=1)).isoformat())).fetchall()
        otp = {r["status"]: r["n"] for r in ev}
        data = {"profile_status": p["status"], "device_bound": bool(p["device_bound"]), "otp_recent": otp,
                "guidance_article_id": "KB-09-mobile-banking"}
        if p["status"] == "locked":
            if not policy.tier_ok(tok["tier"], "T2"):
                data = {"profile_status": "needs_full_verification", "otp_recent": otp}
                say = "I can see there's an issue with your mobile banking access. To tell you more I need to fully verify you."
            else:
                say = ("Your mobile banking profile is locked after too many wrong attempts. I can't unlock it on this call, "
                       "but you can reset it yourself in the app with 'Forgot password' or visit any branch with a valid ID.")
        elif not p["device_bound"]:
            say = "It looks like you're logging in on a new phone. The app will ask you to link the new device. Follow those steps and it should work."
        elif otp.get("dnd_blocked"):
            say = ("Our messages to your number are being blocked by Do-Not-Disturb on your line. You can text ALLOW to your network's DND code, "
                   "or switch your OTP to email in the app.")
        elif otp.get("failed") or otp.get("delayed"):
            say = "There's been a delay delivering messages to your network. Please wait a few minutes and try again."
        else:
            say = "Everything looks normal on your mobile banking profile."
        return self._ok(data, say, conv)

    def _new_ticket(self, customer_id, category, txn_id, summary, priority, conv, idem=None) -> str:
        if idem:
            r = self.db.execute("SELECT ticket_id FROM tickets WHERE idempotency_key=?", (idem,)).fetchone()
            if r:
                return r["ticket_id"]
        tid = self._next_id("tickets", "ticket_id", "TKT", 104300)
        self.db.execute("INSERT INTO tickets VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (tid, customer_id, category, txn_id, "open", priority,
                         (self.clock() + timedelta(days=policy.COMPLAINT_SLA_DAYS)).replace(microsecond=0).isoformat(),
                         redact(summary or "")[:400], "voice_agent", self._now(), idem))
        self._event("ticket_created", {"ticket_id": tid, "conversation_id": conv, "category": category, "priority": priority})
        self.db.commit()
        return tid

    def t_create_ticket(self, req: dict) -> dict:
        tok = self._require(req, "T1")
        conv = req["conversation_id"]
        cat = req.get("category")
        if cat not in policy.INTENTS:
            raise ToolError("VALIDATION_ERROR", "What would you like me to log this as?")
        txn = req.get("linked_txn_id")
        if txn:
            self._own_txn(tok, txn)
        priority = "P1" if self._risk(conv) == "HIGH" else "P2" if req.get("callback_requested") else "P3"
        tid = self._new_ticket(tok["customer_id"], cat, txn, req.get("summary"), priority, conv, req.get("idempotency_key"))
        return self._ok({"id": tid, "ticket_id": tid, "ticket_id_spoken": spoken_ref(tid), "priority": priority,
                         "sla_days": policy.COMPLAINT_SLA_DAYS},
                        f"I've logged that for you. Your reference is {spoken_ref(tid)}. We aim to resolve it within {policy.COMPLAINT_SLA_DAYS} days, and you'll get updates by SMS.",
                        conv)

    def t_create_dispute(self, req: dict) -> dict:
        tok = self._require(req, "T2")
        conv = req["conversation_id"]
        t = self._own_txn(tok, req.get("txn_id"))
        dtype = req.get("type")
        if dtype not in ("ATM_NO_CASH", "POS_DOUBLE_DEBIT", "POS_FAILED_DEBITED", "UNAUTHORIZED"):
            raise ToolError("VALIDATION_ERROR", "Can you tell me what went wrong with that transaction?")
        idem = req.get("idempotency_key")
        if idem:
            r = self.db.execute("SELECT * FROM disputes WHERE idempotency_key=?", (idem,)).fetchone()
            if r:
                return self._ok({"id": r["dispute_id"], "dispute_id": r["dispute_id"], "ticket_id": r["ticket_id"]}, "", conv)
        key = ("ATM_ON_US" if t["on_us"] else "ATM_NOT_ON_US") if t["channel"] == "ATM" else t["channel"]
        hours = max(policy.WINDOW_HOURS.get(key, 72), 24)
        intent = {"ATM_NO_CASH": "ATM_CASH_DISPUTE", "UNAUTHORIZED": "UNAUTHORIZED_TRANSACTION"}.get(dtype, "POS_DISPUTE")
        if policy.INTENTS[intent][0] == "HIGH":
            self._raise_risk(conv, "HIGH", intent)
        tid = self._new_ticket(tok["customer_id"], intent, t["txn_id"], req.get("caller_statement"),
                               "P1" if self._risk(conv) == "HIGH" else "P2", conv)
        did = self._next_id("disputes", "dispute_id", "DSP", 200000)
        self.db.execute("INSERT INTO disputes VALUES (?,?,?,?,?,?,?)",
                        (did, tid, t["txn_id"], dtype, "open",
                         (self.clock() + timedelta(hours=hours)).replace(microsecond=0).isoformat(), idem))
        self._event("dispute_created", {"dispute_id": did, "ticket_id": tid, "conversation_id": conv, "type": dtype})
        self.db.commit()
        return self._ok({"id": did, "dispute_id": did, "dispute_id_spoken": spoken_ref(did), "ticket_id": tid,
                         "expected_resolution_hours": hours, "policy_ref": "KB-06-disputes"},
                        f"I've logged a dispute. Your reference is {spoken_ref(did)}. Under CBN timelines this type of case should be resolved within {hours} hours.",
                        conv, ["offer_human"] if self._risk(conv) == "HIGH" else [])

    def t_get_ticket_status(self, req: dict) -> dict:
        tok = self._require(req, "T1")
        conv, ref = req["conversation_id"], (req.get("reference") or "").upper().replace(" ", "")
        if ref.startswith("DSP"):
            d = self.db.execute("SELECT ticket_id FROM disputes WHERE dispute_id=?", (ref,)).fetchone()
            ref = d["ticket_id"] if d else ref
        t = self.db.execute("SELECT * FROM tickets WHERE ticket_id=? AND customer_id=?", (ref, tok["customer_id"])).fetchone()
        if not t:
            raise ToolError("NOT_FOUND", "I couldn't find that reference on your profile. Could you read it out again?")
        breached = t["sla_due_at"] < self._now() and t["status"] not in ("resolved", "closed")
        repeats = self._repeat_contacts(tok["customer_id"], t["linked_txn_id"]) if t["linked_txn_id"] else 1
        data = {"id": t["ticket_id"], "ticket_id": t["ticket_id"], "status": t["status"], "sla_breached": breached,
                "repeat_contacts_7d": repeats}
        say = f"Your complaint {spoken_ref(t['ticket_id'])} is {t['status'].replace('_', ' ')}."
        nxt = []
        if breached or repeats >= policy.REPEAT_CONTACT_THRESHOLD:
            self._raise_risk(conv, "HIGH")
            self.db.execute("UPDATE tickets SET priority='P1' WHERE ticket_id=?", (t["ticket_id"],))
            self._event("sla_breached", {"ticket_id": t["ticket_id"], "conversation_id": conv, "repeat_contacts_7d": repeats})
            self.db.commit()
            say += " I'm sorry it's taken this long. I've escalated it as a priority and I'll connect you to a senior colleague."
            nxt = ["request_human_handoff"]
        return self._ok(data, say, conv, nxt)

    def t_report_security_event(self, req: dict) -> dict:
        conv = req.get("conversation_id") or ""
        typ = req.get("type")
        if typ not in ("sensitive_disclosure", "social_engineering", "unauthorized_txn", "prompt_injection", "third_party_data_request"):
            raise ToolError("VALIDATION_ERROR", "")
        s = self._session(conv)
        case = self._security_case(conv, typ, req.get("secret_kind"), s["customer_id"])
        if typ in ("prompt_injection", "third_party_data_request"):
            self._raise_risk(conv, "HIGH", "PROHIBITED_REQUEST")
        advice = {"pin": "Please change your PIN in the ENTIN app or at any ATM as soon as you can.",
                  "otp": "Don't use that code for anything, and don't share codes with anyone. If you didn't start a transaction, tell me now.",
                  "cvv": "To be safe, I recommend we block that card and issue a new one.",
                  "password": "Please change your mobile banking password in the app as soon as you can.",
                  "card_number": "To be safe, I recommend we block that card and issue a new one."}
        say = advice.get(req.get("secret_kind") or "", "")
        return self._ok({"id": case, "case_id": case, "advice_article_id": "KB-12-security"}, say, conv)

    def t_request_human_handoff(self, req: dict) -> dict:
        conv = req.get("conversation_id") or ""
        s = self._session(conv)
        risk = s["max_risk"]
        intents = s["intents"].split(",") if s["intents"] else []
        queue = next((policy.INTENTS[i][2] for i in reversed(intents) if i in policy.INTENTS and policy.INTENTS[i][2] != "general"), "general")
        priority = {"HIGH": "P1", "MEDIUM": "P2", "LOW": "P3"}[risk]
        mode = "callback" if req.get("caller_preference") == "callback" else "transfer"
        hid = self._next_id("handoffs", "handoff_id", "HOF", 400000)
        self.db.execute("INSERT INTO handoffs VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (hid, conv, queue, priority, risk, s["verification_tier"], req.get("reason") or "caller_request",
                         redact(req.get("summary") or "")[:600], mode, "queued", self._now()))
        self._event("handoff_created", {"handoff_id": hid, "conversation_id": conv, "queue": queue, "priority": priority,
                                        "risk_level": risk, "summary": redact(req.get("summary") or "")[:600]})
        self.db.commit()
        say = ("I'm connecting you to a colleague now. I've passed on everything we discussed, so you won't need to repeat yourself."
               if mode == "transfer" else "I've booked a callback. A colleague will call you back on your registered number.")
        return self._ok({"id": hid, "handoff_id": hid, "mode": mode, "queue": queue, "priority": priority,
                         "transfer_destination_key": f"{queue}_line"}, say, conv, ["transfer_to_number"] if mode == "transfer" else ["end_call"])

    def t_find_branch_or_atm(self, req: dict) -> dict:
        city = (req.get("city") or "").strip().lower()
        area = (req.get("area") or "").strip().lower()
        typ = req.get("type") or "any"
        rows = [r for r in self.db.execute("SELECT * FROM branches_atms")
                if (not city or r["city"].lower() == city) and (not area or area in r["area"].lower())
                and (typ == "any" or r["type"] == typ)][:3]
        if not rows:
            return self._ok({"results": []}, "I don't have an ENTIN location there. The nearest ones are listed in the app under Locations.")
        res = [{"name": r["name"], "address": r["address"], "hours": r["hours"], "status": r["status"]} for r in rows]
        first = res[0]
        extra = " It's currently out of service." if first["status"] == "out_of_service" else ""
        return self._ok({"results": res}, f"The closest is {first['name']}, at {first['address']}. Opening hours: {first['hours']}.{extra}")
