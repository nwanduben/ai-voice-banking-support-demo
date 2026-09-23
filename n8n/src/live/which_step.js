// Every tool call ElevenLabs makes during the conversation lands here first.
// Each tool has its own webhook node ("Webhook: verify_caller", ...); find the one that fired.
const TOOL_NAMES = ['assess_request', 'verify_caller', 'find_transactions', 'get_transaction_status', 'get_card_status', 'block_card',
  'get_digital_access_status', 'create_ticket', 'create_dispute', 'get_ticket_status', 'report_security_event', 'request_human_handoff', 'find_branch_or_atm'];
const tool = TOOL_NAMES.find((t) => $(`Webhook: ${t}`).isExecuted) || '';
const hook = tool ? $(`Webhook: ${tool}`).first().json : {};
const body = hook.body || {};
const conv = String(body.conversation_id || 'unknown');
const s = rowsOf('Load Session')[0] || {};
const session = {
  conversation_id: conv, customer_id: s.customer_id || '', customer_name: s.customer_name || '', tier: s.tier || 'T0',
  verified_at: s.verified_at || '', failed_attempts: Number(s.failed_attempts || 0), locked: yes(s.locked) ? 'yes' : 'no',
  max_risk: s.max_risk || 'LOW', intents: s.intents || '', secret_detected: s.secret_detected || 'no',
};
let expired = false;
if (session.tier !== 'T0' && (!parseWAT(session.verified_at) || nowDate() - parseWAT(session.verified_at) > VERIFY_TTL_MIN * 60e3)) {
  session.tier = 'T0'; expired = true;
}
const LABELS = {
  assess_request: ['Identity & Risk', 'Understanding the request and checking risk'],
  verify_caller: ['Identity & Risk', 'Verifying the caller against the Customers tab'],
  find_transactions: ['Transactions', 'Searching the Transactions tab for what the caller described'],
  get_transaction_status: ['Transactions', 'Checking transfer / reversal status'],
  get_card_status: ['Cards', 'Checking card status and last decline'],
  block_card: ['Cards', 'Blocking card(s) in the Cards tab'],
  get_digital_access_status: ['Digital Banking', 'Checking app login / lock / OTP delivery'],
  create_ticket: ['Tickets & Disputes', 'Adding a complaint to the Tickets tab'],
  create_dispute: ['Tickets & Disputes', 'Adding a dispute to the Disputes tab'],
  get_ticket_status: ['Tickets & Disputes', 'Checking an existing complaint'],
  report_security_event: ['Security & Handoff', 'Recording a security event'],
  request_human_handoff: ['Security & Handoff', 'Handing over to a human'],
  find_branch_or_atm: ['Branches & ATMs', 'Finding a branch or ATM'],
};
const [group, step] = LABELS[tool] || ['Unknown', 'Unknown tool'];

// Secret guard: reject any request whose free text carries a PIN, OTP, CVV, password or card number.
const WORDS = '(?:pin|otp|one[\\s-]?time|cvv|cvc|security\\s+code|passcode|password|token|auth(?:entication)?\\s+code)';
const PAN = /(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)/;
const AFTER = new RegExp(WORDS + '\\W+(?:\\w+\\W+){0,3}?(\\d[\\d ]{2,9}\\d|\\d{3,8})', 'i');
const BEFORE = new RegExp('(?<!\\d)(\\d{3,8})(?!\\d)\\W+(?:\\w+\\W+){0,2}?(?:is\\s+)?(?:my\\s+)?' + WORDS, 'i');
const PWD = /(?:password|passcode)\s+(?:is|na)\s+(\S+)/i;
const kindOf = (t) => {
  if (PAN.test(t)) return 'card_number';
  const m = t.match(AFTER) || t.match(BEFORE);
  if (m) {
    const w = m[0].match(new RegExp(WORDS, 'i'))[0].toLowerCase();
    if (w.startsWith('pin')) return 'pin';
    if (w.startsWith('otp') || w.startsWith('one')) return 'otp';
    if (w.startsWith('cvv') || w.startsWith('cvc') || w.startsWith('security')) return 'cvv';
    if (w.startsWith('pass')) return 'password';
    return 'token';
  }
  return PWD.test(t) ? 'password' : null;
};
const STRUCTURED = new Set(['conversation_id', 'date_of_birth', 'account_last4', 'phone_last4', 'card_last4', 'txn_id', 'reference',
  'date_from', 'date_to', 'amount_naira_approx', 'amount_naira']);
let secret = null;
for (const [k, v] of Object.entries(body)) {
  if (STRUCTURED.has(k)) continue;
  for (const x of (Array.isArray(v) ? v : [v])) if (!secret && typeof x === 'string') secret = kindOf(x);
}
const SHAPES = { account_last4: /^\d{4}$/, phone_last4: /^\d{4}$/, card_last4: /^\d{4}$/ };
const badShape = Object.entries(SHAPES).some(([k, re]) => body[k] !== undefined && body[k] !== null && body[k] !== '' && !re.test(String(body[k])));

let blocked = null, security_case = null, blocked_update = {};
if (secret) {
  blocked = fail('SENSITIVE_DATA_REJECTED', "Please stop there. For your safety, don't share that with anyone, including me. ENTIN Bank will never ask for your PIN, OTP, password or card number.");
  security_case = { case_id: newId('SEC'), conversation_id: conv, customer_id: session.customer_id, type: 'sensitive_disclosure', secret_kind: secret, created_at: fmtWAT(nowDate()) };
  blocked_update = { max_risk: 'HIGH', intents_add: 'SENSITIVE_INFO_DISCLOSED', secret_detected: 'yes' };
} else if (!LABELS[tool]) {
  blocked = fail('NOT_FOUND', "Sorry, I can't do that here.");
} else if (badShape) {
  blocked = fail('VALIDATION_ERROR', "Sorry, I didn't catch that in the right format. Could you say the four digits again?", []);
} else if (TOOL_TIER[tool] !== 'T0' && session.locked === 'yes') {
  blocked = fail('VERIFICATION_LOCKED', "I'm not able to access account details on this call. Let me connect you to a colleague.");
} else if (tierRank(session.tier) < tierRank(TOOL_TIER[tool])) {
  blocked = fail(expired ? 'VERIFICATION_EXPIRED' : 'VERIFICATION_REQUIRED',
    expired ? 'For your security I need to confirm your details again.'
      : session.tier === 'T0' ? "Before I can check that, I need to confirm who I'm speaking with." : "To look at that I need a couple more details to confirm it's you.",
    ['verify_caller']);
}
const HIDE = new Set(['full_name', 'date_of_birth', 'account_last4', 'phone_last4', 'conversation_id']);
const details = secret ? `[${secret} shared by caller - value not logged]`
  : Object.entries(body).filter(([k]) => !HIDE.has(k)).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`).join(' | ')
    || (tool === 'verify_caller' ? 'identity details (hidden)' : '');
return [{ json: { tool, route: blocked ? 'blocked' : tool, group, step, body, conv, session, details, blocked, security_case, blocked_update } }];
