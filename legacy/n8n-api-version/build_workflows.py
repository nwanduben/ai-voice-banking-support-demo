"""Generate the ENTIN n8n workflows as importable JSON (n8n/*.json).

Self-hosted n8n requirements:
  - env NODE_FUNCTION_ALLOW_BUILTIN=crypto   (Code node HMAC verification)
  - env ENTIN_API_BASE, ENTIN_ELEVENLABS_WEBHOOK_SECRET, ENTIN_ALERT_EMAIL
  - credential "ENTIN API" (Header Auth: Authorization = Bearer <ENTIN_TOOL_SECRET>)
  - credential "ENTIN SMTP" (any SMTP account) for alert emails
"""
import json
import pathlib

OUT = pathlib.Path(__file__).parent
API_CRED = {"httpHeaderAuth": {"id": "REPLACE", "name": "ENTIN API"}}
SMTP_CRED = {"smtp": {"id": "REPLACE", "name": "ENTIN SMTP"}}

REDACT_JS = r"""
const WORDS = '(?:pin|otp|one[\\s-]?time|cvv|cvc|security\\s+code|passcode|password|token|auth(?:entication)?\\s+code)';
const PAN = /(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)/g;
const AFTER = new RegExp(WORDS + '\\W+(?:\\w+\\W+){0,3}?(\\d[\\d ]{2,9}\\d|\\d{3,8})', 'gi');
const BEFORE = new RegExp('(?<!\\d)(\\d{3,8})(?!\\d)\\W+(?:\\w+\\W+){0,2}?(?:is\\s+)?(?:my\\s+)?' + WORDS, 'gi');
const PWD = /(?:password|passcode)\s+(?:is|na)\s+(\S+)/gi;
function redact(text) {
  if (!text) return { text, found: false };
  let found = false;
  const mark = () => { found = true; };
  let t = text.replace(PAN, () => { mark(); return '[REDACTED_CARD]'; });
  t = t.replace(AFTER, (m, code) => { mark(); return m.replace(code, '[REDACTED_CODE]'); });
  t = t.replace(BEFORE, (m, code) => { mark(); return m.replace(code, '[REDACTED_CODE]'); });
  t = t.replace(PWD, (m, pw) => { mark(); return m.replace(pw, '[REDACTED_PASSWORD]'); });
  return { text: t, found };
}
"""

VERIFY_JS = r"""
// ElevenLabs post-call webhook: header "elevenlabs-signature: t=<unix>,v0=<hex hmac sha256 of `${t}.${rawBody}`>"
const crypto = require('crypto');
const item = $input.first();
const secret = $env.ENTIN_ELEVENLABS_WEBHOOK_SECRET;
const header = (item.json.headers || {})['elevenlabs-signature'] || '';
const parts = Object.fromEntries(header.split(',').map(p => p.split('=')));
const raw = item.binary && item.binary.data
  ? Buffer.from(item.binary.data.data, 'base64').toString('utf8')
  : JSON.stringify(item.json.body);
const expected = crypto.createHmac('sha256', secret).update(`${parts.t}.${raw}`).digest('hex');
const fresh = Math.abs(Date.now() / 1000 - Number(parts.t)) < 30 * 60;
let valid = false;
try {
  valid = fresh && !!parts.v0 && crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(parts.v0));
} catch (e) { valid = false; }
const body = item.binary && item.binary.data ? JSON.parse(raw) : item.json.body;
return [{ json: { valid, body } }];
"""

EXTRACT_JS = REDACT_JS + r"""
const body = $input.first().json.body || {};
const d = body.data || {};
const analysis = d.analysis || {};
const turns = (d.transcript || []).map(t => `${t.role}: ${t.message || ''}`);
const r = redact(turns.join('\n'));
const evals = analysis.evaluation_criteria_results || {};
const failed = Object.entries(evals).filter(([k, v]) => v && v.result === 'failure').map(([k]) => k);
const dc = analysis.data_collection_results || {};
const val = k => (dc[k] && dc[k].value !== undefined) ? dc[k].value : null;
return [{ json: {
  conversation_id: d.conversation_id,
  agent_id: d.agent_id,
  call_successful: analysis.call_successful,
  summary: redact(analysis.transcript_summary || '').text,
  transcript_redacted: r.text,
  secret_detected: r.found,
  failed_evaluations: failed,
  primary_intent: val('primary_intent'),
  max_risk: val('max_risk'),
  references_created: val('references_created'),
  needs_qa_alert: r.found || failed.length > 0,
} }];
"""


