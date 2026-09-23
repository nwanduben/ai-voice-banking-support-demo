const c = ctx(); const b = c.body;
const intents = String(c.session.intents || '').split(',').filter(Boolean).reverse();
const queue = (intents.map((i) => (INTENTS[i] || [])[2]).find((q) => q && q !== 'general')) || 'general';
const mode = b.caller_preference === 'callback' ? 'callback' : 'transfer';
const esc = { handoff_id: newId('HOF'), conversation_id: c.conv, customer_id: c.session.customer_id, queue, priority: '', risk_level: '',
  reason: b.reason || 'caller_request', summary: String(b.summary || '').slice(0, 600), mode, status: 'queued', created_at: fmtWAT(nowDate()) };
const say = mode === 'transfer' ? "I'm connecting you to a colleague now. I've passed on everything we discussed, so you won't need to repeat yourself."
  : 'I\'ve booked a callback. A colleague will call you back on your registered number.';
return result(ok({ handoff_id: esc.handoff_id, mode, queue, transfer_destination: `${queue}_line` }, say, [mode === 'transfer' ? 'transfer_to_number' : 'end_call']),
  { escalation: esc, session_update: { intents_add: 'HUMAN_AGENT_REQUEST' } });
