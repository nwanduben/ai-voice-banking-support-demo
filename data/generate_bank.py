"""Generate the synthetic ENTIN Bank database (500 customers) as Google-Sheets-ready tabs.

    python data/generate_bank.py            -> data/csv/*.csv  (+ data/entin-bank.xlsx if openpyxl is installed)

Import entin-bank.xlsx into Google Sheets (File > Import > Replace spreadsheet) to get every tab at once.
Everything is fictional: 99xxxxxxxx account numbers fail NUBAN validation, phones use +234 700 001 xxxx,
banks and merchants are invented. No PIN, OTP, password, CVV or full card number exists anywhere.
Deterministic: the same seed always produces the same customers, accounts and IDs.
"""
import csv
import pathlib
import random
from datetime import datetime, timedelta, timezone

WAT = timezone(timedelta(hours=1))
OUT = pathlib.Path(__file__).parent
rng = random.Random(2026)
NOW = datetime.now(WAT).replace(second=0, microsecond=0)


def ts(dt: datetime) -> str:
    return dt.astimezone(WAT).strftime("%Y-%m-%d %H:%M")


FIRST = {
    "yoruba": ["Adebayo", "Funke", "Tunde", "Yemisi", "Segun", "Bisola", "Kunle", "Ronke", "Femi", "Titilayo", "Dayo", "Bukola", "Tope", "Kemi", "Wale", "Folake", "Seun", "Lola"],
    "igbo": ["Chinedu", "Adaeze", "Emeka", "Ngozi", "Obinna", "Chiamaka", "Ifeanyi", "Nkechi", "Uche", "Amaka", "Kelechi", "Chioma", "Ikenna", "Ebere", "Nnamdi", "Ogechi"],
    "hausa": ["Ibrahim", "Aisha", "Musa", "Halima", "Abubakar", "Zainab", "Usman", "Hauwa", "Sani", "Fatima", "Aminu", "Maryam", "Bello", "Hadiza", "Yusuf", "Rukayya"],
    "other": ["Grace", "Daniel", "Joy", "Gerald", "Esther", "Victor", "Blessing", "Samuel", "Patience", "Emmanuel", "Mercy", "Godwin", "Precious", "Efe", "Ese", "Idara"],
}
LAST = {
    "yoruba": ["Adeyemi", "Bakare", "Ogunleye", "Adebayo", "Oladipo", "Salami", "Ogunbiyi", "Akinola", "Adewale", "Olatunji", "Fashola", "Oyelaran"],
    "igbo": ["Okafor", "Eze", "Nwosu", "Okonkwo", "Umeh", "Chukwu", "Nwachukwu", "Obi", "Okeke", "Nnaji", "Onyekachi", "Ibe"],
    "hausa": ["Musa", "Yusuf", "Bello", "Lawal", "Danjuma", "Abdullahi", "Garba", "Aliyu", "Sule", "Umar", "Idris", "Shehu"],
    "other": ["Etim", "Okoro", "Edet", "Ekanem", "Akpan", "Ogbeide", "Omoregie", "Ikpe", "Efiong", "Otu", "Bassey", "Oghene"],
}
PLACES = [("Lagos", "Ikeja"), ("Lagos", "Lekki"), ("Lagos", "Yaba"), ("Lagos", "Surulere"), ("FCT", "Wuse"), ("FCT", "Garki"),
          ("Rivers", "Port Harcourt"), ("Oyo", "Ibadan"), ("Kano", "Kano"), ("Enugu", "Enugu"), ("Kaduna", "Kaduna"), ("Edo", "Benin City")]
BANKS = ["Fictional Trust Bank", "Sample Savings Bank", "Demo Microfinance Bank", "Quick Fictional Bank", "Placeholder Bank"]
MERCHANTS = ["Mama Put Kitchen", "ShopRite-like Store (fictional)", "Filling Station (fictional)", "Pharmacy Plus (fictional)",
             "Market Stall POS", "Lekki Luxury Stores", "QuickBuy Online (fictional)", "StreamFlix (fictional)", "Bolt-like Rides (fictional)"]
