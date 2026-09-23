# ENTIN Bank — AI Voice Customer Support (Synthetic Demo)

A voice agent for a **fictional Nigerian bank** with 500 existing customers. It handles:
- failed, pending and not-received transfers, and reversals
- ATM and POS disputes, declined cards, lost cards and fraud
- login and OTP problems, complaints, and requests for a human

It never asks for a PIN, OTP, password, CVV or card number.

> Fully synthetic. There is no real bank, API, account, payment or customer data. Account numbers use a fake `99…` range, phones a fake `+234 700 001…` range, and banks and merchants are invented. Customer SMS is never sent.

```
Caller ── ElevenLabs agent (voice, prompt, knowledge base, 13 tools)
              │  tool call during the call:  POST /webhook/entin/find_transactions  (13 webhooks, one per tool)
              ▼
          n8n "1 - Live call tools"  ── reads / writes ──►  Google Sheet = the bank
              │                                             Customers · Accounts · Cards · Transactions
              │                                             Tickets · Disputes · Security Cases · Escalations
              │                                             Sessions · Call Log · …
              ▼
          reply spoken to the caller; every step logged in "Call Log"

n8n "3 - Bank activity"   every 5 min: salaries, POS, transfers, occasional failed transfer / ATM error
n8n "2 - Post-call"       ElevenLabs post-call webhook (HMAC) → redacted summary into Sessions, QA email
n8n "4 - Daily digest"    08:00 WAT email
n8n "5 - Reset demo"      run before a demo
```

## Safety rules, enforced inside n8n (not just in the prompt)
- **Identity levels.** These are checked against the Customers and Accounts tabs:
  - Anonymous callers get knowledge-base answers only.
  - Name plus last-4 digits can block a card or check a ticket.
  - Name, date of birth, account last-4 and phone last-4 together unlock transaction details.
  - Two failed attempts lock the call.
  - Verification lasts 15 minutes and belongs to one conversation.
- **Secret guard.** The **Which Step?** node rejects any request containing a PIN, OTP, CVV, password or card number. It opens a Security Case, and the secret is never written to the sheet.
- **Risk levels.** Every request is LOW, MEDIUM or HIGH. Risk goes up for things like a denied payment, ₦1m or more, a repeat complaint, a restricted account or failed verification, and it never goes down during a call. HIGH always ends with a human.
- **CBN timelines, with sources.** ENTIN's own ATMs: instant. Another bank's ATM: 48 hours. POS: 72 hours. Failed transfers: 72 hours. Complaints: 14 days.

## Layout
| Path | What |
|---|---|
| `data/` | `generate_bank.py`, which produces `entin-bank.xlsx` (import into Google Sheets) plus `csv/` |
| `n8n/` | The 5 importable workflows, `build_workflows.py`, Code-node logic in `src/`, tests in `test/` |
| `agent/` | ElevenLabs prompt, first message, tools, knowledge base, evaluation, **`SETUP.md`** |
| `docs/` | Kickoff brief and design specs |
| `legacy/` | The first version (Python API with 29 tests), kept as a reference |

## Verified
- `node n8n/test/run_tests.mjs`: 31 end-to-end scenarios pass. They run the exported workflow JSON against the 500-customer data, including:
  - Gerald's full call and the secret-rejection cases
  - the lock after two failed verifications
  - blocking every card
  - the three background workflows and the demo reset
- Deliberately breaking a rule makes the tests fail. Letting unverified callers see transactions, or switching off OTP detection, were both caught.
- All 5 workflows pass n8n-mcp validation with 0 errors. The Code-node contents were replaced with stubs for that check; the tests above run the real code.

## Not yet verified
- Importing into your n8n and running against a real Google Sheet: check Google Sheets API speed during live calls.
- Live ElevenLabs calls, and voice quality in Yoruba, Hausa, Igbo and Pidgin.

Start with [agent/SETUP.md](agent/SETUP.md).
