# ENTIN Support API — Tool Contracts

Status: **draft for review [hyp]**. The FastAPI implementation will generate the OpenAPI 3.1 spec, which becomes the source of truth after that. This document is the design intent.

## 1. Conventions

- **Base:** `https://<api-host>/v1/tools/<tool_name>`, all `POST` with a JSON body. Each endpoint maps to one ElevenLabs server tool with the same name.
- **Auth:** `Authorization: Bearer <ELEVENLABS_TOOL_SECRET>`, stored as an ElevenLabs secret ([server-tool auth](https://elevenlabs.io/docs/agents-platform/customization/tools/server-tools)). A separate secret is used for n8n → API calls. Keys can be rotated with no downtime (two keys valid at once).
- **Conversation binding:** every request carries `conversation_id`, filled from the ElevenLabs system dynamic variable `system__conversation_id`. Phone calls also send `caller_id` from `system__caller_id`. *Verify the exact variable names during setup.*
- **Verification:** data tools require `verification_token`. The server checks that the token matches `conversation_id`, is unexpired, and has a sufficient tier.
- **Secret guard:** any string field that matches a secret pattern (13–19 digits, or a 4–8-digit code next to pin/otp/cvv/token/password) is rejected with `SENSITIVE_DATA_REJECTED` and logged as a security event, with the value masked.
- **Idempotency:** write tools accept `idempotency_key` (the agent passes `conversation_id` + tool + intent), so retries don't create duplicate tickets.
- **Latency target:** p95 < 800 ms per tool, hard timeout 5 s. Voice callers hear silence.
- **Envelope (every response):**

```json
{
  "ok": true,
  "data": { },
  "say": "Short, speakable sentence the agent may use.",
  "risk_level": "LOW|MEDIUM|HIGH",
  "next_actions": ["offer_human", "create_ticket"],
  "error": null
}
```

`error` = `{ "code": "...", "retryable": bool, "say": "..." }`. The `say` field keeps the wording for sensitive outcomes (declines, restrictions, failures) controlled by the server and safe for customers.

**Error codes:** `UNAUTHORIZED`, `VERIFICATION_REQUIRED`, `VERIFICATION_LOCKED`, `TOKEN_EXPIRED`, `NOT_FOUND`, `AMBIGUOUS_MATCH`, `SENSITIVE_DATA_REJECTED`, `POLICY_BLOCKED`, `RATE_LIMITED`, `UPSTREAM_UNAVAILABLE`, `VALIDATION_ERROR`.

## 2. Tools

| # | Tool | Min tier | Purpose |
|---|---|---|---|
| 1 | `assess_request` | T0 | Deterministic risk + allowed actions for an intent |
| 2 | `verify_caller` | T0 | Identity verification → token |
| 3 | `find_transactions` | T2 | Match the transaction the caller describes |
| 4 | `get_transaction_status` | T2 | Status, reversal, next step for one transaction |
| 5 | `get_card_status` | T2 | Card state + latest decline reason (customer-safe) |
| 6 | `block_card` | T1 | Protective block (lost/stolen/fraud) |
| 7 | `get_digital_access_status` | T1 (T2 for lock details) | Login/lock/device/OTP-delivery state |
| 8 | `create_ticket` | T1 | Complaint / callback / replacement ticket |
| 9 | `create_dispute` | T2 | ATM/POS/unauthorised dispute linked to a transaction |
| 10 | `get_ticket_status` | T1 + ticket ref | Ticket/dispute status and SLA |
| 11 | `report_security_event` | T0 | Sensitive disclosure / social engineering / fraud signal |
| 12 | `request_human_handoff` | T0 | Create handoff + return transfer target or callback |
| 13 | `find_branch_or_atm` | T0 | Nearest branch/ATM by city/area |

### 2.1 `assess_request`
**In:** `conversation_id`, `intent` (enum from the intents doc), `signals[]` (`customer_denies_authorisation`, `social_engineering_suspected`, `vulnerable_customer`, `repeat_contact`), `amount_naira?`
**Out `data`:** `risk_level`, `required_tier`, `allowed_tools[]`, `must_escalate` (bool), `escalation_queue?`
The session's `max_risk` is updated and never lowered.

### 2.2 `verify_caller`
**In:** `conversation_id`, `caller_id?`, `full_name`, `date_of_birth` (YYYY-MM-DD), `account_last4?`, `phone_last4?`
**Out `data`:** `result` (`verified|partial|failed|locked`), `tier` (`T0|T1|T2`), `verification_token?`, `attempts_remaining`, `first_name?` (only when verified or partial)
Never says which factor failed. The second failure returns `locked` with `must_escalate=true`.

### 2.3 `find_transactions`
**In:** `conversation_id`, `verification_token`, `date_from`, `date_to`, `amount_naira_approx?`, `channel?` (`transfer|pos|atm|card_online|ussd`), `direction?`, `counterparty_hint?`
**Out `data`:** `matches[]` (max 3): `txn_id`, `date_spoken` ("yesterday at about 2 PM"), `amount_naira`, `channel`, `counterparty_name_masked`, `counterparty_bank`, `status`. On more than 3 matches, returns `AMBIGUOUS_MATCH` plus a `say` that asks a narrowing question.

### 2.4 `get_transaction_status`
**In:** `conversation_id`, `verification_token`, `txn_id`
**Out `data`:** `status`, `debited` (bool), `beneficiary_credited` (bool|null), `reversal: {status, expected_by, completed_at}?`, `within_policy_window` (bool), `recommended_action` (`wait|create_ticket|create_dispute|escalate`), `policy_ref` (KB article id)

### 2.5 `get_card_status`
**In:** `conversation_id`, `verification_token`, `card_last4?`
**Out `data`:** `card_last4`, `status`, `online_enabled`, `latest_decline: {date_spoken, merchant, reason_category}`. `reason_category` is customer-safe (`insufficient_funds`, `card_blocked`, `online_disabled`, `limit_reached`, `expired`, `needs_review`). `FRAUD_RULE` maps to `needs_review` and `must_escalate`.

### 2.6 `block_card`
**In:** `conversation_id`, `verification_token`, `card_last4`, `reason` (`lost|stolen|suspected_fraud`), `caller_confirmed` (must be `true`; the agent confirms verbally first), `idempotency_key`
**Out `data`:** `blocked` (bool), `block_ref`, `replacement_ticket_id?`. The API also puts a `card_blocked` event on the n8n queue and records a simulated notification in `notification_outbox`.

### 2.7 `get_digital_access_status`
**In:** `conversation_id`, `verification_token`
**Out `data`:** `profile_status`, `locked` (bool), `device_bound`, `otp_recent: {delivered, failed, dnd_blocked, last_status_spoken}`, `guidance_article_id`. Never returns or accepts a code.

### 2.8 `create_ticket`
**In:** `conversation_id`, `verification_token`, `category` (intent code), `linked_txn_id?`, `summary` (≤ 400 chars; redacted server-side), `callback_requested` (bool), `idempotency_key`
**Out `data`:** `ticket_id`, `ticket_id_spoken` ("T K T, one zero four, two three three"), `priority`, `sla_due_spoken`

### 2.9 `create_dispute`
**In:** `conversation_id`, `verification_token`, `txn_id`, `type` (`ATM_NO_CASH|POS_DOUBLE_DEBIT|POS_FAILED_DEBITED|UNAUTHORIZED`), `caller_statement` (≤ 400 chars), `idempotency_key`
**Out `data`:** `dispute_id`, `dispute_id_spoken`, `ticket_id`, `expected_resolution_spoken`, `policy_ref`

### 2.10 `get_ticket_status`
**In:** `conversation_id`, `verification_token`, `reference` (TKT- or DSP-)
**Out `data`:** `status`, `last_update_spoken`, `sla_breached` (bool), `next_step`. A breach automatically escalates the ticket (event to n8n).

### 2.11 `report_security_event`
**In:** `conversation_id`, `type` (`sensitive_disclosure|social_engineering|unauthorized_txn|prompt_injection`), `secret_kind?` (`pin|otp|password|cvv|card_number|other`). **The value itself is never sent.** Also `note?` (≤ 200 chars, redacted).
**Out `data`:** `case_id`, `advice_article_id`. Sets session risk to HIGH.

### 2.12 `request_human_handoff`
**In:** `conversation_id`, `reason` (enum), `summary` (≤ 600 chars: intent, what was checked, refs), `caller_preference?` (`transfer|callback`)
**Out `data`:** `handoff_id`, `mode` (`transfer|callback`), `queue`, `priority`, `transfer_destination_key?`, `callback_window_spoken?`. The agent then uses the ElevenLabs **transfer** system tool / workflow node to the configured number. The API never returns a raw phone number to the LLM.

### 2.13 `find_branch_or_atm`
**In:** `city`, `area?`, `type` (`branch|atm|any`), `service?`
**Out `data`:** `results[]` (max 3): `name`, `address_spoken`, `hours_spoken`, `status`

## 3. Inbound webhooks (to n8n, not the API)

| Source | Endpoint | Auth |
|---|---|---|
| ElevenLabs post-call transcription | n8n `/webhook/entin/post-call` | HMAC `elevenlabs-signature` ([docs](https://elevenlabs.io/docs/agents-platform/workflows/post-call-webhooks)) |
| API events (`handoff_created`, `card_blocked`, `security_case_opened`, `sla_breached`, `ticket_created`) | n8n `/webhook/entin/events` | HMAC `x-entin-signature` (shared secret) + timestamp, 5-min replay window |

## 4. Non-functional

- **Rate limits:** 30 tool calls per conversation per minute; `verify_caller` limited to 2 failures per conversation and 5 per customer per 24 h.
- **Audit:** every call writes to `audit_log` (redacted params, result code, latency).
- **Observability:** structured JSON logs, request id = `conversation_id` + sequence.
- **Contract tests:** each tool has happy path, verification-missing, token-expired, secret-injection and not-found tests. The persona fixtures (S01–S26) are the shared test data.