EMPLOYERS = ["Demo Oil Services Ltd", "Sample Tech Hub", "Fictional State Ministry", "Placeholder Schools", "Mock Logistics Ltd"]

# Scenario personas keep fixed IDs and details so the demo scripts always work.
# (num, name, dob, scenario)
PERSONAS = [
    (1, "Adaeze Okafor", "1991-03-14", "S01 transfer debited, recipient not credited (within 72h)"),
    (2, "Tunde Bakare", "1988-07-02", "S02 transfer failed, not debited"),
    (3, "Chinedu Eze", "1985-11-23", "S03 reversal completed; has open ticket TKT-104233"),
    (4, "Halima Yusuf", "1993-01-30", "S04 reversal overdue; ticket TKT-104250 past SLA"),
    (5, "Emeka Nwosu", "1990-05-09", "S05 transfer pending 20 minutes"),
    (6, "Funke Adeyemi", "1987-09-17", "S06 ATM (other bank) debited, no cash"),
    (7, "Ibrahim Musa", "1992-12-01", "S07 POS double debit"),
    (8, "Ngozi Obi", "1995-04-21", "S08 card declined: insufficient funds"),
    (9, "Segun Ade", "1989-08-08", "S09 card declined: online payments off"),
    (10, "Aisha Bello", "1994-02-11", "S10 card on fraud hold"),
    (11, "Kelechi Umeh", "1986-06-19", "S11 lost card"),
    (12, "Ronke Adebayo", "1983-10-05", "S12 three unrecognised web debits at 2am"),
    (13, "Uche Okonkwo", "1996-03-03", "S13 new phone, device not linked"),
    (14, "Grace Etim", "1990-12-25", "S14 mobile profile locked"),
    (16, "Musa Danjuma", "1984-07-15", "S16 OTP blocked by DND"),
    (18, "Femi Ogun", "1982-01-27", "S18 volunteers PIN"),
    (19, "Joy Nnaji", "1997-05-30", "S19 scammed, shared OTP, N80,000 left"),
    (20, "Tope Salami", "1981-09-09", "S20 account restricted"),
    (24, "Daniel Okoro", "1979-04-04", "S24 N2,500,000 transfer not received"),
    (25, "Kemi Oladipo", "1992-10-10", "S25 wants a human"),
    (31, "Obinna Chukwu", "1991-08-18", "S31 no reference, several similar transfers"),
    (32, "Zainab Lawal", "1993-06-06", "S32 does not recognise N150,000"),
    (34, "Bayo Ogunleye", "1980-02-29", "S34 block every card (3 cards)"),
    (36, "Amaka Nwachukwu", "1988-12-12", "S36 reported the same issue three times"),
    (37, "Gerald Okeke", "1990-06-15", "S37 DEMO: N70,000 deducted yesterday ~4pm, doesn't know why"),
]
PERSONA_BY_NUM = {p[0]: p for p in PERSONAS}

tabs: dict[str, list[dict]] = {k: [] for k in [
    "Customers", "Accounts", "Cards", "Transactions", "Digital Access", "Tickets", "Disputes", "Security Cases",
    "Sessions", "Escalations", "Call Log", "Branches & ATMs", "Demo Scenarios", "Test Callers"]}
