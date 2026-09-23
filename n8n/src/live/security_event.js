const c = ctx(); const b = c.body;
const TYPES = ['sensitive_disclosure', 'social_engineering', 'unauthorized_txn', 'prompt_injection', 'third_party_data_request'];
if (!TYPES.includes(b.type)) return result(fail('VALIDATION_ERROR', '', []));
const ADVICE = { pin: 'Please change your PIN in the ENTIN app or at any ENTIN ATM as soon as you can.',
  otp: "Don't use that code for anything, and never share codes with anyone. If you didn't start a transaction, tell me now.",
  cvv: 'To be safe, I recommend we block that card and issue a new one.', password: 'Please change your mobile banking password in the app as soon as you can.',
  card_number: 'To be safe, I recommend we block that card and issue a new one.' };
const intent = ['prompt_injection', 'third_party_data_request'].includes(b.type) ? 'PROHIBITED_REQUEST'
  : b.type === 'sensitive_disclosure' ? 'SENSITIVE_INFO_DISCLOSED' : 'SUSPECTED_FRAUD_SCAM';
const say = ADVICE[b.secret_kind] || (intent === 'PROHIBITED_REQUEST' ? "I'm not able to help with that, but I'm happy to help with your own ENTIN account." : '');
const sc = { case_id: newId('SEC'), conversation_id: c.conv, customer_id: c.session.customer_id, type: b.type, secret_kind: b.secret_kind || '', created_at: fmtWAT(nowDate()) };
return result(ok({ case_id: sc.case_id }, say), { security_case: sc, session_update: { max_risk: 'HIGH', intents_add: intent, ...(b.type === 'sensitive_disclosure' ? { secret_detected: 'yes' } : {}) } });
