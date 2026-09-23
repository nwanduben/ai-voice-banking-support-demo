const c = ctx(); const b = c.body;
if (!INTENTS[b.intent]) return result(fail('VALIDATION_ERROR', 'Could you tell me a little more about what you need help with?', []));
const [base, tier, queue] = INTENTS[b.intent];
const signals = Array.isArray(b.signals) ? b.signals : String(b.signals || '').split(',');
let level = base;
if (signals.some((x) => HIGH_SIGNALS.includes(String(x).trim()))) level = 'HIGH';
if (Number(b.amount_naira || 0) >= HIGH_AMOUNT_NAIRA) level = 'HIGH';
const final = maxRisk(c.session.max_risk, level);
const verified = tierRank(c.session.tier) >= tierRank(tier);
const must = final === 'HIGH' || b.intent === 'HUMAN_AGENT_REQUEST';
return result(ok({ intent: b.intent, risk_level: final, required_tier: tier, already_verified: verified, must_escalate: must, escalation_queue: queue }, '',
  [...(verified ? [] : ['verify_caller']), ...(must ? ['request_human_handoff'] : [])]),
  { session_update: { max_risk: level, intents_add: b.intent } });
