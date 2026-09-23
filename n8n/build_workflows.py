"""Build the ENTIN n8n workflows (Google Sheets = the bank's database) as importable JSON.

    python n8n/build_workflows.py
    ENTIN_BANK_SHEET_URL=https://docs.google.com/spreadsheets/d/... python n8n/build_workflows.py   # bake your sheet URL in

Outputs n8n/*.json:
  1-live-call-tools.json      ElevenLabs calls this DURING the conversation (13 webhooks, one per tool)
  2-post-call-summary.json    ElevenLabs post-call webhook -> Sessions tab (+ QA email)
  3-bank-activity.json        every 5 min: new transactions + balances (keeps the bank alive)
  4-daily-digest.json         08:00 WAT email summary
  5-reset-demo.json           run before a demo: re-anchors scenario dates, un-blocks scenario cards
Code-node logic lives in n8n/src (tested by n8n/test/run_tests.mjs).
"""
import json
import os
import pathlib

HERE = pathlib.Path(__file__).parent
SRC = HERE / "src"
LIB = (SRC / "lib.js").read_text()
SHEET_URL = os.environ.get("ENTIN_BANK_SHEET_URL", "https://docs.google.com/spreadsheets/d/1Dr7c9_2wfoYQNxc67Vus-Rg7iNERS8rhC065zd7p30Q/edit")
ALERT_EMAIL = os.environ.get("ENTIN_ALERT_EMAIL", "nwanduben@gmail.com")
WEBHOOK_SECRET_PLACEHOLDER = "PASTE_ELEVENLABS_WEBHOOK_SECRET_HERE"
DOC = {"__rl": True, "mode": "url", "value": SHEET_URL or "={{ $env.ENTIN_BANK_SHEET_URL }}"}
GS_CRED = {"googleSheetsOAuth2Api": {"id": "REPLACE", "name": "Google Sheets account"}}
SMTP_CRED = {"smtp": {"id": "REPLACE", "name": "ENTIN SMTP"}}


def js(path: str, with_lib: bool = True) -> str:
    body = (SRC / path).read_text()
    return (LIB + "\n" + body) if with_lib else body


def node(name, type_, version, pos, params, **extra):
    n = {"parameters": params, "name": name, "type": type_, "typeVersion": version, "position": pos}
    n.update(extra)
    return n


def code(name, pos, path, with_lib=True):
    return node(name, "n8n-nodes-base.code", 2, pos, {"jsCode": js(path, with_lib)})


def sheet(tab):
    return {"__rl": True, "mode": "name", "value": tab}


def gs_read(name, pos, tab, filter_col=None, filter_expr=None, once=False):
    p = {"operation": "read", "documentId": DOC, "sheetName": sheet(tab), "options": {}}
    if filter_col:
        p["filtersUI"] = {"values": [{"lookupColumn": filter_col, "lookupValue": filter_expr}]}
    extra = {"credentials": GS_CRED, "alwaysOutputData": True}
    if once:
        extra["executeOnce"] = True
    return node(name, "n8n-nodes-base.googleSheets", 4.7, pos, p, **extra)


def gs_write(name, pos, tab, op, match=None, once=False):
    p = {"operation": op, "documentId": DOC, "sheetName": sheet(tab),
         "columns": {"mappingMode": "autoMapInputData", "value": {}, "matchingColumns": [match] if match else [], "schema": []},
         "options": {}}
    if op in ("append", "appendOrUpdate"):
        p["options"] = {"handlingExtraData": "ignoreIt"}
    extra = {"credentials": GS_CRED}
    if once:
        extra["executeOnce"] = True
    return node(name, "n8n-nodes-base.googleSheets", 4.7, pos, p, **extra)


def if_true(name, pos, expr):
    return node(name, "n8n-nodes-base.if", 2.2, pos, {
        "conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                       "conditions": [{"id": name.lower().replace(" ", "-").replace("?", ""), "leftValue": expr, "rightValue": "",
                                       "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
                       "combinator": "and"},
        "looseTypeValidation": True, "options": {}})


def branded(body_file, kicker, footer=""):
    shell = (SRC / "email" / "shell.html").read_text()
    body = (SRC / "email" / body_file).read_text()
    return "=" + (shell.replace("__KICKER__", kicker).replace("__BODY__", body).replace("__FOOTER__", footer)
                  .replace("__SHEET_URL__", SHEET_URL))