HEADERS = {
    "Customers": ["customer_id", "full_name", "date_of_birth", "phone", "phone_last4", "email", "state", "city", "segment", "customer_since", "scenario"],
    "Accounts": ["account_number", "customer_id", "account_type", "status", "balance_naira", "opened_on", "home_branch"],
    "Cards": ["card_id", "customer_id", "account_number", "scheme", "card_last4", "status", "online_enabled", "daily_limit_naira",
              "blocked_at", "block_reason", "last_decline_reason", "last_decline_at", "last_decline_merchant"],
    "Transactions": ["txn_id", "customer_id", "account_number", "date_time", "channel", "direction", "amount_naira", "counterparty",
                     "counterparty_bank", "narration", "status", "debited", "beneficiary_credited", "on_us", "reversal_status",
                     "reversal_due", "reversal_completed_at", "reference", "balance_after"],
    "Digital Access": ["customer_id", "app_status", "failed_logins", "device_linked", "otp_channel", "otp_last_status", "otp_last_attempt"],
    "Tickets": ["ticket_id", "customer_id", "category", "linked_txn_id", "status", "priority", "created_at", "sla_due", "summary", "created_by"],
    "Disputes": ["dispute_id", "ticket_id", "customer_id", "txn_id", "type", "status", "created_at", "expected_resolution"],
    "Security Cases": ["case_id", "conversation_id", "customer_id", "type", "secret_kind", "created_at"],
    "Sessions": ["conversation_id", "customer_id", "customer_name", "tier", "verified_at", "failed_attempts", "locked", "max_risk",
                 "intents", "updated_at", "call_summary", "secret_detected", "failed_evaluations"],
    "Escalations": ["handoff_id", "conversation_id", "customer_id", "queue", "priority", "risk_level", "reason", "summary", "mode", "status", "created_at"],
    "Call Log": ["timestamp", "conversation_id", "group", "step", "caller_details", "result", "agent_says", "risk_level", "next_actions"],
    "Branches & ATMs": ["location_id", "type", "name", "city", "area", "address", "hours", "status"],
    "Demo Scenarios": ["tab", "id_column", "id", "field", "offset_minutes", "value", "note"],
    "Test Callers": ["scenario", "full_name", "date_of_birth", "account_last4", "phone_last4", "what_to_say"],
}


def acct_number() -> str:
    return "99" + "".join(str(rng.randint(0, 9)) for _ in range(8))


def demo(tab, id_col, id_, field, offset=None, value="", note=""):
    tabs["Demo Scenarios"].append({"tab": tab, "id_column": id_col, "id": id_, "field": field,
                                   "offset_minutes": "" if offset is None else offset, "value": value, "note": note})


# ---------- customers, accounts, cards, digital access ----------
used_names, used_accts, used_last4 = set(), set(), set()
acct_of: dict[int, list[str]] = {}
for num in range(1, 501):
    cid = f"CUS-{num:04d}"
    if num in PERSONA_BY_NUM:
        _, name, dob, scenario = PERSONA_BY_NUM[num]
    else:
        group = rng.choice(list(FIRST))
        while True:
            name = f"{rng.choice(FIRST[group])} {rng.choice(LAST[rng.choice([group, group, 'other'])])}"
            if name not in used_names and all(name != p[1] for p in PERSONAS):
                break
        dob = f"{rng.randint(1962, 2004)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
        scenario = ""
    used_names.add(name)
    state, city = rng.choice(PLACES)
    phone = f"+234700001{num:04d}"
    first, last = name.lower().split()[0], name.lower().split()[-1]
    tabs["Customers"].append({"customer_id": cid, "full_name": name, "date_of_birth": dob, "phone": phone, "phone_last4": phone[-4:],
                              "email": f"{first}.{last}{num}@example.com", "state": state, "city": city,
                              "segment": "SME" if rng.random() < 0.12 else "Retail",
                              "customer_since": f"{rng.randint(2012, 2025)}-{rng.randint(1, 12):02d}-01", "scenario": scenario})
    n_accts = 2 if (num == 34 or (num not in PERSONA_BY_NUM and rng.random() < 0.15)) else 1
    acct_of[num] = []
    for a in range(n_accts):
        while True:
            an = acct_number()
            if an not in used_accts and an[-4:] not in used_last4:
                break
        used_accts.add(an); used_last4.add(an[-4:])
        acct_of[num].append(an)
        status = {10: "fraud_hold", 20: "restricted"}.get(num, "dormant" if num not in PERSONA_BY_NUM and rng.random() < 0.03 else "active")
        tabs["Accounts"].append({"account_number": an, "customer_id": cid, "account_type": "Savings" if a == 0 else "Current",
                                 "status": status, "balance_naira": 0, "opened_on": f"{rng.randint(2012, 2025)}-{rng.randint(1, 12):02d}-15",
                                 "home_branch": f"ENTIN {city}"})
    n_cards = 3 if num == 34 else 1
    for k in range(n_cards):
        an = acct_of[num][min(k, len(acct_of[num]) - 1)]
        tabs["Cards"].append({"card_id": f"CRD-{num:04d}-{k + 1}", "customer_id": cid, "account_number": an,
                              "scheme": rng.choice(["Verve", "Mastercard", "Visa"]), "card_last4": f"{rng.randint(0, 9999):04d}",
                              "status": "blocked_fraud" if num == 10 else "active",
                              "online_enabled": "no" if num == 9 else "yes", "daily_limit_naira": rng.choice([100000, 200000, 500000]),
                              "blocked_at": "", "block_reason": "", "last_decline_reason": "", "last_decline_at": "", "last_decline_merchant": ""})
    tabs["Digital Access"].append({"customer_id": cid, "app_status": "locked" if num == 14 else "active",
                                   "failed_logins": 5 if num == 14 else 0, "device_linked": "no" if num == 13 else "yes",
                                   "otp_channel": "sms", "otp_last_status": "dnd_blocked" if num == 16 else "delivered",
                                   "otp_last_attempt": ts(NOW - timedelta(minutes=12 if num == 16 else rng.randint(600, 40000)))})