def node(name, type_, version, pos, params, **extra):
    n = {"parameters": params, "name": name, "type": type_, "typeVersion": version, "position": pos}
    n.update(extra)
    return n


def conn(*pairs):
    """pairs: (from, [[targets for output 0], [targets for output 1], ...])"""
    return {src: {"main": [[{"node": t, "type": "main", "index": 0} for t in outs] for outs in outputs]} for src, outputs in pairs}


def http_api(name, pos, method, path, body_expr=None):
    p = {"method": method, "url": f"={{{{ $env.ENTIN_API_BASE }}}}{path}",
         "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth", "options": {"timeout": 10000}}
    if body_expr:
        p.update({"sendBody": True, "specifyBody": "json", "jsonBody": body_expr})
    return node(name, "n8n-nodes-base.httpRequest", 4.2, pos, p, credentials=API_CRED)


def email(name, pos, subject, text):
    return node(name, "n8n-nodes-base.emailSend", 2.1, pos,
                {"fromEmail": "entin-demo@example.com", "toEmail": "={{ $env.ENTIN_ALERT_EMAIL }}",
                 "subject": subject, "emailFormat": "text", "text": text, "options": {}},
                credentials=SMTP_CRED)


def if_true(name, pos, left):
    return node(name, "n8n-nodes-base.if", 2.2, pos, {
        "conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                       "conditions": [{"id": name.lower().replace(" ", "-"), "leftValue": left, "rightValue": "",
                                       "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
                       "combinator": "and"},
        "looseTypeValidation": True, "options": {}})


def post_call():
    nodes = [
        node("ElevenLabs Post-call Webhook", "n8n-nodes-base.webhook", 2, [0, 300],
             {"httpMethod": "POST", "path": "entin-post-call", "responseMode": "responseNode", "options": {"rawBody": True}},
             webhookId="entin-post-call"),
        node("Verify HMAC Signature", "n8n-nodes-base.code", 2, [220, 300], {"jsCode": VERIFY_JS}),
        if_true("Signature Valid?", [440, 300], "={{ $json.valid }}"),
        node("Reject 401", "n8n-nodes-base.respondToWebhook", 1.1, [660, 480],
             {"respondWith": "json", "responseBody": '={"ok": false}', "options": {"responseCode": 401}}),
        node("Redact & Extract Outcome", "n8n-nodes-base.code", 2, [660, 200], {"jsCode": EXTRACT_JS}),
        http_api("Store Outcome in ENTIN API", [880, 200], "POST",
                 "/v1/sessions/{{ $json.conversation_id }}/outcome",
                 "={{ JSON.stringify({ call_successful: $json.call_successful, summary: $json.summary, secret_detected: $json.secret_detected, failed_evaluations: $json.failed_evaluations, primary_intent: $json.primary_intent, max_risk: $json.max_risk }) }}"),
        node("Respond 200", "n8n-nodes-base.respondToWebhook", 1.1, [1100, 200],
             {"respondWith": "json", "responseBody": '={"ok": true}', "options": {}}),
        if_true("Needs QA Alert?", [1320, 200], "={{ $('Redact & Extract Outcome').item.json.needs_qa_alert }}"),
        email("Email QA Alert", [1540, 120], "=ENTIN QA alert: {{ $('Redact & Extract Outcome').item.json.conversation_id }}",
              "=Secret detected: {{ $('Redact & Extract Outcome').item.json.secret_detected }}\nFailed evaluations: {{ $('Redact & Extract Outcome').item.json.failed_evaluations.join(', ') || 'none' }}\nIntent: {{ $('Redact & Extract Outcome').item.json.primary_intent }}\nSummary (redacted): {{ $('Redact & Extract Outcome').item.json.summary }}"),
    ]
    connections = conn(
        ("ElevenLabs Post-call Webhook", [["Verify HMAC Signature"]]),
        ("Verify HMAC Signature", [["Signature Valid?"]]),
        ("Signature Valid?", [["Redact & Extract Outcome"], ["Reject 401"]]),
        ("Redact & Extract Outcome", [["Store Outcome in ENTIN API"]]),
        ("Store Outcome in ENTIN API", [["Respond 200"]]),
        ("Respond 200", [["Needs QA Alert?"]]),
        ("Needs QA Alert?", [["Email QA Alert"], []]),
    )
    return {"name": "ENTIN W1 - Post-call ingestion (HMAC + redaction)", "nodes": nodes, "connections": connections,
            "settings": {"executionOrder": "v1"}}


