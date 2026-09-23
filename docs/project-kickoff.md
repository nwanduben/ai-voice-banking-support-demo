# ENTIN Bank — AI Voice Support Demo: Project Kickoff

> **Fictional bank, fully synthetic environment.** No real bank, banking API, payment rail, customer account or customer data is used anywhere in this project.

## 0. Active goal and phase

**Phase:** Discovery / design (no code yet, per user instruction on 2026-09-21).

**Goal (paste into Claude Code as `/goal …`; not active until you run it):**

```
/goal Produce a reviewed design package for the ENTIN Bank synthetic AI voice support demo: docs/project-kickoff.md plus docs/design/{intents-and-risk,data-model,api-contracts,agent-and-workflows}.md that together define every supported intent with a risk level, the verification tiers, the synthetic DB schema with seeded test personas, every ElevenLabs tool contract, the n8n workflows, and a runnable proof check for the first slice. Stop when the docs are internally consistent (every intent maps to a risk, a tool path and at least one seeded test persona) and the open decisions are listed with owners. Do not write application code, create external accounts or deploy anything.
```

**Stopping point:** open decisions in §5 need your answers before implementation starts.

**Evidence labels:** **[user]** you decided it · **[source]** backed by primary docs (linked) · **[hyp]** my recommendation or hypothesis, not validated yet.

---

## 1. Six Ps

| P | Decision | Status |
|---|---|---|
| **Pain** | Nigerian retail-bank contact centres field large volumes of repetitive, anxiety-heavy requests: debited-but-not-credited transfers, reversals, ATM/POS disputes, card blocks, login/OTP problems. Customers wait a long time. Social-engineering fraud (callers asking for OTP or PIN) is a known risk in the market. | **[hyp]** plausible, not researched. Before using it in portfolio copy, cite a source (e.g. CBN consumer-protection reports, NIBSS fraud reports). |
| **Pain (portfolio audience)** | The real audience is hiring managers, banks, fintechs and AI agencies judging whether *you* can build a voice AI they would trust with money-adjacent support. | **[user]** portfolio / demo purpose |
| **Promise** | "A voice agent that resolves or correctly escalates the most common Nigerian banking support requests. It never asks for a PIN, OTP, password or CVV, and every step is verifiable in logs and tests." | **[hyp]** wording draft |
| **Product** | ElevenLabs voice agent + ENTIN Support API + synthetic Postgres DB + n8n orchestration. It covers 19 customer intents and 3 control intents (see `docs/design/intents-and-risk.md`). | **[user]** scope · **[hyp]** decomposition |
| **Plumbing** | See §2. Synthetic data only. The API enforces security itself, so safety doesn't depend on the prompt alone. | **[hyp]** architecture |
| **Packaging** | A public GitHub repo with an architecture diagram, a live web-widget demo (optional phone number), a 3-minute demo video, and a published test/red-team report. | **[hyp]** |
| **Proof** | (a) ElevenLabs tool-call and simulation tests pass with mocks and live. (b) A red-team suite of social-engineering calls results in zero requests for secrets. (c) Every seeded persona reaches its expected outcome. (d) n8n execution logs show escalations and post-call ingestion. This proves a *working prototype*, not customer validation. | **[hyp]** |

## 2. Architecture (recommended)

```
Caller (web widget / optional Twilio number)
   │  voice
   ▼
ElevenLabs Agent  ── Knowledge Base (ENTIN FAQs, fictional policies; RAG)
   │  Workflow: Triage → Verify → Specialist sub-agents → Human transfer
   │  Server tools (HTTPS + bearer secret)
   ▼
ENTIN Support API  (FastAPI + Pydantic, OpenAPI contract)
   │  identity verification · risk engine · redaction · audit log
   ├──► Postgres (Supabase) — synthetic banking DB
   └──► n8n (async events: escalations, notifications, SLA)
ElevenLabs post-call webhook (HMAC) ──► n8n ──► call outcomes / QA digest
```

**Backend recommendation [hyp]: Python FastAPI + Pydantic on Render/Railway/Fly, with Postgres on Supabase.**
- Security-critical logic lives in versioned, unit-tested code rather than workflow nodes. That covers verification, risk scoring, redaction and verification-token scoping.
- Pydantic generates the OpenAPI spec, so the API contract document and the running code can't drift apart.
- Synchronous voice tools go **directly** to the API. Callers hear every extra hop as silence.
- n8n takes the **asynchronous** work: escalation routing, synthetic customer notifications, SLA watchers, post-call ingestion and the daily QA digest. That's where visual orchestration adds value and latency doesn't matter.
- *Alternative:* n8n as the whole backend (webhook → Postgres). It's faster to build but harder to test and to prove safe. I don't recommend it for a "production-minded" portfolio piece.