card_by_num = {int(c["customer_id"][4:]): c for c in reversed(tabs["Cards"])}  # first card per customer
for num, reason, merchant, mins in ((8, "insufficient_funds", "Jumia-like Store (fictional)", 240),
                                   (9, "online_disabled", "StreamFlix (fictional)", 360),
                                   (10, "needs_review", "ShopGlobal Online (fictional)", 120)):
    c = card_by_num[num]
    c.update(last_decline_reason=reason, last_decline_merchant=merchant, last_decline_at=ts(NOW - timedelta(minutes=mins)))
    demo("Cards", "card_id", c["card_id"], "last_decline_at", mins, note=f"S{num:02d} decline time")
for c in tabs["Cards"]:  # demo reset: every scenario card back to its seeded status
    num = int(c["customer_id"][4:])
    if num in PERSONA_BY_NUM:
        demo("Cards", "card_id", c["card_id"], "status", None, c["status"], "reset card status")
demo("Digital Access", "customer_id", "CUS-0016", "otp_last_attempt", 12, note="S16 OTP attempt")

# ---------- transactions ----------
txn_counter = 0


def txn(num, when, channel, direction, amount, counterparty="", bank="", narration="", status="successful", debited="yes",
        credited="", on_us="", rev_status="", rev_due="", rev_done="", txn_id=None, offset=None):
    global txn_counter
    txn_counter += 1
    tid = txn_id or f"TXN-{txn_counter:06d}"
    row = {"txn_id": tid, "customer_id": f"CUS-{num:04d}", "account_number": acct_of[num][0], "date_time": ts(when), "channel": channel,
           "direction": direction, "amount_naira": amount, "counterparty": counterparty, "counterparty_bank": bank,
           "narration": narration, "status": status, "debited": debited if direction == "debit" else "", "beneficiary_credited": credited,
           "on_us": on_us, "reversal_status": rev_status, "reversal_due": rev_due, "reversal_completed_at": rev_done,
           "reference": f"ENT{rng.randint(10**11, 10**12 - 1)}", "balance_after": ""}
    tabs["Transactions"].append(row)
    if offset is not None:
        demo("Transactions", "txn_id", tid, "date_time", offset, note=f"{tid} time")
    return row


def masked(name):
    first, last = name.split()[0], name.split()[-1]
    return f"{first} {last[0]}{'*' * (len(last) - 2)}{last[-1]}"


