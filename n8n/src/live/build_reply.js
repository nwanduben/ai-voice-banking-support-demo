// Merge the branch result into the call session and shape the answer ElevenLabs will speak.
const c = ctx();
const out = $input.first().json;
const res = out.reply ? out : { reply: c.blocked, session_update: c.blocked_update || {}, security_case: c.security_case, escalation: null };
const u = res.session_update || {};
const s = { ...c.session };
for (const k of ['customer_id', 'customer_name', 'tier', 'verified_at', 'failed_attempts', 'locked', 'secret_detected']) if (u[k] !== undefined) s[k] = u[k];
const intents = new Set(String(s.intents || '').split(',').filter(Boolean));
if (u.intents_add) intents.add(u.intents_add);
s.intents = [...intents].join(',');
s.max_risk = maxRisk(s.max_risk, u.max_risk, res.security_case ? 'HIGH' : 'LOW');
s.updated_at = fmtWAT(nowDate());
const reply = { ...res.reply, risk_level: s.max_risk };
const escalation = res.escalation ? { ...res.escalation, risk_level: s.max_risk, priority: { HIGH: 'P1', MEDIUM: 'P2', LOW: 'P3' }[s.max_risk] } : null;
const log = { timestamp: fmtWAT(nowDate()), conversation_id: c.conv, group: c.group, step: c.step, caller_details: c.details,
  result: reply.ok ? 'ok' : (reply.error && reply.error.code) || 'error', agent_says: reply.say || '', risk_level: s.max_risk,
  next_actions: (reply.next_actions || []).join(', ') };
return [{ json: { reply, session: s, log, security_case: res.security_case || null, escalation } }];