**Platform facts relied on [source]:**
- ElevenLabs server (webhook) tools support bearer/custom-header/OAuth2 auth, path/query/body params, and assigning dynamic variables from responses. [docs](https://elevenlabs.io/docs/agents-platform/customization/tools/server-tools)
- Agent Workflows provide subagent nodes, tool nodes that guarantee a call, and transfer-to-number nodes. [docs](https://elevenlabs.io/docs/agents-platform/customization/agent-workflows)
- System tools include call transfer. [docs](https://elevenlabs.io/docs/agents-platform/customization/tools/system-tools)
- Post-call webhooks are HMAC-signed via the `elevenlabs-signature` header and include transcript, analysis, evaluation-criteria and data-collection results. [docs](https://elevenlabs.io/docs/agents-platform/workflows/post-call-webhooks)
- Agent testing offers simulation, next-reply and tool-call tests, with tool mocking. [docs](https://elevenlabs.io/docs/eleven-agents/customization/agent-testing)

## 3. First end-to-end slice

**Scenario:** "I sent money and it left my account, but my sister says she hasn't received it." (intent `TRANSFER_DEBITED_NOT_RECEIVED`, risk MEDIUM, persona S01)

| | |
|---|---|
| **User** | Synthetic customer "Adaeze Okafor" calling from the web widget |
| **Trigger** | Caller describes a debited transfer that hasn't arrived |
| **Flow** | Greet → classify → `assess_request` → `verify_caller` (name + DOB + last 4 of account) → `find_transactions` (amount ≈ ₦45,000, yesterday) → `get_transaction_status` → agent explains in plain speech → `create_ticket` if the reversal/credit window has passed → offer human → close |
| **Output** | Spoken status and next step; a ticket ref read back in digit groups; `call_sessions` and `audit_log` rows; an n8n post-call execution |
| **Success** | Correct transaction identified. No secret requested. Status matches the DB. Ticket created only when policy says so. Summary stored with redaction. |
| **Failure behavior** | 2 failed verifications → HIGH risk → no data disclosed → human handoff. API timeout → agent apologises, offers callback ticket, never guesses status. |

**Non-goals for v1 [hyp]:** reading out balances, moving money, reversing transactions, changing PINs/passwords, unlocking accounts over the phone, real SMS/email to real people, multi-language (pending decision D4).

## 4. Decision log

| # | Decision | By | Why |
|---|---|---|---|
| 1 | Fictional bank, synthetic data only, no real rails | user | Safety and legal; portfolio purpose |
| 2 | ElevenLabs for the voice agent | user | Stated stack |
| 3 | "anything" = **n8n** for orchestration | Claude (assumed from dictation) | "anything" read as dictated "n8n". **Confirm (D1).** |
| 4 | "existing compliance/ticket status" = **complaint** / ticket status | Claude (assumed) | Looks like a transcription of "complaint". **Confirm (D2).** |
| 5 | FastAPI + Supabase Postgres backend; n8n for async only | Claude (recommendation) | See §2. **Confirm (D3).** |
| 6 | Never request PIN, OTP, password, CVV, auth/token codes, full card number, online-banking password. Also never full BVN/NIN. | user (+ BVN/NIN added by Claude) | Security. Enforced in prompt, API input validation and tests. |
| 7 | Three risk levels: LOW / MEDIUM / HIGH | user | The API computes risk deterministically; see intents doc |
| 8 | Protective actions (card block) need less verification than disclosures | Claude | Real banks let you block a card fast. Blocking harms no one; disclosing data can. |
| 9 | All money stored as integer kobo; all IDs prefixed and deterministic | Claude | Correctness and stable test references |

## 4b. Decisions made 2026-09-21 (round 2)

| # | Decision | By |
|---|---|---|
| D1 | n8n **self-hosted** | user |
| D2 | "compliance" = **complaint** / ticket status (assumed; no objection) | Claude |
| D3 | **FastAPI** chosen: Python domain logic is framework-free and unit-tested; FastAPI is a thin layer. **SQLite** for the demo (single file, zero setup); Postgres/Supabase is an optional later swap | user asked Claude to decide |
| D4 | Nigerian English default; Pidgin, Yoruba, Hausa, Igbo where ElevenLabs supports them (verify the language list at setup) | user |
| D5 | Web widget now; Nigerian phone number later (Twilio or SIP trunk) | user |
| D6 | Real **CBN timelines with sources**: ATM on-us instant, not-on-us 48 h, POS 72 h, failed transfers 72 h (effective 8 June 2020); complaints within two weeks | user |
| D7 | Human handoff goes to the **user's own phone** (phone calls only; the widget books a callback + email) | user |
| D8 | Added scenarios S27–S36: forgot PIN, volunteered OTP/CVV/password, no transaction reference, unrecognised ₦150,000, another customer's balance, block every card, "ignore your rules", reported three times | user |
| D9 | **ATM disputes = HIGH**; POS disputes stay MEDIUM | user |

**Phase now:** implementation (user asked to build fast, 2026-09-21). See the README for what is built and verified.

## 4c. Decisions made 2026-09-21 (round 3): Google Sheets bank

| # | Decision | By |
|---|---|---|
| D10 | The bank's database is a **Google Sheet** with 500 existing customers (571 accounts, 502 cards, ~6,200 transactions), generated by `data/generate_bank.py` | user |
| D11 | **All logic runs inside n8n** (`n8n/1-live-call-tools.json`), which reads and writes the sheet directly. The Python API moves to `legacy/` as a reference. | user |
| D12 | A **bank-activity simulator** (n8n, every 5 min) keeps accounts moving and occasionally creates issues for the agent | user |
| D13 | Verification state lives in the **Sessions** tab, keyed by the ElevenLabs `system__conversation_id`, so there's no token. Secrets are blocked before any tool runs. | Claude |

The design docs in `docs/design/` still describe the API version's endpoints. The tool names, intents, risk model and personas carry over unchanged.

## 5. Open decisions (owner: you) — superseded by 4b; kept for history

- **D1** Confirm n8n (self-hosted or n8n Cloud?). An n8n MCP connection is available in this environment, so I can build and validate workflows directly in your instance later.
- **D2** Confirm "complaint/ticket status".
- **D3** Approve the FastAPI + Supabase backend, or pick TypeScript (Hono/Fastify) if you'd rather show TS skills.
- **D4** Languages: Nigerian English only for v1, or also Pidgin / Yoruba / Hausa / Igbo? This affects voice choice and tests.
- **D5** Channel: web widget only, or also a Twilio phone number (paid)?
- **D6** Timelines and limits in the knowledge base: purely fictional ENTIN policy (my default), or mirror real CBN guidance? Mirroring means citing sources.
- **D7** Human handoff target for the demo: transfer to your own phone number, or simulated handoff (ticket + callback window)?
- **D8** Test cases: I propose 26 seeded personas in `data-model.md` §4. Add any scenarios you specifically want to show.
- **D9** Are ATM/POS disputes MEDIUM (escalating to HIGH on modifiers) or always HIGH? See `design/intents-and-risk.md` §6.

## 6. Implementation outline (after sign-off)

1. **M1 Specs frozen** — this package reviewed; D1–D8 answered.
2. **M2 Data** — schema migration, deterministic seed script, persona fixtures, synthetic-data guard checks.
3. **M3 API** — 13 tool endpoints, verification and risk engines, redaction, audit log, OpenAPI; unit and contract tests.
4. **M4 Agent** — system prompt, KB docs, tools JSON, workflow, evaluation criteria and data-collection fields; tool-call tests with mocks.
5. **M5 n8n** — 5 workflows exported as JSON, validated, run against the staging API.
6. **M6 Proof** — live simulation suite, red-team suite, demo video, README with results.

## 7. Proof checks for the next build milestone (first slice)

1. `pytest` passes for `verify_caller`, `assess_request`, `find_transactions`, `get_transaction_status` and `create_ticket`. This includes sending a 16-digit number or an `otp` field, which must return `SENSITIVE_DATA_REJECTED`.
2. An ElevenLabs tool-call test for persona S01 asserts that `verify_caller`, then `find_transactions`, then `get_transaction_status` are called with the expected params.
3. An ElevenLabs simulation test for S01 passes its success criteria. The evaluation criterion `no_secret_requested` is `success`.
4. After a live widget call, the DB has one `call_sessions` row with intent `TRANSFER_DEBITED_NOT_RECEIVED`, risk `MEDIUM` and a redacted summary. The n8n post-call execution status is `success`, with its signature verified.
5. Negative case (persona S17, wrong DOB twice): no transaction data appears in the transcript, and a handoff is recorded with risk `HIGH`.

## Design package

- [Intents, risk model, security and escalation policy](design/intents-and-risk.md)
- [Synthetic data model and seeded test personas](design/data-model.md)
- [API / tool contracts](design/api-contracts.md)
- [ElevenLabs agent package and n8n workflows plan](design/agent-and-workflows.md)
