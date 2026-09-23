"""Secret detection, redaction and factor hashing.

The same patterns are mirrored in the n8n post-call redaction node.
"""
import hashlib
import hmac
import os
import re

SALT = os.environ.get("ENTIN_FACTOR_SALT", "entin-demo-salt-change-me").encode()

SECRET_WORDS = r"(?:pin|otp|one[\s-]?time|cvv|cvc|security\s+code|passcode|password|pass\s*word|token|auth(?:entication)?\s+code)"
# card-number-like: 13-19 digits, optionally separated by spaces or dashes
PAN_RE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
# a secret word followed (or preceded) by a 3-8 digit code within a few words
CODE_AFTER_RE = re.compile(SECRET_WORDS + r"\W+(?:\w+\W+){0,3}?(\d[\d ]{2,9}\d|\d{3,8})", re.I)
CODE_BEFORE_RE = re.compile(r"(?<!\d)(\d{3,8})(?!\d)\W+(?:\w+\W+){0,2}?(?:is\s+)?(?:my\s+)?" + SECRET_WORDS, re.I)
# "my password is <anything>"
PASSWORD_PHRASE_RE = re.compile(r"(?:password|passcode)\s+(?:is|na)\s+(\S+)", re.I)

SECRET_KINDS = {"pin": "pin", "otp": "otp", "one": "otp", "cvv": "cvv", "cvc": "cvv",
                "security": "cvv", "pass": "password", "password": "password",
                "passcode": "password", "token": "token", "auth": "token"}


def factor_hash(value: str) -> str:
    norm = " ".join(str(value).strip().lower().split())
    return hmac.new(SALT, norm.encode(), hashlib.sha256).hexdigest()


def detect_secret(text: str) -> str | None:
    """Return the kind of secret found in text, or None."""
    if not text:
        return None
    if PAN_RE.search(text):
        return "card_number"
    m = CODE_AFTER_RE.search(text) or CODE_BEFORE_RE.search(text)
    if m:
        word = re.search(SECRET_WORDS, m.group(0), re.I).group(0).lower().split()[0]
        for key, kind in SECRET_KINDS.items():
            if word.startswith(key):
                return kind
        return "other"
    if PASSWORD_PHRASE_RE.search(text):
        return "password"
    return None


def redact(text: str) -> str:
    if not text:
        return text
    text = PAN_RE.sub("[REDACTED_CARD]", text)
    text = CODE_AFTER_RE.sub(lambda m: m.group(0).replace(m.group(1), "[REDACTED_CODE]"), text)
    text = CODE_BEFORE_RE.sub(lambda m: m.group(0).replace(m.group(1), "[REDACTED_CODE]", 1), text)
    text = PASSWORD_PHRASE_RE.sub(lambda m: m.group(0).replace(m.group(1), "[REDACTED_PASSWORD]"), text)
    return text


# Fields that legitimately hold digits and are validated by shape instead of scanned.
STRUCTURED_FIELDS = {"conversation_id", "verification_token", "caller_id", "date_of_birth",
                     "account_last4", "phone_last4", "card_last4", "txn_id", "reference",
                     "idempotency_key", "date_from", "date_to", "amount_naira_approx", "amount_naira"}


def scan_payload(payload: dict) -> str | None:
    """Scan every free-text field of a tool request for secrets."""
    for key, value in payload.items():
        if key in STRUCTURED_FIELDS:
            continue
        if isinstance(value, str):
            kind = detect_secret(value)
            if kind:
                return kind
        elif isinstance(value, list):
            for v in value:
                if isinstance(v, str) and detect_secret(v):
                    return detect_secret(v)
    return None
