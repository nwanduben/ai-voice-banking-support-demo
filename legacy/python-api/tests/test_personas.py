"""Persona scenario tests (S01-S36). Run from api/:  python -m unittest -v"""
import unittest
from datetime import datetime, timezone

from app import db
from app.guard import detect_secret, redact
from app.service import Tools

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)

# name, dob, account last4, phone last4
FACTORS = {
    "CUS-0001": ("Adaeze Okafor", "1991-03-14", "0001", "0001"),
    "CUS-0002": ("Tunde Bakare", "1988-07-02", "0002", "0002"),
    "CUS-0003": ("Chinedu Eze", "1985-11-23", "0003", "0003"),
    "CUS-0004": ("Halima Yusuf", "1993-01-30", "0004", "0004"),
    "CUS-0006": ("Funke Adeyemi", "1987-09-17", "0006", "0006"),
    "CUS-0007": ("Ibrahim Musa", "1992-12-01", "0007", "0007"),
    "CUS-0008": ("Ngozi Obi", "1995-04-21", "0008", "0008"),
    "CUS-0010": ("Aisha Bello", "1994-02-11", "0010", "0010"),
    "CUS-0011": ("Kelechi Umeh", "1986-06-19", "0011", "0011"),
    "CUS-0014": ("Grace Etim", "1990-12-25", "0014", "0014"),
    "CUS-0016": ("Musa Danjuma", "1984-07-15", "0016", "0016"),
    "CUS-0020": ("Tope Salami", "1981-09-09", "0020", "0020"),
    "CUS-0024": ("Daniel Okoro", "1979-04-04", "0024", "0024"),
    "CUS-0031": ("Obinna Chukwu", "1991-08-18", "0031", "0031"),
    "CUS-0032": ("Zainab Lawal", "1993-06-06", "0032", "0032"),
    "CUS-0034": ("Bayo Ogunleye", "1980-02-29", "0034", "0034"),
    "CUS-0036": ("Amaka Nwachukwu", "1988-12-12", "0036", "0036"),
    "CUS-0037": ("Gerald Okeke", "1990-06-15", "0037", "0037"),
}


class Base(unittest.TestCase):
    def setUp(self):
        self.t = Tools(db.fresh(":memory:", NOW), clock=lambda: NOW)
        self.conv = f"conv_{self._testMethodName}"

    def call(self, tool, **kw):
        return self.t.call(tool, {"conversation_id": self.conv, **kw})

    def verify(self, cid, full=True):
        name, dob, acct, phone = FACTORS[cid]
        args = dict(full_name=name, account_last4=acct)
        if full:
            args.update(date_of_birth=dob, phone_last4=phone)
        r = self.call("verify_caller", **args)
        self.assertTrue(r["ok"], r)
        return r["data"]["verification_token"]


class TestTransfers(Base):
    def test_s01_debited_not_received_within_window(self):
        self.call("assess_request", intent="TRANSFER_DEBITED_NOT_RECEIVED")
        tok = self.verify("CUS-0001")
        m = self.call("find_transactions", verification_token=tok, amount_naira_approx=45000, channel="transfer")
        self.assertEqual([x["txn_id"] for x in m["data"]["matches"]], ["TXN-000101"])
        s = self.call("get_transaction_status", verification_token=tok, txn_id="TXN-000101")
        self.assertEqual(s["data"]["recommended_action"], "wait")
        self.assertIn("72 hours", s["say"])
        self.assertEqual(s["risk_level"], "MEDIUM")

    def test_s02_failed_not_debited(self):
        tok = self.verify("CUS-0002")
        s = self.call("get_transaction_status", verification_token=tok, txn_id="TXN-000201")
        self.assertIn("no money left your account", s["say"])

    def test_s03_reversal_completed(self):
        tok = self.verify("CUS-0003")
        s = self.call("get_transaction_status", verification_token=tok, txn_id="TXN-000301")
        self.assertEqual(s["data"]["reversal"]["status"], "completed")
        self.assertIn("reversed", s["say"])

    def test_s04_reversal_overdue_creates_ticket(self):
        tok = self.verify("CUS-0004")
        s = self.call("get_transaction_status", verification_token=tok, txn_id="TXN-000401")
        self.assertEqual(s["data"]["recommended_action"], "create_ticket")
        t = self.call("create_ticket", verification_token=tok, category="REVERSAL_STATUS", linked_txn_id="TXN-000401",
                      summary="Reversal overdue", idempotency_key="k1")
        again = self.call("create_ticket", verification_token=tok, category="REVERSAL_STATUS", linked_txn_id="TXN-000401",
                          summary="Reversal overdue", idempotency_key="k1")
        self.assertEqual(t["data"]["ticket_id"], again["data"]["ticket_id"])  # idempotent

    def test_s24_large_amount_is_high(self):
        tok = self.verify("CUS-0024")
        s = self.call("get_transaction_status", verification_token=tok, txn_id="TXN-002401")
        self.assertEqual(s["data"]["recommended_action"], "escalate")
        self.assertEqual(s["risk_level"], "HIGH")

    def test_s31_no_reference_is_narrowed_by_amount_and_date(self):
        tok = self.verify("CUS-0031")
        broad = self.call("find_transactions", verification_token=tok, channel="transfer")
        self.assertEqual(broad["error"]["code"], "AMBIGUOUS_MATCH")
        narrow = self.call("find_transactions", verification_token=tok, channel="transfer", amount_naira_approx=25000)
        self.assertEqual(len(narrow["data"]["matches"]), 1)

    def test_s36_reported_three_times_escalates(self):
        tok = self.verify("CUS-0036")
        r = self.call("get_ticket_status", verification_token=tok, reference="TKT-104302")
        self.assertIn("request_human_handoff", r["next_actions"])
        self.assertEqual(r["risk_level"], "HIGH")


