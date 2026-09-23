"""Synthetic ENTIN Bank database: schema + deterministic seed.

Everything here is fictional. No PIN, OTP, password, CVV, full card number,
BVN or NIN is ever stored. Verification factors are salted hashes.
Money is integer kobo. IDs are fixed per persona so tests can rely on them.
"""
import os
import sqlite3
from datetime import datetime, timedelta, timezone

from .guard import factor_hash

SCHEMA = """
CREATE TABLE customers (
  customer_id TEXT PRIMARY KEY, full_name TEXT NOT NULL, name_norm TEXT NOT NULL,
  dob_hash TEXT NOT NULL, phone_e164_masked TEXT NOT NULL, phone_hash TEXT NOT NULL,
  phone_last4_hash TEXT NOT NULL, vulnerability_flag INTEGER NOT NULL DEFAULT 0,
  persona TEXT, is_synthetic INTEGER NOT NULL DEFAULT 1 CHECK (is_synthetic = 1));
CREATE TABLE accounts (
  account_id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers,
  nuban TEXT NOT NULL, nuban_last4_hash TEXT NOT NULL, type TEXT NOT NULL,
  status TEXT NOT NULL, restriction_code TEXT, balance_kobo INTEGER NOT NULL,
  is_synthetic INTEGER NOT NULL DEFAULT 1 CHECK (is_synthetic = 1));
CREATE TABLE cards (
  card_id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts,
  scheme TEXT NOT NULL, pan_last4 TEXT NOT NULL, status TEXT NOT NULL,
  online_enabled INTEGER NOT NULL, blocked_at TEXT, block_reason TEXT,
  is_synthetic INTEGER NOT NULL DEFAULT 1 CHECK (is_synthetic = 1));
CREATE TABLE transactions (
  txn_id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts,
  channel TEXT NOT NULL, direction TEXT NOT NULL, amount_kobo INTEGER NOT NULL,
  counterparty_bank TEXT, counterparty_name_masked TEXT, narration TEXT,
  session_ref TEXT, status TEXT NOT NULL, debited INTEGER NOT NULL,
  beneficiary_credited INTEGER, on_us INTEGER, terminal_id TEXT,
  created_at TEXT NOT NULL,
  is_synthetic INTEGER NOT NULL DEFAULT 1 CHECK (is_synthetic = 1));
CREATE TABLE reversals (
  reversal_id TEXT PRIMARY KEY, txn_id TEXT NOT NULL REFERENCES transactions,
  status TEXT NOT NULL, expected_by TEXT, completed_at TEXT);
CREATE TABLE card_authorizations (
  auth_id TEXT PRIMARY KEY, card_id TEXT NOT NULL REFERENCES cards,
  merchant_name TEXT, amount_kobo INTEGER, result TEXT NOT NULL,
  decline_code TEXT, created_at TEXT NOT NULL);
CREATE TABLE digital_profiles (
  customer_id TEXT PRIMARY KEY REFERENCES customers, status TEXT NOT NULL,
  failed_login_count INTEGER NOT NULL, device_bound INTEGER NOT NULL,
  otp_channel TEXT NOT NULL);
CREATE TABLE otp_delivery_events (  -- delivery events only, never codes
  event_id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, channel TEXT NOT NULL,
  status TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE branches_atms (
  location_id TEXT PRIMARY KEY, type TEXT NOT NULL, name TEXT NOT NULL,
  city TEXT NOT NULL, area TEXT NOT NULL, address TEXT NOT NULL,
  hours TEXT NOT NULL, status TEXT NOT NULL);
CREATE TABLE tickets (
  ticket_id TEXT PRIMARY KEY, customer_id TEXT, category TEXT NOT NULL,
  linked_txn_id TEXT, status TEXT NOT NULL, priority TEXT NOT NULL,
  sla_due_at TEXT NOT NULL, summary_redacted TEXT, created_by TEXT NOT NULL,
  created_at TEXT NOT NULL, idempotency_key TEXT UNIQUE);
CREATE TABLE disputes (
  dispute_id TEXT PRIMARY KEY, ticket_id TEXT NOT NULL, txn_id TEXT NOT NULL,
  type TEXT NOT NULL, status TEXT NOT NULL, expected_resolution_at TEXT NOT NULL,
  idempotency_key TEXT UNIQUE);
CREATE TABLE security_cases (
  case_id TEXT PRIMARY KEY, conversation_id TEXT, customer_id TEXT,
  type TEXT NOT NULL, secret_kind TEXT, severity TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE handoffs (
  handoff_id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, queue TEXT NOT NULL,
  priority TEXT NOT NULL, risk_level TEXT NOT NULL, verification_tier TEXT NOT NULL,
  reason TEXT NOT NULL, summary_redacted TEXT, mode TEXT NOT NULL,
  status TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE call_sessions (
  conversation_id TEXT PRIMARY KEY, customer_id TEXT, verification_tier TEXT NOT NULL,
  verification_failures INTEGER NOT NULL DEFAULT 0, locked INTEGER NOT NULL DEFAULT 0,
  max_risk TEXT NOT NULL DEFAULT 'LOW', intents TEXT NOT NULL DEFAULT '',
  secret_detected INTEGER NOT NULL DEFAULT 0, started_at TEXT NOT NULL);
CREATE TABLE verification_tokens (
  token_hash TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, customer_id TEXT NOT NULL,
  tier TEXT NOT NULL, expires_at TEXT NOT NULL);
CREATE TABLE notification_outbox (  -- simulated only, never delivered
  id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id TEXT, template TEXT NOT NULL,
  channel TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'simulated', created_at TEXT NOT NULL);
CREATE TABLE events_outbox (  -- consumed by n8n
  id INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT NOT NULL, payload TEXT NOT NULL,
  delivered INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
CREATE TABLE audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, actor TEXT NOT NULL,
  conversation_id TEXT, action TEXT NOT NULL, object_id TEXT, result TEXT NOT NULL,
  meta TEXT);
"""