def email(name, pos, subject, text, html=None):
    p = {"fromEmail": f"ENTIN Bank Operations <{ALERT_EMAIL}>", "toEmail": ALERT_EMAIL, "subject": subject,
         "options": {"appendAttribution": False}}
    if html:
        p.update({"emailFormat": "html", "html": html})
    else:
        p.update({"emailFormat": "text", "text": text})
    return node(name, "n8n-nodes-base.emailSend", 2.1, pos, p, credentials=SMTP_CRED)


def connect(pairs):
    out = {}
    for src, outputs in pairs:
        out[src] = {"main": [[{"node": t, "type": "main", "index": 0} for t in targets] for targets in outputs]}
    return out


def sticky(text, pos, w=420, h=200, color=5):
    return node("About This Workflow", "n8n-nodes-base.stickyNote", 1, pos, {"content": text, "width": w, "height": h, "color": color})


CTX = "$('Which Step?').first().json"


# ---------------------------------------------------------------- 1. live call tools
def live_call_tools():
    X = [0, 240, 480, 760, 1040, 1320, 1600, 1880, 2160]  # columns
    nodes, pairs = [], []
    tools = ["assess_request", "verify_caller", "find_transactions", "get_transaction_status", "get_card_status", "block_card",
             "get_digital_access_status", "create_ticket", "create_dispute", "get_ticket_status", "report_security_event",
             "request_human_handoff", "find_branch_or_atm", "blocked"]
    X[0] = -300
    hooks = [node(f"Webhook: {t}", "n8n-nodes-base.webhook", 2, [X[0], 80 + i * 170],
                  {"httpMethod": "POST", "path": f"entin/{t}", "authentication": "headerAuth", "responseMode": "responseNode", "options": {}},
                  webhookId=f"entin-{t.replace('_', '-')}", credentials={"httpHeaderAuth": {"id": "REPLACE", "name": "ENTIN Webhook Auth"}})
             for i, t in enumerate(tools[:-1])]
    nodes += hooks + [
        gs_read("Load Session", [X[1], 1200], "Sessions", "conversation_id", "={{ $json.body.conversation_id }}"),
        code("Which Step?", [X[2], 1200], "live/which_step.js"),
    ]
    rules = [{"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
                             "conditions": [{"id": f"r{i}", "leftValue": "={{ $json.route }}", "rightValue": t,
                                             "operator": {"type": "string", "operation": "equals"}}], "combinator": "and"},
              "renameOutput": True, "outputKey": t} for i, t in enumerate(tools)]
    nodes.append(node("Route by Tool", "n8n-nodes-base.switch", 3.2, [X[3] - 60, 1200], {"rules": {"values": rules}, "options": {}}))

    cust = f"={{{{ {CTX}.session.customer_id }}}}"
    body = lambda f: f"={{{{ {CTX}.body.{f} }}}}"  # noqa: E731
    Y = lambda i: 80 + i * 170  # noqa: E731
    first = {}  # first node of each branch

    def chain(i, *ns):
        for k, n in enumerate(ns):
            n["position"] = [X[4] + k * 260, Y(i)]
            nodes.append(n)
        for a, b in zip(ns, ns[1:]):
            pairs.append((a["name"], [[b["name"]]]))
        first[tools[i]] = ns[0]["name"]
        return ns[-1]["name"]

    ends = []
    ends.append(chain(0, code("Assess Risk", [0, 0], "live/assess.js")))
    ends.append(chain(1, gs_read("Read Customers", [0, 0], "Customers"), gs_read("Read Accounts", [0, 0], "Accounts", once=True),
                      code("Check Identity", [0, 0], "live/check_identity.js")))
    ends.append(chain(2, gs_read("Read Customer Transactions", [0, 0], "Transactions", "customer_id", cust),
                      code("Match Transactions", [0, 0], "live/match_transactions.js")))
    ends.append(chain(3, gs_read("Read Transaction", [0, 0], "Transactions", "txn_id", body("txn_id")),
                      gs_read("Read Related Tickets", [0, 0], "Tickets", "linked_txn_id", body("txn_id"), once=True),
                      code("Work Out Status", [0, 0], "live/txn_status.js")))
    ends.append(chain(4, gs_read("Read Customer Cards", [0, 0], "Cards", "customer_id", cust), code("Explain Card", [0, 0], "live/card_status.js")))
    # block_card has a yes/no split
    chain(5, gs_read("Read Cards To Block", [0, 0], "Cards", "customer_id", cust), code("Choose Cards", [0, 0], "live/choose_cards.js"),
          if_true("Cards Found?", [0, 0], "={{ $json.proceed }}"))
    blk = [code("Card Updates", [0, 0], "live/card_updates.js"), gs_write("Update Card Status", [0, 0], "Cards", "update", "card_id"),
           code("Replacement Ticket Row", [0, 0], "live/replacement_ticket_row.js"), gs_write("Add Replacement Ticket", [0, 0], "Tickets", "append"),
           code("Card Blocked Reply", [0, 0], "live/card_blocked_reply.js")]
    for k, n in enumerate(blk):
        n["position"] = [X[4] + (3 + k) * 260, Y(5) - 60]
        nodes.append(n)
    pairs.append(("Cards Found?", [["Card Updates"], ["Build Reply"]]))
    for a, b in zip(blk, blk[1:]):
        pairs.append((a["name"], [[b["name"]]]))
    ends.append("Card Blocked Reply")
    ends.append(chain(6, gs_read("Read Digital Access", [0, 0], "Digital Access", "customer_id", cust), code("Explain Access", [0, 0], "live/digital.js")))
    ends.append(chain(7, code("New Ticket Row", [0, 0], "live/new_ticket_row.js"), gs_write("Add Ticket", [0, 0], "Tickets", "append"),
                      code("Ticket Reply", [0, 0], "live/ticket_reply.js")))
    chain(8, gs_read("Read Disputed Transaction", [0, 0], "Transactions", "txn_id", body("txn_id")), code("Check Dispute", [0, 0], "live/check_dispute.js"),
          if_true("Dispute OK?", [0, 0], "={{ $json.proceed }}"))
    dsp = [code("Dispute Ticket Row", [0, 0], "live/dispute_ticket_row.js"), gs_write("Add Dispute Ticket", [0, 0], "Tickets", "append"),
           code("Dispute Row", [0, 0], "live/dispute_row.js"), gs_write("Add Dispute", [0, 0], "Disputes", "append"),
           code("Dispute Reply", [0, 0], "live/dispute_reply.js")]
    for k, n in enumerate(dsp):
        n["position"] = [X[4] + (3 + k) * 260, Y(8) - 60]
        nodes.append(n)
    pairs.append(("Dispute OK?", [["Dispute Ticket Row"], ["Build Reply"]]))
    for a, b in zip(dsp, dsp[1:]):
        pairs.append((a["name"], [[b["name"]]]))
    ends.append("Dispute Reply")
    ends.append(chain(9, gs_read("Read Customer Tickets", [0, 0], "Tickets", "customer_id", cust),
                      gs_read("Read Customer Disputes", [0, 0], "Disputes", "customer_id", cust, once=True),
                      code("Ticket Progress", [0, 0], "live/ticket_progress.js")))
    ends.append(chain(10, code("Record Security Event", [0, 0], "live/security_event.js")))
    ends.append(chain(11, code("Prepare Handoff", [0, 0], "live/handoff.js")))
    ends.append(chain(12, gs_read("Read Branches", [0, 0], "Branches & ATMs"), code("Nearest Branch", [0, 0], "live/nearest_branch.js")))
    first["blocked"] = "Build Reply"

    pairs = [(h["name"], [["Load Session"]]) for h in hooks] + [("Load Session", [["Which Step?"]]), ("Which Step?", [["Route by Tool"]]),
             ("Route by Tool", [[first[t]] for t in tools])] + pairs
    pairs += [(e, [["Build Reply"]]) for e in ends]

    tail_x = X[4] + 8 * 260
    tail = [code("Build Reply", [tail_x, 1200], "live/build_reply.js"),
            node("Reply to ElevenLabs", "n8n-nodes-base.respondToWebhook", 1.1, [tail_x + 240, 1200],
                 {"respondWith": "json", "responseBody": "={{ JSON.stringify($json.reply) }}", "options": {}}),
            code("Session Row", [tail_x + 480, 1200], "live/session_row.js", False),
            gs_write("Save Session", [tail_x + 720, 1200], "Sessions", "appendOrUpdate", "conversation_id"),
            code("Log Row", [tail_x + 960, 1200], "live/log_row.js", False),
            gs_write("Log Call Step", [tail_x + 1200, 1200], "Call Log", "append")]
    nodes += tail
    for a, b in zip(tail, tail[1:]):
        pairs.append((a["name"], [[b["name"]]]))
    nodes += [code("Security Case Row", [tail_x + 1440, 1080], "live/security_case_row.js", False),
              gs_write("Add Security Case", [tail_x + 1680, 1080], "Security Cases", "append"),
              code("Escalation Row", [tail_x + 1440, 1320], "live/escalation_row.js", False),
              gs_write("Add Escalation", [tail_x + 1680, 1320], "Escalations", "append"),
              email("Alert Human Team", [tail_x + 1920, 1320],
                    "=[{{ $json.priority }} · {{ $json.risk_level }}] Customer handoff · {{ $('Build Reply').first().json.session.customer_name || 'Unverified caller' }} · {{ $json.handoff_id }}",
                    "=ENTIN Bank - customer handoff {{ $json.handoff_id }}\nPriority: {{ $json.priority }} ({{ $json.risk_level }} risk)\nCustomer: {{ $('Build Reply').first().json.session.customer_name || 'Caller not verified' }} {{ $json.customer_id }}\nTeam: {{ $json.queue }}\nReason: {{ $json.reason }}\nType: {{ $json.mode }}\nSummary: {{ $json.summary }}\n\nSynthetic demo data only.",
                    branded("handoff_body.html", "Customer Operations &middot; Handoff alert",
                            "Conversation <span style=\"font-family:Menlo,Consolas,monospace;\">{{ $json.conversation_id }}</span><br>"))]
    nodes[-1]["onError"] = "continueRegularOutput"
    pairs += [("Log Call Step", [["Security Case Row", "Escalation Row"]]), ("Security Case Row", [["Add Security Case"]]),
              ("Escalation Row", [["Add Escalation"]]), ("Add Escalation", [["Alert Human Team"]])]
    nodes.append(sticky("## ENTIN live call tools\nElevenLabs calls one of the **13 webhooks on the left** during the call, one per tool, e.g. `/webhook/entin/verify_caller`.\n\n"
                        "1. Load the call's session from the **Sessions** tab\n2. **Which Step?** blocks secrets (PIN/OTP/CVV/password/card no.) and checks the caller is verified enough\n"
                        "3. Each tool reads/writes the Google Sheet\n4. **Build Reply** answers ElevenLabs, then the session, call log, security cases and handoffs are saved",
                        [-340, -260], 560, 300, 4))
    return {"name": "ENTIN 1 - Live call tools (Google Sheets bank)", "nodes": nodes, "connections": connect(pairs),
            "settings": {"executionOrder": "v1"}}


