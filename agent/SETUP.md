# ENTIN Voice Agent: Setup (about 30–40 minutes)

No servers to host. You need three things: **one Google Sheet** (the bank), **your self-hosted n8n** (the brain) and **one ElevenLabs agent** (the voice).

## 1. Create the bank in Google Sheets (5 min)

1. Optional: regenerate the data first so all dates are relative to today:
   ```bash
   python3 data/generate_bank.py
   ```
   You need `pip install openpyxl` for this.
2. In Google Drive, create a new Google Sheet. Then use **File → Import → Upload** with `data/entin-bank.xlsx`, and choose **Replace spreadsheet**.
3. You now have 14 tabs:
   - **Customers** (500), **Accounts**, **Cards**, **Transactions** (~6,200), **Digital Access**
   - **Tickets**, **Disputes**, **Security Cases**, **Sessions**, **Escalations**, **Call Log**
   - **Branches & ATMs**, **Demo Scenarios**, and **Test Callers** (your cheat sheet for demo calls)
4. Copy the sheet's URL.

## 2. Set up n8n (10 min)

1. **No server settings needed.** This works on RepoCloud as it is: the sheet link and alert email (nwanduben@gmail.com) are already written into the workflows.
2. Create these credentials:
   - **Google Sheets account**: Google Sheets OAuth2, signed in to the account that owns the sheet.
   - **ENTIN Webhook Auth**: Header Auth, with name `Authorization` and value `Bearer <a long random secret>`. Keep that secret for ElevenLabs.
   - **ENTIN SMTP**: Gmail with an App Password. Use host `smtp.gmail.com`, port `465`, SSL/TLS on.
3. Import the five workflows from `n8n/`. On each Google Sheets, Webhook and Email node, pick the credential above.

   | File | What it does | Activate? |
   |---|---|---|
   | `1-live-call-tools.json` | ElevenLabs calls it **during** the call through 13 webhooks, one per tool (`/webhook/entin/<tool>`); reads and writes the bank | Yes |
   | `2-post-call-summary.json` | Saves each call's redacted summary to **Sessions** and emails QA alerts | Yes |
   | `3-bank-activity.json` | Every 5 minutes: new salaries, POS, transfers, occasional failed transfers and ATM errors | Yes |
   | `4-daily-digest.json` | 08:00 WAT summary email | Yes |
   | `5-reset-demo.json` | **Run manually before a demo.** Puts Gerald's payment back at "yesterday ~4pm" and un-blocks the test cards | No, manual only |
4. Run **5 – Reset demo** once now.

## 3. Create the agent in ElevenLabs (15 min)

1. **Secret.** Go to Agents → Secrets and create `ENTIN_TOOL_SECRET`, with value `Bearer <the same secret as ENTIN Webhook Auth>`. Copy its secret id.
2. **Tools.** Generate them, then add each file in `agent/tools/` as a Webhook tool:
   ```bash
   N8N_BASE=https://your-n8n ELEVENLABS_SECRET_ID=<id> python3 agent/build_tools.py
   ```
   `conversation_id` must be set to the dynamic variable `system__conversation_id`. The field names in the UI may differ slightly.
3. **Prompt.** Paste `agent/system-prompt.md` into the System prompt and `agent/first-message.txt` into the First message.
4. **Knowledge base.** Upload the 4 files in `agent/knowledge-base/` and enable RAG.
5. **System tools.**
   - Enable **End call**.
   - Enable **Language detection**. Add Hausa, Yoruba and Igbo if they're listed.
   - Enable **Transfer to number** with your phone number.
6. **Voice and LLM.**
   - Pick a Nigerian-accented voice.
   - Use a multilingual model if you enabled other languages.
   - Pick an LLM with reliable tool calling, with temperature around 0.3.
7. **Analysis.** Add the criteria and fields from `agent/evaluation.json`.
8. **Post-call webhook.** Point it at `https://<your-n8n>/webhook/entin-post-call`. Paste its HMAC secret into the **Secret** box of the **HMAC with ElevenLabs Secret** node in workflow 2, replacing `PASTE_ELEVENLABS_WEBHOOK_SECRET_HERE`.
9. **Widget.** Copy the embed snippet into your portfolio page.

> **Transfer limitation.** Transfer to number only works on phone calls. On the web widget, a handoff is logged in **Escalations** and emailed to you. Once you add a Nigerian number (Twilio or SIP trunk), transfers go to your phone.

## 4. Your first demo call

1. Open the **Test Callers** tab and find Gerald Okeke.
2. Open the widget and say: *"Good morning, my name is Gerald. 70,000 naira was deducted from my account yesterday and I don't understand why."*
3. When asked, give Gerald's date of birth (15 June 1990), the last 4 digits of his account and the last 4 of his phone. All three are in Test Callers.
4. Watch the sheet change as the call goes on:
   - **Call Log** gains a row per step.
   - **Sessions** shows him verified and at HIGH risk.
   - In **Cards**, his card flips to `blocked_fraud`.
   - New rows appear in **Tickets**, **Disputes** and **Escalations**.
   - You get an email.
5. Run **5 – Reset demo** afterwards.

`n8n/test/sample-call-log.csv` shows what the Call Log rows look like.

## Test before importing (optional)

```bash
node n8n/test/run_tests.mjs
```

This runs the exact workflow JSON against the 500-customer data. It covers 31 scenarios and needs no n8n or Google account.
