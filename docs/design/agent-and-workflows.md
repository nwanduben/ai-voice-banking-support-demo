# ElevenLabs Agent Package and n8n Workflows — Plan

Status: **plan only [hyp]**. The final prompt text, tool JSON and workflow JSON are produced in milestones M4–M5.

## 1. Agent package contents (`agent/`)

| File | What it contains |
|---|---|
| `system-prompt.md` | Spoken-conversation prompt (structure in §2) |
| `first-message.txt` | Greeting + demo/recording notice |
| `tools/*.json` | 13 server-tool definitions matching `api-contracts.md`, plus system tools (end call, transfer, language detection if D4 = multilingual) |
| `workflow.md` | Agent Workflow graph (subagent + tool + transfer nodes) with the conditions for each edge |
| `knowledge-base/*.md` | ENTIN KB documents (§4), exported from `kb_articles` |
| `security-policy.md` / `escalation-policy.md` | Plain-language copies of `intents-and-risk.md` §4–5, uploaded to the KB and linked from the prompt |
| `evaluation.json` | Evaluation criteria + data-collection fields (§5) |
| `tests/*.json` | Tool-call, next-reply and simulation tests (§6) |
| `SETUP.md` | Step-by-step dashboard/CLI setup: voice, LLM, turn-taking, secrets, webhooks, phone/widget |

## 2. System prompt structure (spoken-first)

Sections: **Identity · Environment · Tone · Goal (numbered flow) · Guardrails · Tools (when and how) · Error handling · Closing.** The sectioned layout follows ElevenLabs' prompting guidance; confirm it against the current prompting guide during M4.

Voice-specific rules to include:
- 1–2 sentences per turn and one question at a time. No lists, markdown or URLs read aloud.
- Money spoken naturally ("forty-five thousand naira"). References read in chunks ("T-K-T, one-zero-four, two-three-three") and repeated once on request.
- Before a tool call, say a short filler ("Let me check that for you"), so the caller never hears dead air.
- Confirm understanding before acting ("So a transfer of about forty-five thousand naira yesterday to your sister at another bank — is that right?").
- Nigerian English register: warm, respectful ("Ma"/"Sir" only if the caller uses them first), with no slang imitation.
- Handle interruptions gracefully, and recover when speech-to-text is unclear ("Sorry, I didn't catch the last part…").
- Tool results always override the model's assumptions. Use the API's `say` field verbatim for sensitive outcomes.

**Draft first message:** "Hello, thank you for calling ENTIN Bank. This is a demo line and calls may be recorded. I'm Ada, your virtual assistant. How can I help you today?" (The name "Ada" is a placeholder; you decide.)

## 3. Agent Workflow graph

```
Start → [Triage subagent]
          ├─ LOW (FAQ/branch/password guidance) → [Info subagent] → wrap-up
          ├─ needs T1/T2 → [Verify subagent] ─ tool node: verify_caller
          │      ├─ verified → route by intent:
          │      │     [Transactions subagent] (C03–C06, C08, C09)
          │      │     [Cards & Fraud subagent] (C07, C10, C11, C18)
          │      │     [Digital Access subagent] (C12–C15)
          │      │     [Tickets subagent] (C16)
          │      └─ locked → [Handoff]
          ├─ HIGH anywhere → tool node: request_human_handoff → Transfer-to-number node
          └─ Human request → [Handoff]
```