def events_router():
    rule = lambda types, key: {  # noqa: E731
        "conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
                       "conditions": [{"id": f"{key}-{t}", "leftValue": "={{ $json.type }}", "rightValue": t,
                                       "operator": {"type": "string", "operation": "equals"}} for t in types],
                       "combinator": "or"},
        "renameOutput": True, "outputKey": key}
    nodes = [
        node("Every Minute", "n8n-nodes-base.scheduleTrigger", 1.2, [0, 300],
             {"rule": {"interval": [{"field": "minutes", "minutesInterval": 1}]}}),
        http_api("Fetch ENTIN Events", [220, 300], "GET", "/v1/events"),
        node("Split Events", "n8n-nodes-base.splitOut", 1, [440, 300], {"fieldToSplitOut": "events", "options": {}}),
        node("Parse Payload", "n8n-nodes-base.code", 2, [660, 300], {
            "mode": "runOnceForEachItem",
            "jsCode": "const e = $json; return { json: { id: e.id, type: e.type, created_at: e.created_at, ...JSON.parse(e.payload) } };"}),
        node("Route by Event Type", "n8n-nodes-base.switch", 3.2, [880, 300], {
            "rules": {"values": [rule(["handoff_created", "sla_breached"], "Human Queue"),
                                 rule(["card_blocked", "security_case_opened"], "Fraud Queue"),
                                 rule(["ticket_created", "dispute_created"], "Tickets")]},
            "options": {"fallbackOutput": "none"}}),
        email("Notify Human Queue", [1120, 160],
              "=[{{ $json.priority || 'P2' }}] ENTIN {{ $json.type }} - {{ $json.queue || $json.ticket_id }}",
              "=Conversation: {{ $json.conversation_id }}\nQueue: {{ $json.queue }}\nRisk: {{ $json.risk_level }}\nHandoff/Ticket: {{ $json.handoff_id || $json.ticket_id }}\nSummary (redacted): {{ $json.summary }}\n\nSynthetic demo data only."),
        email("Notify Fraud Team", [1120, 320],
              "=[P1] ENTIN {{ $json.type }} - {{ $json.case_id || $json.block_ref }}",
              "=Conversation: {{ $json.conversation_id }}\nEvent: {{ $json.type }}\nCase: {{ $json.case_id }}\nCards blocked: {{ ($json.cards || []).join(', ') }}\nSecret kind (never the value): {{ $json.secret_kind }}\n\nCustomer SMS is simulated in notification_outbox; nothing is sent to real people."),
        node("Log Ticket Event", "n8n-nodes-base.noOp", 1, [1120, 480], {}),
    ]
    connections = conn(
        ("Every Minute", [["Fetch ENTIN Events"]]),
        ("Fetch ENTIN Events", [["Split Events"]]),
        ("Split Events", [["Parse Payload"]]),
        ("Parse Payload", [["Route by Event Type"]]),
        ("Route by Event Type", [["Notify Human Queue"], ["Notify Fraud Team"], ["Log Ticket Event"]]),
    )
    return {"name": "ENTIN W2 - Escalation & security event router", "nodes": nodes, "connections": connections,
            "settings": {"executionOrder": "v1"}}