# (customer_id, name, dob, phone, persona) — phones use the fictional +234 700 0xx xxxx pattern
CUSTOMERS = [
    ("CUS-0001", "Adaeze Okafor", "1991-03-14", "+2347000010001", "S01/S17 debited transfer not received"),
    ("CUS-0002", "Tunde Bakare", "1988-07-02", "+2347000010002", "S02 failed transfer, not debited"),
    ("CUS-0003", "Chinedu Eze", "1985-11-23", "+2347000010003", "S03 reversal completed; S21 open ticket"),
    ("CUS-0004", "Halima Yusuf", "1993-01-30", "+2347000010004", "S04 reversal overdue; S22 SLA breached ticket"),
    ("CUS-0005", "Emeka Nwosu", "1990-05-09", "+2347000010005", "S05 pending transfer"),
    ("CUS-0006", "Funke Adeyemi", "1987-09-17", "+2347000010006", "S06 ATM no cash"),
    ("CUS-0007", "Ibrahim Musa", "1992-12-01", "+2347000010007", "S07 POS double debit"),
    ("CUS-0008", "Ngozi Obi", "1995-04-21", "+2347000010008", "S08 decline insufficient funds"),
    ("CUS-0009", "Segun Ade", "1989-08-08", "+2347000010009", "S09 decline online disabled"),
    ("CUS-0010", "Aisha Bello", "1994-02-11", "+2347000010010", "S10 fraud hold"),
    ("CUS-0011", "Kelechi Umeh", "1986-06-19", "+2347000010011", "S11 lost card"),
    ("CUS-0012", "Ronke Adebayo", "1983-10-05", "+2347000010012", "S12 unauthorised web debits"),
    ("CUS-0013", "Uche Okonkwo", "1996-03-03", "+2347000010013", "S13 new device login"),
    ("CUS-0014", "Grace Etim", "1990-12-25", "+2347000010014", "S14 digital profile locked"),
    ("CUS-0016", "Musa Danjuma", "1984-07-15", "+2347000010016", "S16 OTP DND blocked"),
    ("CUS-0018", "Femi Ogun", "1982-01-27", "+2347000010018", "S18 volunteers PIN"),
    ("CUS-0019", "Joy Nnaji", "1997-05-30", "+2347000010019", "S19 scammed, shared OTP"),
    ("CUS-0020", "Tope Salami", "1981-09-09", "+2347000010020", "S20 account restricted"),
    ("CUS-0024", "Daniel Okoro", "1979-04-04", "+2347000010024", "S24 N2.5m transfer not received"),
    ("CUS-0025", "Kemi Oladipo", "1992-10-10", "+2347000010025", "S25 wants human"),
    ("CUS-0031", "Obinna Chukwu", "1991-08-18", "+2347000010031", "S31 no transaction reference, similar transfers"),
    ("CUS-0032", "Zainab Lawal", "1993-06-06", "+2347000010032", "S32 does not recognise N150,000"),
    ("CUS-0034", "Bayo Ogunleye", "1980-02-29", "+2347000010034", "S34 block every card"),
    ("CUS-0036", "Amaka Nwachukwu", "1988-12-12", "+2347000010036", "S36 reported three times"),
    ("CUS-0037", "Gerald Okeke", "1990-06-15", "+2347000010037", "S37 demo call: N70,000 deducted yesterday ~4pm, doesn't know why"),
]