# ---------------------------------------------------------------- 2. post-call summary
def post_call():
    nodes = [
        node("ElevenLabs Post-call Webhook", "n8n-nodes-base.webhook", 2, [0, 300],
             {"httpMethod": "POST", "path": "entin-post-call", "responseMode": "responseNode", "options": {"rawBody": True}},
             webhookId="entin-post-call"),
        code("Prepare Signature Check", [220, 300], "other/prepare_signature.js", False),
        node("HMAC with ElevenLabs Secret", "n8n-nodes-base.crypto", 1, [440, 300],
             {"action": "hmac", "type": "SHA256", "value": "={{ $json.signed_payload }}", "dataPropertyName": "expected",
              "secret": WEBHOOK_SECRET_PLACEHOLDER, "encoding": "hex"}),
        code("Check Signature", [660, 300], "other/check_signature.js", False),
        if_true("Signature Valid?", [880, 300], "={{ $json.valid }}"),
        node("Reject 401", "n8n-nodes-base.respondToWebhook", 1.1, [1100, 460],
             {"respondWith": "json", "responseBody": '={"ok": false}', "options": {"responseCode": 401}}),
        code("Redact & Summarise", [1100, 200], "other/outcome_row.js", False),
        gs_write("Save Call Summary", [1320, 200], "Sessions", "appendOrUpdate", "conversation_id"),
        node("Respond 200", "n8n-nodes-base.respondToWebhook", 1.1, [1540, 200], {"respondWith": "json", "responseBody": '={"ok": true}', "options": {}}),
        if_true("Needs QA Alert?", [1760, 200], "={{ $('Redact & Summarise').first().json.needs_qa_alert }}"),
        email("Email QA Alert", [1980, 120], "=[Quality review] ENTIN call {{ $json.conversation_id }}",
              "=Secret spoken on call: {{ $json.secret_detected }}\nFailed checks: {{ $json.failed_evaluations || 'none' }}\nSummary (redacted): {{ $json.call_summary }}",
              branded("qa_body.html", "Quality Assurance &middot; Call review",
                      "Conversation <span style=\"font-family:Menlo,Consolas,monospace;\">{{ $json.conversation_id }}</span><br>")),
    ]
    pairs = [("ElevenLabs Post-call Webhook", [["Prepare Signature Check"]]), ("Prepare Signature Check", [["HMAC with ElevenLabs Secret"]]),
             ("HMAC with ElevenLabs Secret", [["Check Signature"]]), ("Check Signature", [["Signature Valid?"]]),
             ("Signature Valid?", [["Redact & Summarise"], ["Reject 401"]]), ("Redact & Summarise", [["Save Call Summary"]]),
             ("Save Call Summary", [["Respond 200"]]), ("Respond 200", [["Needs QA Alert?"]]), ("Needs QA Alert?", [["Email QA Alert"], []])]
    return {"name": "ENTIN 2 - Post-call summary", "nodes": nodes, "connections": connect(pairs), "settings": {"executionOrder": "v1"}}