def daily_digest():
    nodes = [
        node("Daily 08:00 WAT", "n8n-nodes-base.scheduleTrigger", 1.2, [0, 300],
             {"rule": {"interval": [{"field": "cronExpression", "expression": "0 8 * * *"}]}}),
        http_api("Fetch Daily Report", [220, 300], "GET", "/v1/reports/daily"),
        email("Email QA Digest", [440, 300], "=ENTIN daily voice-support digest {{ $now.toFormat('yyyy-LL-dd') }}",
              "=Calls: {{ $json.calls }}\nBy max risk: {{ JSON.stringify($json.by_risk) }}\nSecrets detected (redacted): {{ $json.secret_detected }}\nHandoffs: {{ $json.handoffs }}\nTickets created: {{ $json.tickets_created }}\nDisputes: {{ $json.disputes }}\nSecurity cases: {{ $json.security_cases }}\nSLA-breached open tickets: {{ $json.sla_breached_open }}"),
    ]
    connections = conn(("Daily 08:00 WAT", [["Fetch Daily Report"]]), ("Fetch Daily Report", [["Email QA Digest"]]))
    return {"name": "ENTIN W3 - Daily QA digest", "nodes": nodes, "connections": connections,
            "settings": {"executionOrder": "v1", "timezone": "Africa/Lagos"}}


STEP_JS = r"""
// Runs on every tool call ElevenLabs makes DURING the conversation.
const tool = ($json.query || {}).tool || '';
const body = $json.body || {};
const LABELS = {
  assess_request:            ['Identity & Risk',        'Understanding the request and checking risk'],
  verify_caller:             ['Identity & Risk',        'Verifying the caller (name, DOB, last 4 digits)'],
  find_transactions:         ['Transactions',           'Searching the account for the transaction the caller described'],
  get_transaction_status:    ['Transactions',           'Checking transfer / reversal status'],
  get_card_status:           ['Cards',                  'Checking card status and last decline'],
  block_card:                ['Cards',                  'Blocking card(s)'],
  get_digital_access_status: ['Digital Banking',        'Checking app login / lock / OTP delivery'],
  create_ticket:             ['Tickets & Disputes',     'Logging a complaint ticket'],
  create_dispute:            ['Tickets & Disputes',     'Logging a dispute'],
  get_ticket_status:         ['Tickets & Disputes',     'Checking an existing complaint'],
  report_security_event:     ['Security & Handoff',     'Recording a security event'],
  request_human_handoff:     ['Security & Handoff',     'Handing over to a human'],
  find_branch_or_atm:        ['Branches & ATMs',        'Finding a branch or ATM'],
};
const [group, step] = LABELS[tool] || ['Unknown', 'Unknown tool'];
// What the caller told the agent, minus identity factors and the token (never logged).
const HIDE = new Set(['verification_token', 'full_name', 'date_of_birth', 'account_last4', 'phone_last4', 'caller_id', 'conversation_id']);
const details = Object.entries(body).filter(([k]) => !HIDE.has(k)).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`).join(' | ');
return [{ json: { tool, group, step, body, conversation_id: body.conversation_id || 'unknown', details: details || (tool === 'verify_caller' ? 'identity factors (hidden)' : '') } }];
"""

REPLY_JS = r"""
// Normalise the API answer into the envelope the agent expects, with a safe fallback if the API is down.
const ctx = $('Which Step?').item.json;
const api = $json;
const reply = (api && typeof api.ok === 'boolean') ? api : {
  ok: false, data: null, risk_level: 'LOW', next_actions: ['offer_human'],
  say: "I'm having trouble reaching that information right now. I can log a callback or connect you to a colleague.",
  error: { code: 'UPSTREAM_UNAVAILABLE', retryable: true, say: "I'm having trouble reaching that information right now." },
};
return [{ json: {
  reply,
  log: {
    timestamp: new Date().toISOString(),
    conversation_id: ctx.conversation_id,
    group: ctx.group,
    step: ctx.step,
    caller_details: ctx.details,
    result: reply.ok ? 'ok' : (reply.error && reply.error.code) || 'error',
    agent_says: reply.say || '',
    risk_level: reply.risk_level || '',
    next_actions: (reply.next_actions || []).join(', '),
  },
} }];
"""

LOG_COLUMNS = ["timestamp", "conversation_id", "group", "step", "caller_details", "result", "agent_says", "risk_level", "next_actions"]