def _acct(n: int) -> tuple[str, str]:
    """ACC-#### plus a 10-digit NUBAN-shaped number in the fictional 99xxxxxxxx range."""
    return f"ACC-{n:04d}", f"99{n:08d}"


def iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def connect(path: str | None = None) -> sqlite3.Connection:
    path = path or os.environ.get("ENTIN_DB", "entin.db")
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def seed(conn: sqlite3.Connection, now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    ago = lambda **kw: iso(now - timedelta(**kw))  # noqa: E731
    conn.executescript(SCHEMA)
    c = conn.execute

    for cid, name, dob, phone, persona in CUSTOMERS:
        n = int(cid[-4:])
        c("INSERT INTO customers VALUES (?,?,?,?,?,?,?,0,?,1)",
          (cid, name, " ".join(name.lower().split()), factor_hash(dob),
           phone[:7] + "*****" + phone[-2:], factor_hash(phone), factor_hash(phone[-4:]), persona))
        acc_id, nuban = _acct(n)
        status = {"CUS-0010": "fraud_hold", "CUS-0020": "restricted"}.get(cid, "active")
        restriction = "PND-COMPLIANCE-REVIEW" if cid == "CUS-0020" else None
        c("INSERT INTO accounts VALUES (?,?,?,?,?,?,?,?,1)",
          (acc_id, cid, nuban, factor_hash(nuban[-4:]), "savings", status, restriction, 18_500_000))
        card_status = "blocked_fraud" if cid == "CUS-0010" else "active"
        c("INSERT INTO cards VALUES (?,?,?,?,?,?,?,?,1)",
          (f"CRD-{n:04d}", acc_id, "Verve", f"{(n * 37) % 10000:04d}", card_status,
           0 if cid == "CUS-0009" else 1, None, None))
        c("INSERT INTO digital_profiles VALUES (?,?,?,?,?)",
          (cid, "locked" if cid == "CUS-0014" else "active",
           5 if cid == "CUS-0014" else 0, 0 if cid == "CUS-0013" else 1, "sms"))

    # extra cards for S34 (block every card)
    for i, last4 in ((1, "4410"), (2, "7781")):
        c("INSERT INTO cards VALUES (?,?,?,?,?,?,?,?,1)",
          (f"CRD-0034-{i}", "ACC-0034", "Mastercard", last4, "active", 1, None, None))

    T = lambda *r: c("INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)", r)  # noqa: E731
    #  txn_id, account, channel, dir, kobo, cp_bank, cp_name, narration, session_ref, status, debited, credited, on_us, terminal, created
    T("TXN-000101", "ACC-0001", "NIP", "debit", 4_500_000, "Fictional Trust Bank", "Chioma O****r", "Transfer to Chioma", "NIPSIM000101", "pending", 1, 0, 0, None, ago(hours=20))
    T("TXN-000201", "ACC-0002", "NIP", "debit", 1_200_000, "Demo Microfinance Bank", "Kunle B****e", "Rent part", "NIPSIM000201", "failed", 0, 0, 0, None, ago(hours=3))
    T("TXN-000301", "ACC-0003", "NIP", "debit", 3_000_000, "Fictional Trust Bank", "Ifeoma E*e", "School fees", "NIPSIM000301", "reversed", 1, 0, 0, None, ago(days=4))
    T("TXN-000401", "ACC-0004", "NIP", "debit", 6_000_000, "Sample Savings Bank", "Aminu Y***f", "Family support", "NIPSIM000401", "reversal_pending", 1, 0, 0, None, ago(days=5))
    T("TXN-000501", "ACC-0005", "NIP", "debit", 1_500_000, "Fictional Trust Bank", "Obi N***u", "Transfer", "NIPSIM000501", "pending", 1, None, 0, None, ago(minutes=20))
    T("TXN-000601", "ACC-0006", "ATM", "debit", 2_000_000, "Sample Savings Bank ATM", None, "ATM withdrawal - no cash dispensed", None, "successful", 1, None, 0, "ATM-SSB-LAG-0419", ago(hours=30))
    T("TXN-000701", "ACC-0007", "POS", "debit", 1_250_000, None, "Mama Put Kitchen Ikeja", "POS purchase", None, "successful", 1, None, 0, "POS-2033-8811", ago(days=1, hours=2))
    T("TXN-000702", "ACC-0007", "POS", "debit", 1_250_000, None, "Mama Put Kitchen Ikeja", "POS purchase", None, "successful", 1, None, 0, "POS-2033-8811", ago(days=1, hours=2, seconds=-40))
    for i, mins in enumerate((0, 4, 9)):
        T(f"TXN-00120{i + 1}", "ACC-0012", "WEB", "debit", 4_950_000, None, "ShopGlobal Online", "Card web purchase", None, "successful", 1, None, 0, None, ago(hours=9, minutes=-mins))
    T("TXN-001901", "ACC-0019", "NIP", "debit", 8_000_000, "Quick Fictional Bank", "Unknown R*******t", "Refund processing", "NIPSIM001901", "successful", 1, 1, 0, None, ago(hours=5))
    T("TXN-002401", "ACC-0024", "NIP", "debit", 250_000_000, "Fictional Trust Bank", "Okoro Holdings L**", "Supplier payment", "NIPSIM002401", "pending", 1, 0, 0, None, ago(hours=26))
    for i, (kobo, days) in enumerate(((2_000_000, 1), (2_000_000, 2), (2_500_000, 2), (2_000_000, 3))):
        T(f"TXN-00310{i + 1}", "ACC-0031", "NIP", "debit", kobo, "Fictional Trust Bank", "Nneka C****u", "Upkeep", f"NIPSIM00310{i + 1}", "successful" if i else "pending", 1, 0 if i == 0 else 1, 0, None, ago(days=days))
    T("TXN-003201", "ACC-0032", "POS", "debit", 15_000_000, None, "Lekki Luxury Stores", "POS purchase", None, "successful", 1, None, 0, "POS-9001-1200", ago(days=2))
    # S37 Gerald: N70,000 web card debit yesterday ~16:05 (demo call script)
    gerald_at = (now - timedelta(days=1)).replace(hour=16, minute=5, second=0, microsecond=0)
    T("TXN-003701", "ACC-0037", "WEB", "debit", 7_000_000, None, "QuickBuy Online (fictional)", "Card web purchase", None, "successful", 1, None, 0, None, iso(gerald_at))
    T("TXN-003601", "ACC-0036", "NIP", "debit", 3_500_000, "Sample Savings Bank", "Uju N********u", "Transfer", "NIPSIM003601", "pending", 1, 0, 0, None, ago(days=6))
    # background activity so lookups are not trivial
    for n in range(1, 37):
        acc = f"ACC-{n:04d}"
        if not conn.execute("SELECT 1 FROM accounts WHERE account_id=?", (acc,)).fetchone():
            continue
        for k in range(3):
            T(f"TXN-9{n:03d}{k:02d}", acc, ("USSD", "POS", "NIP")[k], "debit",
              (k + 1) * 350_000 + n * 1_000, "Fictional Trust Bank" if k == 2 else None,
              ("Airtime", "Supermarket", "Transfer")[k], ("Airtime purchase", "POS purchase", "Transfer")[k],
              None, "successful", 1, 1 if k == 2 else None, 0, None, ago(days=8 + k * 3, hours=n))

    c("INSERT INTO reversals VALUES ('REV-000301','TXN-000301','completed',?,?)", (ago(days=1), ago(days=2)))
    c("INSERT INTO reversals VALUES ('REV-000401','TXN-000401','scheduled',?,NULL)", (ago(days=2),))

    c("INSERT INTO card_authorizations VALUES ('AUTH-0008','CRD-0008','Jumia-like Store (fictional)',2_800_000,'declined','INSUFFICIENT_FUNDS',?)", (ago(hours=4),))
    c("INSERT INTO card_authorizations VALUES ('AUTH-0009','CRD-0009','StreamFlix (fictional)',450_000,'declined','ONLINE_DISABLED',?)", (ago(hours=6),))
    c("INSERT INTO card_authorizations VALUES ('AUTH-0010','CRD-0010','ShopGlobal Online',9_900_000,'declined','FRAUD_RULE',?)", (ago(hours=2),))

    for i in range(3):
        c("INSERT INTO otp_delivery_events VALUES (?,?,?,?,?)",
          (f"OTP-0016-{i}", "CUS-0016", "sms", "dnd_blocked", ago(minutes=10 + i * 7)))
    c("INSERT INTO otp_delivery_events VALUES ('OTP-0001-0','CUS-0001','sms','delivered',?)", (ago(days=3),))

    for row in (
        ("BR-LAG-01", "branch", "ENTIN Ikeja Branch", "Lagos", "Ikeja", "12 Demo Avenue, Ikeja", "Mon-Fri 8am-4pm", "open"),
        ("BR-LAG-02", "branch", "ENTIN Lekki Branch", "Lagos", "Lekki", "5 Sample Road, Lekki Phase 1", "Mon-Fri 8am-4pm, Sat 10am-2pm", "open"),
        ("BR-ABJ-01", "branch", "ENTIN Wuse II Branch", "Abuja", "Wuse", "20 Fictional Crescent, Wuse II", "Mon-Fri 8am-4pm", "open"),
        ("BR-PHC-01", "branch", "ENTIN GRA Branch", "Port Harcourt", "GRA", "9 Placeholder Street, GRA Phase 2", "Mon-Fri 8am-4pm", "open"),
        ("BR-KAN-01", "branch", "ENTIN Kano Main", "Kano", "Nasarawa", "3 Demo Road, Nasarawa GRA", "Mon-Fri 8am-4pm", "open"),
        ("BR-ENU-01", "branch", "ENTIN Enugu Branch", "Enugu", "Independence Layout", "14 Sample Close, Independence Layout", "Mon-Fri 8am-4pm", "open"),
        ("ATM-LAG-014", "atm", "ENTIN ATM Ikeja City Mall (fictional)", "Lagos", "Ikeja", "Ikeja, near Demo Mall", "24 hours", "working"),
        ("ATM-LAG-022", "atm", "ENTIN ATM Yaba", "Lagos", "Yaba", "Herbert Macaulay Way (fictional unit)", "24 hours", "out_of_service"),
        ("ATM-ABJ-003", "atm", "ENTIN ATM Garki", "Abuja", "Garki", "Area 11 (fictional unit)", "24 hours", "working"),
    ):
        c("INSERT INTO branches_atms VALUES (?,?,?,?,?,?,?,?)", row)

    Tk = lambda *r: c("INSERT INTO tickets VALUES (?,?,?,?,?,?,?,?,?,?,NULL)", r)  # noqa: E731
    Tk("TKT-104233", "CUS-0003", "COMPLAINT_GENERAL", None, "in_progress", "P3", iso(now + timedelta(days=9)), "Statement request delayed", "seed", ago(days=5))
    Tk("TKT-104250", "CUS-0004", "REVERSAL_STATUS", "TXN-000401", "in_progress", "P2", ago(days=1), "Reversal not received", "seed", ago(days=15))
    for i in range(3):  # S36: three reports of the same issue within 7 days
        Tk(f"TKT-10430{i}", "CUS-0036", "TRANSFER_DEBITED_NOT_RECEIVED", "TXN-003601", "open", "P3",
           iso(now + timedelta(days=12)), "Transfer not received", "seed", ago(days=5 - i * 2))
    conn.commit()


def fresh(path: str = ":memory:", now: datetime | None = None) -> sqlite3.Connection:
    conn = connect(path)
    seed(conn, now)
    return conn


if __name__ == "__main__":
    target = os.environ.get("ENTIN_DB", "entin.db")
    if os.path.exists(target):
        os.remove(target)
    fresh(target)
    print(f"Seeded synthetic ENTIN database at {target}")
