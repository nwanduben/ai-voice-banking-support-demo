// Redact the transcript and turn ElevenLabs' post-call analysis into a Sessions row update.
const WORDS = '(?:pin|otp|one[\\s-]?time|cvv|cvc|security\\s+code|passcode|password|token|auth(?:entication)?\\s+code)';
const PAN = /(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)/g;
const AFTER = new RegExp(WORDS + '\\W+(?:\\w+\\W+){0,3}?(\\d[\\d ]{2,9}\\d|\\d{3,8})', 'gi');
const BEFORE = new RegExp('(?<!\\d)(\\d{3,8})(?!\\d)\\W+(?:\\w+\\W+){0,2}?(?:is\\s+)?(?:my\\s+)?' + WORDS, 'gi');
const PWD = /(?:password|passcode)\s+(?:is|na)\s+(\S+)/gi;
let found = false;
const redact = (t) => String(t || '')
  .replace(PAN, () => { found = true; return '[REDACTED_CARD]'; })
  .replace(AFTER, (m, code) => { found = true; return m.replace(code, '[REDACTED_CODE]'); })
  .replace(BEFORE, (m, code) => { found = true; return m.replace(code, '[REDACTED_CODE]'); })
  .replace(PWD, (m, pw) => { found = true; return m.replace(pw, '[REDACTED_PASSWORD]'); });
const d = ($input.first().json.body || {}).data || {};
const a = d.analysis || {};
(d.transcript || []).forEach((t) => redact(t.message)); // detection only; the transcript itself is not stored
const summary = redact(a.transcript_summary);
const failed = Object.entries(a.evaluation_criteria_results || {}).filter(([, v]) => v && v.result === 'failure').map(([k]) => k);
return [{ json: { conversation_id: d.conversation_id, call_summary: summary.slice(0, 1000), secret_detected: found ? 'yes' : 'no',
  failed_evaluations: failed.join(', '), needs_qa_alert: found || failed.length > 0 } }];