def live_call_tools():
    groups = ["Identity & Risk", "Transactions", "Cards", "Digital Banking", "Tickets & Disputes", "Security & Handoff", "Branches & ATMs"]
    rules = [{"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
                             "conditions": [{"id": f"g{i}", "leftValue": "={{ $json.group }}", "rightValue": g,
                                             "operator": {"type": "string", "operation": "equals"}}],
                             "combinator": "and"},
              "renameOutput": True, "outputKey": g} for i, g in enumerate(groups)]
    lookup_names = {g: f"ENTIN API: {g}" for g in groups}
    nodes = [
        node("ElevenLabs Tool Call", "n8n-nodes-base.webhook", 2, [0, 400],
             {"httpMethod": "POST", "path": "entin-tool", "authentication": "headerAuth",
              "responseMode": "responseNode", "options": {}},
             webhookId="entin-live-tool", credentials={"httpHeaderAuth": {"id": "REPLACE", "name": "ENTIN Webhook Auth"}}),
        node("Which Step?", "n8n-nodes-base.code", 2, [220, 400], {"jsCode": STEP_JS}),
        node("Route by Topic", "n8n-nodes-base.switch", 3.2, [440, 400],
             {"rules": {"values": rules}, "options": {"fallbackOutput": "extra"}}),
    ]
    for i, g in enumerate(groups):
        n = http_api(lookup_names[g], [700, 80 + i * 110], "POST", "/v1/tools/{{ $json.tool }}", "={{ JSON.stringify($json.body) }}")
        n["onError"] = "continueRegularOutput"
        n["parameters"]["options"] = {"timeout": 8000, "response": {"response": {"neverError": True}}}
        nodes.append(n)
    nodes += [
        node("Build Reply", "n8n-nodes-base.code", 2, [980, 400], {"jsCode": REPLY_JS}),
        node("Reply to ElevenLabs", "n8n-nodes-base.respondToWebhook", 1.1, [1200, 400],
             {"respondWith": "json", "responseBody": "={{ JSON.stringify($json.reply) }}", "options": {}}),
        node("Log Step to Google Sheet", "n8n-nodes-base.googleSheets", 4.7, [1420, 400], {
            "operation": "append",
            "documentId": {"__rl": True, "mode": "url", "value": "={{ $env.ENTIN_CALL_LOG_SHEET_URL }}"},
            "sheetName": {"__rl": True, "mode": "name", "value": "Call Log"},
            "columns": {"mappingMode": "defineBelow",
                        "value": {c: f"={{{{ $('Build Reply').item.json.log.{c} }}}}" for c in LOG_COLUMNS},
                        "schema": [{"id": c, "displayName": c, "type": "string", "display": True, "required": False,
                                    "defaultMatch": False, "canBeUsedToMatch": True} for c in LOG_COLUMNS],
                        "matchingColumns": [], "attemptToConvertTypes": False, "convertFieldsToString": False},
            "options": {}},
             credentials={"googleSheetsOAuth2Api": {"id": "REPLACE", "name": "Google Sheets account"}},
             onError="continueRegularOutput"),
    ]
    route_outputs = [[lookup_names[g]] for g in groups] + [["Build Reply"]]  # unknown tool -> fallback reply
    pairs = [("ElevenLabs Tool Call", [["Which Step?"]]), ("Which Step?", [["Route by Topic"]]),
             ("Route by Topic", route_outputs)]
    pairs += [(lookup_names[g], [["Build Reply"]]) for g in groups]
    pairs += [("Build Reply", [["Reply to ElevenLabs"]]), ("Reply to ElevenLabs", [["Log Step to Google Sheet"]])]
    return {"name": "ENTIN W0 - Live call tools (ElevenLabs -> n8n -> API -> Sheet log)", "nodes": nodes,
            "connections": conn(*pairs), "settings": {"executionOrder": "v1"}}


if __name__ == "__main__":
    for fname, wf in (("w0-live-call-tools.json", live_call_tools()),("w1-post-call-ingestion.json", post_call()), ("w2-escalation-router.json", events_router()),
                      ("w3-daily-qa-digest.json", daily_digest())):
        (OUT / fname).write_text(json.dumps(wf, indent=2) + "\n")
        print("wrote", fname)