# ---------------------------------------------------------------- 3. bank activity
def bank_activity():
    nodes = [
        node("Every 5 Minutes", "n8n-nodes-base.scheduleTrigger", 1.2, [0, 300], {"rule": {"interval": [{"field": "minutes", "minutesInterval": 5}]}}),
        gs_read("Read Accounts", [240, 300], "Accounts"),
        code("Generate Activity", [480, 300], "other/generate_activity.js"),
        gs_write("Add Transactions", [720, 300], "Transactions", "append"),
        code("New Balances", [960, 300], "other/new_balances.js", False),
        gs_write("Update Balances", [1200, 300], "Accounts", "update", "account_number"),
    ]
    pairs = [(a["name"], [[b["name"]]]) for a, b in zip(nodes, nodes[1:])]
    return {"name": "ENTIN 3 - Bank activity simulator", "nodes": nodes, "connections": connect(pairs),
            "settings": {"executionOrder": "v1", "timezone": "Africa/Lagos"}}


# ---------------------------------------------------------------- 4. daily digest
def daily_digest():
    nodes = [
        node("Daily 08:00 WAT", "n8n-nodes-base.scheduleTrigger", 1.2, [0, 300], {"rule": {"interval": [{"field": "cronExpression", "expression": "0 8 * * *"}]}}),
        gs_read("Read Sessions", [240, 300], "Sessions"),
        gs_read("Read Escalations", [480, 300], "Escalations", once=True),
        gs_read("Read Security Cases", [720, 300], "Security Cases", once=True),
        gs_read("Read Tickets", [960, 300], "Tickets", once=True),
        code("Build Digest", [1200, 300], "other/digest.js"),
        email("Email Digest", [1440, 300], "={{ $json.subject }}", "={{ $json.text }}",
              branded("digest_body.html", "Customer Operations &middot; Daily report")),
    ]
    pairs = [(a["name"], [[b["name"]]]) for a, b in zip(nodes, nodes[1:])]
    return {"name": "ENTIN 4 - Daily digest", "nodes": nodes, "connections": connect(pairs),
            "settings": {"executionOrder": "v1", "timezone": "Africa/Lagos"}}