for num in range(1, 501):
    start = NOW - timedelta(days=60)
    salary = rng.choice([85000, 120000, 180000, 250000, 400000, 650000])
    for m in range(3):  # salaries
        d = (start + timedelta(days=5 + 30 * m)).replace(hour=9, minute=rng.randint(0, 59))
        if d < NOW - timedelta(days=2):
            txn(num, d, "TRANSFER", "credit", salary, rng.choice(EMPLOYERS), rng.choice(BANKS), "Salary", credited="yes")
    for _ in range(rng.randint(8, 13)):
        d = start + timedelta(days=rng.uniform(0, 57), hours=rng.uniform(7, 21))
        kind = rng.choices(["pos", "transfer", "airtime", "atm", "web"], [35, 25, 15, 15, 10])[0]
        if kind == "pos":
            txn(num, d, "POS", "debit", rng.choice([1500, 3500, 7800, 12500, 22000, 45000]), rng.choice(MERCHANTS), "", "POS purchase")
        elif kind == "transfer":
            other = f"{rng.choice(sum(FIRST.values(), []))} {rng.choice(sum(LAST.values(), []))}"
            txn(num, d, "TRANSFER", "debit", rng.choice([5000, 10000, 20000, 35000, 50000, 100000]), masked(other), rng.choice(BANKS),
                "Transfer", credited="yes")
        elif kind == "airtime":
            txn(num, d, "USSD", "debit", rng.choice([500, 1000, 2000, 5000]), "Airtime (fictional network)", "", "Airtime purchase")
        elif kind == "atm":
            on_us = rng.random() < 0.5
            txn(num, d, "ATM", "debit", rng.choice([10000, 20000, 40000]), "ENTIN ATM" if on_us else "Other bank ATM", "", "ATM withdrawal",
                on_us="yes" if on_us else "no")
        else:
            txn(num, d, "WEB", "debit", rng.choice([2500, 4500, 9900, 15000]), rng.choice(MERCHANTS[5:]), "", "Online card payment")

