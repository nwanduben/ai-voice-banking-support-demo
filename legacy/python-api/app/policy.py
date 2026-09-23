"""Intent taxonomy, risk model and CBN-based policy windows (single source of truth)."""

LEVELS = ["LOW", "MEDIUM", "HIGH"]

# intent -> (base risk, required tier, escalation queue)
INTENTS = {
    "FAQ_GENERAL": ("LOW", "T0", "general"),
    "BRANCH_SERVICE_INFO": ("LOW", "T0", "general"),
    "TRANSFER_FAILED": ("MEDIUM", "T2", "general"),
    "TRANSFER_DEBITED_NOT_RECEIVED": ("MEDIUM", "T2", "general"),
    "TRANSACTION_PENDING": ("MEDIUM", "T2", "general"),
    "REVERSAL_STATUS": ("MEDIUM", "T2", "complaints"),
    "UNAUTHORIZED_TRANSACTION": ("HIGH", "T1", "fraud"),
    "ATM_CASH_DISPUTE": ("HIGH", "T2", "disputes"),          # user decision 2026-09-21
    "POS_DISPUTE": ("MEDIUM", "T2", "disputes"),
    "CARD_DECLINED": ("MEDIUM", "T2", "cards"),
    "CARD_LOST_STOLEN": ("HIGH", "T1", "fraud"),
    "MOBILE_LOGIN_ISSUE": ("MEDIUM", "T1", "digital"),
    "DIGITAL_PROFILE_LOCKED": ("MEDIUM", "T2", "digital"),
    "CREDENTIAL_RESET_GUIDANCE": ("LOW", "T0", "digital"),   # forgot PIN / password: guidance only
    "OTP_NOT_RECEIVED": ("MEDIUM", "T1", "digital"),
    "COMPLAINT_TICKET_STATUS": ("MEDIUM", "T1", "complaints"),
    "ACCOUNT_RESTRICTION": ("HIGH", "T2", "compliance"),
    "SUSPECTED_FRAUD_SCAM": ("HIGH", "T1", "fraud"),
    "HUMAN_AGENT_REQUEST": ("LOW", "T0", "general"),
    "SENSITIVE_INFO_DISCLOSED": ("HIGH", "T0", "fraud"),
    "VERIFICATION_FAILED": ("HIGH", "T0", "fraud"),
    "PROHIBITED_REQUEST": ("HIGH", "T0", "fraud"),           # other people's data, "tell me the PIN", prompt injection
    "OUT_OF_SCOPE_OR_UNCLEAR": ("LOW", "T0", "general"),
}

HIGH_SIGNALS = {"customer_denies_authorisation", "social_engineering_suspected",
                "vulnerable_customer", "repeat_contact", "prompt_injection"}

HIGH_AMOUNT_KOBO = 100_000_000  # N1,000,000 (fictional ENTIN threshold)
REPEAT_CONTACT_THRESHOLD = 3    # same issue, 7 days

TOOLS_BY_TIER = {
    "T0": ["assess_request", "verify_caller", "report_security_event", "request_human_handoff", "find_branch_or_atm"],
    "T1": ["block_card", "get_digital_access_status", "create_ticket", "get_ticket_status"],
    "T2": ["find_transactions", "get_transaction_status", "get_card_status", "create_dispute"],
}

# CBN timelines for failed e-transactions, effective 8 June 2020.
# Source: CBN circular as reported by Nairametrics, 2020-05-31
# https://nairametrics.com/2020/05/31/just-in-cbn-revises-timelines-for-resolution-of-dispense-errors-refund-complaints/
WINDOW_HOURS = {
    "ATM_ON_US": 0,        # instant reversal
    "ATM_NOT_ON_US": 48,
    "POS": 72,
    "NIP": 72,             # failed online transfers
    "WEB": 72,
    "USSD": 72,
    "INTRA": 72,
}
# Complaint resolution: two weeks (CBN Consumer Protection Regulations 2019 / help-desk circular).
COMPLAINT_SLA_DAYS = 14


def max_level(*levels: str) -> str:
    return max(levels, key=LEVELS.index)


def tier_ok(have: str, need: str) -> bool:
    return int(have[1]) >= int(need[1])


def allowed_tools(tier: str) -> list[str]:
    return [t for k, tools in TOOLS_BY_TIER.items() if tier_ok(tier, k) for t in tools]
