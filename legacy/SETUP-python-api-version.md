# ENTIN Voice Agent: Setup (about 30 minutes)

## 1. Run the API

```bash
cd api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m app.db                       # seeds entin.db with synthetic data
export ENTIN_TOOL_SECRET="$(openssl rand -hex 24)"
uvicorn app.main:app --host 0.0.0.0 --port 8000
python -m unittest discover -s tests -t .   # 29 persona tests
```

**Deploy.** Put it on Render or Railway, wherever your self-hosted n8n lives:
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Environment: `ENTIN_TOOL_SECRET`, `ENTIN_FACTOR_SALT` and `ENTIN_DB=/data/entin.db`
- The database file needs a persistent disk mounted at `/data`.
- Check that `GET /health` returns `{"ok": true, "synthetic": true}`.

For local testing with ElevenLabs, you can expose the API with `ngrok http 8000`.

## 2. Create the agent in ElevenLabs

1. **Secret.** Go to Agents → Secrets → New secret, named `ENTIN_TOOL_SECRET`. Set its value to `Bearer <your ENTIN_TOOL_SECRET>`. Copy its secret id.
2. **Tools.** Generate the tool configs:
   ```bash
   N8N_BASE=https://your-n8n ELEVENLABS_SECRET_ID=<id> python agent/build_tools.py   # tools go through n8n W0 (see section 3)
   ```
   Then add each file in `agent/tools/` as a **Webhook tool**, either via the API or by copying the fields in the dashboard.
   - `conversation_id` must be set to the dynamic variable `system__conversation_id`.
   - `verification_token` must be set to the dynamic variable `verification_token`.
   - In `verify_caller`, add the response assignment `data.verification_token` → `verification_token`.
   - Field names may differ slightly in the current UI; the meaning above is what matters.
3. **Dynamic variable default.** Add `verification_token` with the default value `none`. The API treats `none` as unverified.
4. **Prompt.** Paste `agent/system-prompt.md` into the System prompt and `agent/first-message.txt` into the First message.
5. **Knowledge base.** Upload the 4 files in `agent/knowledge-base/` and enable RAG.
6. **System tools.**
   - Enable **End call**.
   - Enable **Language detection**, with English as default. Add Hausa, Yoruba and Igbo only if the language list shows them. Pidgin is handled by the prompt in English mode.
   - Enable **Transfer to number** with your own phone number as the destination. Label it `human_line` / `fraud_line`.
7. **Voice and LLM.**
   - Pick a Nigerian-accented English voice from the Voice Library.
   - Use a multilingual TTS model if you enabled other languages.
   - Pick an LLM known for reliable tool calling.
   - Set temperature low, around 0.3.
8. **Analysis.** Add the evaluation criteria and data-collection fields from `agent/evaluation.json`.
9. **Post-call webhook.** Point it at `https://<your-n8n>/webhook/entin-post-call`. Copy the HMAC secret into n8n's env as `ENTIN_ELEVENLABS_WEBHOOK_SECRET`.
10. **Widget.** In the Widget tab, copy the embed snippet into your portfolio page.
11. **Tests.** Create tests from `agent/test-calls.md`: tool-call tests for #1, 3, 5, 8, 11 and 12, and simulations for the rest.

> **Transfer limitation.** *Transfer to number* only works on phone calls (Twilio or SIP). On the **web widget**, a handoff is recorded as a callback: the API books it and n8n emails you. When you buy a Nigerian number, import it (Twilio, or a SIP trunk from a Nigerian provider if Twilio has no Nigerian inventory). Then live transfers to your phone will work. Check number availability before buying.

## 3. n8n (self-hosted)

### W0: Live call tools (the one you watch during a call)
Every question the agent needs answered mid-call goes **ElevenLabs → n8n W0 → ENTIN API → back to ElevenLabs**. Each step is added as a row to a Google Sheet.

1. Create a Google Sheet with a tab named **`Call Log`**. Paste the header row from `n8n/google-sheet-call-log-header.csv` into row 1. Set n8n env `ENTIN_CALL_LOG_SHEET_URL=<sheet url>`.
2. Create credential **ENTIN Webhook Auth** (Header Auth): name `Authorization`, value `Bearer <ENTIN_TOOL_SECRET>`. ElevenLabs sends this header on every tool call.
3. Import `n8n/w0-live-call-tools.json` and pick your credentials on:
   - the Webhook node
   - the 7 "ENTIN API: …" nodes
   - the Google Sheets node
   Then activate it.
4. Generate the ElevenLabs tools so they point at n8n:
   `N8N_BASE=https://your-n8n ELEVENLABS_SECRET_ID=<id> python agent/build_tools.py`
   Every tool URL becomes `https://your-n8n/webhook/entin-tool?tool=<name>`.
5. Make a call as Gerald Okeke (DOB 15 June 1990, account and phone ending 0037). Say: "70,000 naira was deducted yesterday around 4pm and I don't know why." Watch n8n → Executions and the sheet fill in. `n8n/sample-call-log-gerald.csv` shows what the rows look like.

### W1–W3: after the call and in the background

1. Set these environment variables on the n8n container (W0 also needs `ENTIN_API_BASE`):
   - `NODE_FUNCTION_ALLOW_BUILTIN=crypto`
   - `ENTIN_API_BASE=https://your-api`
   - `ENTIN_ELEVENLABS_WEBHOOK_SECRET=...`
   - `ENTIN_ALERT_EMAIL=you@example.com`
   - If `$env` access is blocked in expressions, also set `N8N_BLOCK_ENV_ACCESS_IN_NODE=false`.
2. Create two credentials:
   - **ENTIN API**: Header Auth, with name `Authorization` and value `Bearer <ENTIN_TOOL_SECRET>`.
   - **ENTIN SMTP**: any SMTP account.
3. Import the three workflows: `n8n/w1-post-call-ingestion.json`, `n8n/w2-escalation-router.json` and `n8n/w3-daily-qa-digest.json`. Select the credentials on the HTTP and Email nodes, then activate.
4. Test W1 by making one widget call. Check that the execution succeeded and that `call_sessions` in the DB was updated.
