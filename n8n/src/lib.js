// ===== ENTIN shared rules (copied into every Code node by build_workflows.py) =====
const LEVELS = ['LOW', 'MEDIUM', 'HIGH'];
// intent: [base risk, required tier, escalation queue]
const INTENTS = {
  FAQ_GENERAL: ['LOW', 'T0', 'general'], BRANCH_SERVICE_INFO: ['LOW', 'T0', 'general'],
  TRANSFER_FAILED: ['MEDIUM', 'T2', 'general'], TRANSFER_DEBITED_NOT_RECEIVED: ['MEDIUM', 'T2', 'general'],
  TRANSACTION_PENDING: ['MEDIUM', 'T2', 'general'], REVERSAL_STATUS: ['MEDIUM', 'T2', 'complaints'],
  UNAUTHORIZED_TRANSACTION: ['HIGH', 'T1', 'fraud'], ATM_CASH_DISPUTE: ['HIGH', 'T2', 'disputes'],
  POS_DISPUTE: ['MEDIUM', 'T2', 'disputes'], CARD_DECLINED: ['MEDIUM', 'T2', 'cards'],
  CARD_LOST_STOLEN: ['HIGH', 'T1', 'fraud'], MOBILE_LOGIN_ISSUE: ['MEDIUM', 'T1', 'digital'],
  DIGITAL_PROFILE_LOCKED: ['MEDIUM', 'T2', 'digital'], CREDENTIAL_RESET_GUIDANCE: ['LOW', 'T0', 'digital'],
  OTP_NOT_RECEIVED: ['MEDIUM', 'T1', 'digital'], COMPLAINT_TICKET_STATUS: ['MEDIUM', 'T1', 'complaints'],
  ACCOUNT_RESTRICTION: ['HIGH', 'T2', 'compliance'], SUSPECTED_FRAUD_SCAM: ['HIGH', 'T1', 'fraud'],
  HUMAN_AGENT_REQUEST: ['LOW', 'T0', 'general'], SENSITIVE_INFO_DISCLOSED: ['HIGH', 'T0', 'fraud'],
  VERIFICATION_FAILED: ['HIGH', 'T0', 'fraud'], PROHIBITED_REQUEST: ['HIGH', 'T0', 'fraud'],
  OUT_OF_SCOPE_OR_UNCLEAR: ['LOW', 'T0', 'general'],
};
const HIGH_SIGNALS = ['customer_denies_authorisation', 'social_engineering_suspected', 'vulnerable_customer', 'repeat_contact', 'prompt_injection'];
const HIGH_AMOUNT_NAIRA = 1000000;
const REPEAT_CONTACT_THRESHOLD = 3;
// CBN timelines for failed e-transactions, effective 8 June 2020 (Nairametrics report of CBN circular, 31 May 2020).
const WINDOW_HOURS = { ATM_ON_US: 0, ATM_NOT_ON_US: 48, POS: 72, TRANSFER: 72, WEB: 72, USSD: 72 };
const COMPLAINT_SLA_DAYS = 14;
const VERIFY_TTL_MIN = 15;
const TOOL_TIER = {
  assess_request: 'T0', verify_caller: 'T0', report_security_event: 'T0', request_human_handoff: 'T0', find_branch_or_atm: 'T0',
  block_card: 'T1', get_digital_access_status: 'T1', create_ticket: 'T1', get_ticket_status: 'T1',
  find_transactions: 'T2', get_transaction_status: 'T2', get_card_status: 'T2', create_dispute: 'T2',
};
const tierRank = (t) => Number(String(t || 'T0').slice(1)) || 0;
const maxRisk = (...ls) => ls.filter((l) => LEVELS.includes(l)).reduce((a, b) => (LEVELS.indexOf(b) > LEVELS.indexOf(a) ? b : a), 'LOW');

// ----- time (bank runs on West Africa Time, stored as "YYYY-MM-DD HH:MM") -----
const nowDate = () => new Date();
const parseWAT = (v) => {
  if (!v) return null;
  const s = String(v).trim();
  let m = s.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/);
  if (m) return new Date(`${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:00+01:00`);
  m = s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (m) return new Date(`${s}T00:00:00+01:00`);
  const d = new Date(s);
  return isNaN(d) ? null : d;
};
const fmtWAT = (d) => new Date(d.getTime() + 3600e3).toISOString().slice(0, 16).replace('T', ' ');
const watDay = (d) => fmtWAT(d).slice(0, 10);
const hour12 = (d) => { const h = Number(fmtWAT(d).slice(11, 13)); return `${h % 12 || 12} ${h < 12 ? 'AM' : 'PM'}`; };
const spokenWhen = (v) => {
  const d = parseWAT(v); const n = nowDate();
  if (!d) return 'recently';
  const mins = (n - d) / 60000;
  if (mins < 60) return `about ${Math.max(1, Math.round(mins))} minutes ago`;
  if (watDay(d) === watDay(n)) return `today at about ${hour12(d)}`;
  if (watDay(d) === watDay(new Date(n - 86400e3))) return `yesterday at about ${hour12(d)}`;
  return new Date(d.getTime() + 3600e3).toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', timeZone: 'UTC' });
};

// ----- formatting & normalising (Sheets may turn "0001" into 1 or re-format dates) -----
const naira = (n) => `${Math.round(Number(n) || 0).toLocaleString('en-US')} naira`;
const spokenRef = (r) => { const [p, num] = String(r).split('-'); return `${p.split('').join(' ')}, ${String(num || '').split('').join(' ')}`; };
const digits = (v) => String(v ?? '').replace(/\D/g, '');
const last4 = (v) => digits(v).padStart(4, '0').slice(-4);
const normName = (s) => String(s || '').toLowerCase().replace(/[^a-z ]/g, ' ').split(/\s+/).filter(Boolean).join(' ');
const normDob = (v) => {
  const s = String(v || '').trim();
  let m = s.match(/^(\d{4})-(\d{1,2})-(\d{1,2})/);
  if (m) return `${m[1]}-${m[2].padStart(2, '0')}-${m[3].padStart(2, '0')}`;
  m = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/); // DD/MM/YYYY (Nigerian format)
  if (m) return `${m[3]}-${m[2].padStart(2, '0')}-${m[1].padStart(2, '0')}`;
  const d = new Date(s);
  return isNaN(d) ? '' : d.toISOString().slice(0, 10);
};
const yes = (v) => ['yes', 'true', '1'].includes(String(v).toLowerCase());
const newId = (p) => `${p}-${String(Date.now()).slice(-6)}`;
const rowsOf = (name) => $(name).all().map((i) => i.json).filter((r) => r && Object.keys(r).length && !r.error);
const ctx = () => $('Which Step?').first().json;
const ok = (data, say, next = []) => ({ ok: true, data, say, next_actions: next, error: null });
const fail = (code, say, next = ['offer_human']) => ({ ok: false, data: null, say, next_actions: next, error: { code, retryable: false, say } });
const result = (reply, extra = {}) => [{ json: { reply, session_update: {}, security_case: null, escalation: null, ...extra } }];
// ===== end shared rules =====
