const c = ctx(); const b = c.body;
const t = rowsOf('Read Disputed Transaction')[0];
if (!t || t.customer_id !== c.session.customer_id) return result(fail('NOT_FOUND', "I couldn't find that transaction on your account.", []), { proceed: false });
if (!['ATM_NO_CASH', 'POS_DOUBLE_DEBIT', 'POS_FAILED_DEBITED', 'UNAUTHORIZED'].includes(b.type)) return result(fail('VALIDATION_ERROR', 'Can you tell me what went wrong with that transaction?', []), { proceed: false });
const key = t.channel === 'ATM' ? (yes(t.on_us) ? 'ATM_ON_US' : 'ATM_NOT_ON_US') : t.channel;
const hours = Math.max(WINDOW_HOURS[key] ?? 72, 24);
const intent = { ATM_NO_CASH: 'ATM_CASH_DISPUTE', UNAUTHORIZED: 'UNAUTHORIZED_TRANSACTION' }[b.type] || 'POS_DISPUTE';
return [{ json: { proceed: true, txn: t, hours, intent, high: INTENTS[intent][0] === 'HIGH' } }];