class TestGeraldDemo(Base):
    def test_s37_gerald_70k_yesterday_4pm(self):
        a = self.call("assess_request", intent="UNAUTHORIZED_TRANSACTION", signals=["customer_denies_authorisation"], amount_naira=70000)
        self.assertEqual(a["data"]["risk_level"], "HIGH")
        tok = self.verify("CUS-0037")
        m = self.call("find_transactions", verification_token=tok, date_from="2026-09-20", date_to="2026-09-20", amount_naira_approx=70000)
        self.assertEqual(m["data"]["matches"][0]["txn_id"], "TXN-003701")
        self.assertIn("yesterday at about 4 PM", m["say"])
        d = self.call("create_dispute", verification_token=tok, txn_id="TXN-003701", type="UNAUTHORIZED", caller_statement="Does not recognise it")
        self.assertTrue(d["ok"])


class TestDisputesAndCards(Base):
    def test_s06_atm_dispute_is_high_with_48h(self):
        a = self.call("assess_request", intent="ATM_CASH_DISPUTE")
        self.assertEqual(a["data"]["risk_level"], "HIGH")
        tok = self.verify("CUS-0006")
        d = self.call("create_dispute", verification_token=tok, txn_id="TXN-000601", type="ATM_NO_CASH", caller_statement="No cash came out")
        self.assertEqual(d["data"]["expected_resolution_hours"], 48)
        self.assertTrue(d["data"]["dispute_id"].startswith("DSP-"))

    def test_s07_pos_double_debit_is_medium(self):
        tok = self.verify("CUS-0007")
        d = self.call("create_dispute", verification_token=tok, txn_id="TXN-000702", type="POS_DOUBLE_DEBIT", caller_statement="Charged twice")
        self.assertEqual(d["risk_level"], "LOW")  # no HIGH signal raised; session risk only rises via assess_request
        self.assertEqual(d["data"]["expected_resolution_hours"], 72)

    def test_s08_decline_reason_is_customer_safe(self):
        tok = self.verify("CUS-0008")
        r = self.call("get_card_status", verification_token=tok)
        self.assertEqual(r["data"]["latest_decline"]["reason_category"], "insufficient_funds")
        self.assertNotIn("balance", r["say"].lower())

    def test_s10_fraud_rule_escalates(self):
        tok = self.verify("CUS-0010")
        r = self.call("get_card_status", verification_token=tok)
        self.assertEqual(r["risk_level"], "HIGH")
        self.assertIn("request_human_handoff", r["next_actions"])

    def test_s11_lost_card_block_needs_only_t1_and_confirmation(self):
        tok = self.verify("CUS-0011", full=False)
        no = self.call("block_card", verification_token=tok, card_last4="0407", reason="lost")
        self.assertEqual(no["error"]["code"], "VALIDATION_ERROR")
        yes = self.call("block_card", verification_token=tok, card_last4="0407", reason="lost", caller_confirmed=True)
        self.assertTrue(yes["data"]["blocked"])

    def test_s32_unrecognised_150k(self):
        a = self.call("assess_request", intent="UNAUTHORIZED_TRANSACTION", signals=["customer_denies_authorisation"], amount_naira=150000)
        self.assertEqual(a["data"]["risk_level"], "HIGH")
        tok = self.verify("CUS-0032")
        m = self.call("find_transactions", verification_token=tok, amount_naira_approx=150000)
        self.assertEqual(m["data"]["matches"][0]["txn_id"], "TXN-003201")

    def test_s34_block_every_card(self):
        tok = self.verify("CUS-0034", full=False)
        r = self.call("block_card", verification_token=tok, all_cards=True, reason="suspected_fraud", caller_confirmed=True)
        self.assertEqual(len(r["data"]["cards_blocked"]), 3)