# ---------------------------------------------------------------- 5. reset demo
def reset_demo():
    tabs = [("Transactions", "txn_id"), ("Cards", "card_id"), ("Digital Access", "customer_id"), ("Tickets", "ticket_id")]
    nodes = [node("Run Before Demo", "n8n-nodes-base.manualTrigger", 1, [0, 300], {}),
             gs_read("Read Demo Scenarios", [240, 300], "Demo Scenarios"),
             code("Compute Resets", [480, 300], "other/compute_resets.js")]
    pairs = [("Run Before Demo", [["Read Demo Scenarios"]]), ("Read Demo Scenarios", [["Compute Resets"]])]
    fan = []
    for i, (tab, key) in enumerate(tabs):
        pick = f"{tab} Rows"
        nodes.append(node(pick, "n8n-nodes-base.code", 2, [760, 120 + i * 160], {"jsCode":
            f"return $input.all().map(i => i.json).filter(r => r.tab === {json.dumps(tab)})"
            f".map(({{ tab, ...rest }}) => ({{ json: rest }}));"}))
        nodes.append(gs_write(f"Reset {tab}", [1000, 120 + i * 160], tab, "update", key))
        fan.append(pick)
        pairs.append((pick, [[f"Reset {tab}"]]))
    pairs.append(("Compute Resets", [fan]))
    return {"name": "ENTIN 5 - Reset demo scenarios", "nodes": nodes, "connections": connect(pairs), "settings": {"executionOrder": "v1"}}


WORKFLOWS = {"1-live-call-tools.json": live_call_tools, "2-post-call-summary.json": post_call, "3-bank-activity.json": bank_activity,
             "4-daily-digest.json": daily_digest, "5-reset-demo.json": reset_demo}

if __name__ == "__main__":
    for fname, fn in WORKFLOWS.items():
        wf = fn()
        (HERE / fname).write_text(json.dumps(wf, indent=2) + "\n")
        print(f"wrote {fname:28s} {len(wf['nodes'])} nodes")