Each subagent gets only the tools it needs. That keeps tool choice accurate and limits the damage a prompt injection can do. [Workflows docs](https://elevenlabs.io/docs/agents-platform/customization/agent-workflows)

Settings to decide or test in M4:
- **Voice:** a Nigerian-accented English voice from the Voice Library (check what's available).
- **LLM:** pick for tool-calling reliability; ElevenLabs docs note that model choice affects function calling.
- **Turn-taking:** patient turn timeout for callers reading references.
- **Knowledge base:** RAG enabled.
- **Max call duration:** about 10 minutes.

## 4. Knowledge base (all fictional ENTIN policy unless D6 says otherwise)

1. About ENTIN Bank (fictional, demo disclaimer)
2. Contact channels, hours, fictional USSD code, app features
3. Branches & ATMs overview (details come from the tool)
4. Transfers: NIP vs intra-bank, statuses explained, ENTIN reversal windows
5. Failed / pending / reversal FAQs
6. ATM & POS disputes: what to expect, timelines
7. Cards: decline reasons (customer-safe), enabling online use, limits, replacement
8. Lost/stolen card & fraud: immediate steps
9. Mobile banking: login, device binding, lockout, password reset steps (self-service only)
10. OTP not received: DND, network, email fallback
11. Complaints: how tickets work, SLAs
12. **Security: "ENTIN will never ask for…"**, scam patterns in Nigeria (impersonation, "wrong transfer" refund scams, fake alerts)
13. Fees & limits table (fictional)

## 5. Evaluation criteria and data collection (post-call analysis)

**Evaluation criteria (success/failure):**
- `no_secret_requested`
- `secret_disclosure_handled`
- `verification_before_disclosure`
- `correct_escalation`
- `no_unfounded_promises` (no promised refunds or outcomes)
- `concise_spoken_style`
- `issue_resolved_or_routed`

**Data collection fields:** `primary_intent`, `secondary_intents`, `max_risk`, `verification_tier`, `references_created`, `handoff_reason`, `caller_sentiment`.

These arrive in the post-call webhook `analysis` object. n8n stores them in `call_sessions`. [docs](https://elevenlabs.io/docs/agents-platform/workflows/post-call-webhooks)

## 6. Test calls

- **Tool-call tests** (one per persona S01–S26): assert tool order and params, with mocked tool responses taken from the seed fixtures.
- **Simulation tests:** a simulated caller per persona, with mocks first, then live against staging.
- **Red-team simulations:** prompt injection, "I'm bank staff", a caller offering an OTP, requests for a full account number, money-movement requests, third-party callers.
- **Human test script:** 10 scripted live calls recorded for the demo video, with pass/fail against each persona's expected outcome.

[Agent testing docs](https://elevenlabs.io/docs/eleven-agents/customization/agent-testing)

## 7. n8n workflows (exported JSON in `n8n/`)

| # | Workflow | Trigger | Key steps |
|---|---|---|---|
| W1 | Post-call ingestion | Webhook `/entin/post-call` | Verify HMAC (Code node, crypto) → reject if bad → redact transcript (secret regexes) → upsert `call_sessions` → if `secret_detected` or failed eval → alert QA channel |
| W2 | Escalation router | Webhook `/entin/events` (`handoff_created`, `sla_breached`) | Verify signature → Switch on priority/queue → notify the human queue (Slack/email/Sheet, D7) → Wait until SLA → if still open, re-escalate |
| W3 | Security & card-block notifications | Webhook `/entin/events` (`card_blocked`, `security_case_opened`) | Insert a simulated customer notification in `notification_outbox` (no real SMS) → alert the fraud queue → log to `audit_log` |
| W4 | Ticket SLA watcher | Schedule (every 15 min) | Query tickets near/over SLA → emit `sla_breached` → W2 |
| W5 | Daily QA digest | Schedule (daily 08:00 WAT) | Aggregate calls by intent, risk, containment rate, escalations and evaluation failures → email/Slack report |

Build approach: the n8n MCP tools available in this environment can search node schemas, validate workflows and deploy them to your instance. Each workflow gets validated and a test execution before its JSON is exported to the repo. Credentials (Postgres, Slack/email) are created by you in n8n; the JSON only references them by name.

## 8. Proposed repo layout

```
entin-voice-support/
  docs/            kickoff + design (this package)
  api/             FastAPI app, risk & verification engines, tests
  db/              migrations, seed script, persona fixtures
  agent/           ElevenLabs package (§1)
  n8n/             W1–W5 JSON exports
  evals/           red-team scripts, results reports
  README.md        architecture diagram, demo video, results
```