M = lambda **kw: NOW - timedelta(**kw)  # noqa: E731
mins = lambda **kw: int(timedelta(**kw).total_seconds() // 60)  # noqa: E731
# S01 Adaeze: debited, not credited, pending (20h ago)
txn(1, M(hours=20), "TRANSFER", "debit", 45000, "Chioma O***r", "Fictional Trust Bank", "Transfer to Chioma", status="pending", credited="no", txn_id="TXN-S01", offset=mins(hours=20))
# S02 Tunde: failed, not debited
txn(2, M(hours=3), "TRANSFER", "debit", 12000, "Kunle B****e", "Demo Microfinance Bank", "Rent part", status="failed", debited="no", credited="no", txn_id="TXN-S02", offset=mins(hours=3))
# S03 Chinedu: reversed 2 days ago
txn(3, M(days=4), "TRANSFER", "debit", 30000, "Ifeoma E*e", "Fictional Trust Bank", "School fees", status="reversed", credited="no",
    rev_status="completed", rev_done=ts(M(days=2)), txn_id="TXN-S03", offset=mins(days=4))
demo("Transactions", "txn_id", "TXN-S03", "reversal_completed_at", mins(days=2))
# S04 Halima: reversal overdue
txn(4, M(days=5), "TRANSFER", "debit", 60000, "Aminu Y***f", "Sample Savings Bank", "Family support", status="reversal_pending", credited="no",
    rev_status="scheduled", rev_due=ts(M(days=2)), txn_id="TXN-S04", offset=mins(days=5))
demo("Transactions", "txn_id", "TXN-S04", "reversal_due", mins(days=2))
# S05 Emeka: pending 20 min
txn(5, M(minutes=20), "TRANSFER", "debit", 15000, "Obi N***u", "Fictional Trust Bank", "Transfer", status="pending", credited="", txn_id="TXN-S05", offset=20)
# S06 Funke: ATM not-on-us, no cash
txn(6, M(hours=30), "ATM", "debit", 20000, "Other bank ATM (Sample Savings Bank)", "", "ATM withdrawal - no cash dispensed", on_us="no", txn_id="TXN-S06", offset=mins(hours=30))
# S07 Ibrahim: POS double debit
txn(7, M(days=1, hours=2), "POS", "debit", 12500, "Mama Put Kitchen Ikeja", "", "POS purchase", txn_id="TXN-S07A", offset=mins(days=1, hours=2))
txn(7, M(days=1, hours=2) + timedelta(minutes=1), "POS", "debit", 12500, "Mama Put Kitchen Ikeja", "", "POS purchase", txn_id="TXN-S07B", offset=mins(days=1, hours=2) - 1)
# S12 Ronke: 3 web debits at night
for i in range(3):
    txn(12, M(hours=9) + timedelta(minutes=4 * i), "WEB", "debit", 49500, "ShopGlobal Online (fictional)", "", "Online card payment", txn_id=f"TXN-S12{'ABC'[i]}", offset=mins(hours=9) - 4 * i)
# S19 Joy: sent N80,000 to scammer
txn(19, M(hours=5), "TRANSFER", "debit", 80000, "Unknown R*******t", "Quick Fictional Bank", "Refund processing", credited="yes", txn_id="TXN-S19", offset=mins(hours=5))
# S24 Daniel: N2.5m pending
txn(24, M(hours=26), "TRANSFER", "debit", 2500000, "Okoro Holdings L**", "Fictional Trust Bank", "Supplier payment", status="pending", credited="no", txn_id="TXN-S24", offset=mins(hours=26))
# S31 Obinna: similar transfers
for i, (amt, days) in enumerate(((20000, 1), (20000, 2), (25000, 2), (20000, 3))):
    txn(31, M(days=days, hours=i), "TRANSFER", "debit", amt, "Nneka C****u", "Fictional Trust Bank", "Upkeep", credited="yes", txn_id=f"TXN-S31{'ABCD'[i]}", offset=mins(days=days, hours=i))
# S32 Zainab: N150,000 POS not recognised
txn(32, M(days=2), "POS", "debit", 150000, "Lekki Luxury Stores", "", "POS purchase", txn_id="TXN-S32", offset=mins(days=2))
# S36 Amaka: transfer pending 6 days, reported 3 times
txn(36, M(days=6), "TRANSFER", "debit", 35000, "Uju N********u", "Sample Savings Bank", "Transfer", status="pending", credited="no", txn_id="TXN-S36", offset=mins(days=6))
# S37 Gerald (DEMO): N70,000 online card payment yesterday 16:05
g_when = (NOW - timedelta(days=1)).replace(hour=16, minute=5)
txn(37, g_when, "WEB", "debit", 70000, "QuickBuy Online (fictional)", "", "Online card payment", txn_id="TXN-S37", offset=int((NOW - g_when).total_seconds() // 60))

# balances: walk each account chronologically from an opening balance
tabs["Transactions"].sort(key=lambda r: r["date_time"])
bal = {a["account_number"]: rng.choice([35000, 80000, 150000, 400000, 900000, 2500000]) for a in tabs["Accounts"]}
bal[acct_of[8][0]] = 6200  # S08 low balance
for r in tabs["Transactions"]:
    a = r["account_number"]
    if r["direction"] == "credit" and r["status"] == "successful":
        bal[a] += r["amount_naira"]
    elif r["direction"] == "debit" and r["debited"] == "yes" and r["status"] != "reversed":
        bal[a] -= r["amount_naira"]
        if bal[a] < 0:
            bal[a] += 500000  # top-up so history stays plausible
    r["balance_after"] = bal[a]
for a in tabs["Accounts"]:
    a["balance_naira"] = bal[a["account_number"]]

# ---------- tickets ----------
def ticket(tid, num, cat, txn_id, status, prio, created_min, sla_min, summary):
    tabs["Tickets"].append({"ticket_id": tid, "customer_id": f"CUS-{num:04d}", "category": cat, "linked_txn_id": txn_id, "status": status,
                            "priority": prio, "created_at": ts(NOW - timedelta(minutes=created_min)), "sla_due": ts(NOW - timedelta(minutes=sla_min)),
                            "summary": summary, "created_by": "seed"})
    demo("Tickets", "ticket_id", tid, "created_at", created_min)
    demo("Tickets", "ticket_id", tid, "sla_due", sla_min)


ticket("TKT-104233", 3, "COMPLAINT_GENERAL", "", "in_progress", "P3", mins(days=5), -mins(days=9), "Statement request delayed")
ticket("TKT-104250", 4, "REVERSAL_STATUS", "TXN-S04", "in_progress", "P2", mins(days=15), mins(days=1), "Reversal not received")
for i in range(3):
    ticket(f"TKT-10430{i}", 36, "TRANSFER_DEBITED_NOT_RECEIVED", "TXN-S36", "open", "P3", mins(days=5 - 2 * i), -mins(days=12), "Transfer not received")

# ---------- branches & ATMs ----------
for row in [
    ("BR-LAG-01", "branch", "ENTIN Ikeja Branch", "Lagos", "Ikeja", "12 Demo Avenue, Ikeja", "Mon-Fri 8am-4pm", "open"),
    ("BR-LAG-02", "branch", "ENTIN Lekki Branch", "Lagos", "Lekki", "5 Sample Road, Lekki Phase 1", "Mon-Fri 8am-4pm, Sat 10am-2pm", "open"),
    ("BR-LAG-03", "branch", "ENTIN Yaba Branch", "Lagos", "Yaba", "22 Placeholder Street, Yaba", "Mon-Fri 8am-4pm", "open"),
    ("BR-ABJ-01", "branch", "ENTIN Wuse II Branch", "Abuja", "Wuse", "20 Fictional Crescent, Wuse II", "Mon-Fri 8am-4pm", "open"),
    ("BR-ABJ-02", "branch", "ENTIN Garki Branch", "Abuja", "Garki", "7 Demo Close, Area 11, Garki", "Mon-Fri 8am-4pm", "open"),
    ("BR-PHC-01", "branch", "ENTIN GRA Branch", "Port Harcourt", "GRA", "9 Placeholder Street, GRA Phase 2", "Mon-Fri 8am-4pm", "open"),
    ("BR-IBD-01", "branch", "ENTIN Ring Road Branch", "Ibadan", "Ring Road", "4 Sample Way, Ring Road", "Mon-Fri 8am-4pm", "open"),
    ("BR-KAN-01", "branch", "ENTIN Kano Main", "Kano", "Nasarawa", "3 Demo Road, Nasarawa GRA", "Mon-Fri 8am-4pm", "open"),
    ("BR-ENU-01", "branch", "ENTIN Enugu Branch", "Enugu", "Independence Layout", "14 Sample Close, Independence Layout", "Mon-Fri 8am-4pm", "open"),
    ("BR-KAD-01", "branch", "ENTIN Kaduna Branch", "Kaduna", "Barnawa", "11 Fictional Road, Barnawa", "Mon-Fri 8am-4pm", "open"),
    ("BR-BEN-01", "branch", "ENTIN Benin Branch", "Benin City", "GRA", "2 Demo Avenue, GRA", "Mon-Fri 8am-4pm", "open"),
    ("ATM-LAG-014", "atm", "ENTIN ATM Ikeja City Mall (fictional)", "Lagos", "Ikeja", "Ikeja, near Demo Mall", "24 hours", "working"),
    ("ATM-LAG-022", "atm", "ENTIN ATM Yaba", "Lagos", "Yaba", "Herbert Macaulay Way (fictional unit)", "24 hours", "out_of_service"),
    ("ATM-LAG-031", "atm", "ENTIN ATM Lekki Phase 1", "Lagos", "Lekki", "Admiralty Way (fictional unit)", "24 hours", "working"),
    ("ATM-ABJ-003", "atm", "ENTIN ATM Garki", "Abuja", "Garki", "Area 11 (fictional unit)", "24 hours", "working"),
    ("ATM-PHC-002", "atm", "ENTIN ATM Trans-Amadi", "Port Harcourt", "Trans-Amadi", "Trans-Amadi (fictional unit)", "24 hours", "working"),
]:
    tabs["Branches & ATMs"].append(dict(zip(HEADERS["Branches & ATMs"], row)))

# ---------- test callers (cheat sheet for demos) ----------
cust = {c["customer_id"]: c for c in tabs["Customers"]}
SAY = {1: "I sent 45,000 naira yesterday but my sister hasn't received it.", 2: "My transfer failed, did I lose money?",
       3: "I'm checking if my 30,000 naira reversal has come back.", 4: "My reversal still hasn't come after days!",
       5: "I just sent 15,000 naira and it's showing pending.", 6: "The ATM didn't give me cash but I was debited 20,000.",
       7: "I was charged twice at a POS.", 8: "Why was my card declined?", 9: "My card won't work online.",
       10: "Why was my card declined?", 11: "I lost my card.", 12: "There are three payments at 2am I didn't make.",
       13: "I can't log in on my new phone.", 14: "My app says my profile is locked.", 16: "I'm not getting my OTP.",
       18: "Let me give you my PIN so you can check... it's 4 4 2 1.", 19: "Someone from the bank asked for my OTP and now 80,000 naira is gone.",
       20: "Why is my account restricted?", 24: "I sent 2.5 million naira and it hasn't arrived.", 25: "I want to speak to a human.",
       31: "I don't know the transaction reference, I sent some money this week.", 32: "I don't recognise this 150,000 naira transaction.",
       34: "Block every card on my account.", 36: "I've already reported this three times! Ticket T K T 1 0 4 3 0 2.",
       37: "Good morning, my name is Gerald. 70,000 naira was deducted from my account yesterday and I don't understand why."}
for num, name, dob, scenario in PERSONAS:
    c = cust[f"CUS-{num:04d}"]
    tabs["Test Callers"].append({"scenario": scenario, "full_name": name, "date_of_birth": dob, "account_last4": acct_of[num][0][-4:],
                                 "phone_last4": c["phone_last4"], "what_to_say": SAY.get(num, "")})

# ---------- write ----------
csv_dir = OUT / "csv"
csv_dir.mkdir(exist_ok=True)
for name, rows in tabs.items():
    with open(csv_dir / f"{name.replace(' & ', '-').replace(' ', '-').lower()}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADERS[name])
        w.writeheader()
        w.writerows(rows)
try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook()
    wb.remove(wb.active)
    for name, rows in tabs.items():
        ws = wb.create_sheet(name)
        ws.append(HEADERS[name])
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="1F4E79")
        numeric = {"amount_naira", "balance_naira", "balance_after", "daily_limit_naira", "failed_logins", "failed_attempts", "offset_minutes"}
        for r in rows:
            ws.append([r.get(h, "") for h in HEADERS[name]])
            for h, cell in zip(HEADERS[name], ws[ws.max_row]):
                if h not in numeric:  # keep IDs, last-4 digits, account numbers and dates as text (no "0001" -> 1)
                    cell.value = "" if cell.value is None else str(cell.value)
                    cell.number_format = "@"
        ws.freeze_panes = "A2"
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = min(40, max(10, max(len(str(c.value or "")) for c in col[:200]) + 2))
    wb.save(OUT / "entin-bank.xlsx")
    xlsx = "and entin-bank.xlsx"
except ImportError:
    xlsx = "(install openpyxl for entin-bank.xlsx)"
print(f"Customers {len(tabs['Customers'])}, accounts {len(tabs['Accounts'])}, cards {len(tabs['Cards'])}, "
      f"transactions {len(tabs['Transactions'])}; wrote data/csv/*.csv {xlsx}")