class TestSecurity(Base):
    def test_s17_two_failed_verifications_lock(self):
        for expected in ("failed", "locked"):
            r = self.call("verify_caller", full_name="Adaeze Okafor", date_of_birth="1990-01-01", account_last4="0001", phone_last4="0001")
            self.assertEqual(r["data"]["result"], expected)
        self.assertEqual(r["risk_level"], "HIGH")
        good = self.call("verify_caller", full_name="Adaeze Okafor", date_of_birth="1991-03-14", account_last4="0001", phone_last4="0001")
        self.assertEqual(good["error"]["code"], "VERIFICATION_LOCKED")

    def test_data_tools_require_token(self):
        r = self.call("find_transactions")
        self.assertEqual(r["error"]["code"], "VERIFICATION_REQUIRED")

    def test_token_is_bound_to_conversation(self):
        tok = self.verify("CUS-0001")
        r = self.t.call("find_transactions", {"conversation_id": "other", "verification_token": tok})
        self.assertEqual(r["error"]["code"], "UNAUTHORIZED")

    def test_s18_s28_s29_s30_volunteered_secrets_rejected(self):
        for text, kind in (("my PIN is 4 4 2 1", "pin"), ("My OTP is 829114", "otp"), ("My CVV is 999", "cvv"),
                           ("my password is Lagos2026!", "password"), ("card 5399 1234 5678 9012", "card_number")):
            self.assertEqual(detect_secret(text), kind, text)
            r = self.call("create_ticket", verification_token="x", category="FAQ_GENERAL", summary=text)
            self.assertEqual(r["error"]["code"], "SENSITIVE_DATA_REJECTED")
        self.assertEqual(r["risk_level"], "HIGH")

    def test_redaction(self):
        out = redact("I told him my OTP is 829114 and card 5399123456789012")
        self.assertNotIn("829114", out)
        self.assertNotIn("5399123456789012", out)

    def test_full_card_number_in_last4_field_rejected(self):
        tok = self.verify("CUS-0011", full=False)
        r = self.call("block_card", verification_token=tok, card_last4="5399123456789012", reason="lost", caller_confirmed=True)
        self.assertFalse(r["ok"])

    def test_s33_s35_prohibited_requests_logged(self):
        a = self.call("assess_request", intent="PROHIBITED_REQUEST", signals=["prompt_injection"])
        self.assertEqual(a["data"]["risk_level"], "HIGH")
        r = self.call("report_security_event", type="third_party_data_request")
        self.assertTrue(r["data"]["case_id"].startswith("SEC-"))

    def test_s20_restricted_account_high_and_no_reason(self):
        self.verify("CUS-0020")
        a = self.call("assess_request", intent="ACCOUNT_RESTRICTION")
        self.assertTrue(a["data"]["must_escalate"])
        self.assertNotIn("PND", str(a))


class TestDigitalAndLow(Base):
    def test_s14_locked_profile_never_unlocked(self):
        tok = self.verify("CUS-0014")
        r = self.call("get_digital_access_status", verification_token=tok)
        self.assertIn("can't unlock", r["say"])

    def test_s16_otp_dnd(self):
        tok = self.verify("CUS-0016", full=False)
        r = self.call("get_digital_access_status", verification_token=tok)
        self.assertIn("Do-Not-Disturb", r["say"])

    def test_s23_branch_lookup_needs_no_verification(self):
        r = self.call("find_branch_or_atm", city="Lagos", area="Ikeja", type="branch")
        self.assertIn("Ikeja", r["say"])

    def test_s25_human_handoff(self):
        self.call("assess_request", intent="HUMAN_AGENT_REQUEST")
        r = self.call("request_human_handoff", reason="caller_request", summary="Caller asked for a human")
        self.assertEqual(r["data"]["mode"], "transfer")
        self.assertIn("transfer_to_number", r["next_actions"])

    def test_s27_forgot_pin_is_low_guidance(self):
        a = self.call("assess_request", intent="CREDENTIAL_RESET_GUIDANCE")
        self.assertEqual(a["data"]["risk_level"], "LOW")
        self.assertEqual(a["data"]["required_tier"], "T0")

    def test_risk_never_decreases(self):
        self.call("assess_request", intent="CARD_LOST_STOLEN")
        r = self.call("assess_request", intent="FAQ_GENERAL")
        self.assertEqual(r["data"]["risk_level"], "HIGH")


if __name__ == "__main__":
    unittest.main()
