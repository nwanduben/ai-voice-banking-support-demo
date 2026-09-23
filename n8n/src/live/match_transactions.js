const c = ctx(); const b = c.body; const n = nowDate();
const dayStart = (v) => parseWAT(String(v).slice(0, 10));
const from = b.date_from ? dayStart(b.date_from) : new Date(n - 7 * 86400e3);
const to = b.date_to ? new Date(dayStart(b.date_to).getTime() + 86400e3 - 1) : n;
const CH = { transfer: ['TRANSFER'], pos: ['POS'], atm: ['ATM'], card_online: ['WEB'], ussd: ['USSD'] };
let txns = rowsOf('Read Customer Transactions').filter((t) => t.customer_id === c.session.customer_id);
txns = txns.filter((t) => { const d = parseWAT(t.date_time); return d && d >= from && d <= to; });
txns = txns.filter((t) => t.direction === (b.direction || 'debit'));
if (CH[b.channel]) txns = txns.filter((t) => CH[b.channel].includes(t.channel));
if (b.amount_naira_approx) {
  const a = Number(b.amount_naira_approx);
  txns = txns.filter((t) => Math.abs(Number(t.amount_naira) - a) <= Math.max(0.1 * a, 100));
}
txns.sort((x, y) => parseWAT(y.date_time) - parseWAT(x.date_time));
if (!txns.length) return result(ok({ matches: [] }, "I couldn't find a transaction matching that. Could you tell me roughly when it was and how much?", []));
if (txns.length > 3) return result(fail('AMBIGUOUS_MATCH', 'I can see a few transactions like that. Do you remember roughly which day, or the exact amount?', []));
const KIND = { TRANSFER: 'a transfer', POS: 'a POS payment', ATM: 'an ATM withdrawal', WEB: 'an online card payment', USSD: 'a USSD transaction' };
const matches = txns.map((t) => ({ txn_id: t.txn_id, when: spokenWhen(t.date_time), amount_naira: Number(t.amount_naira), amount_spoken: naira(t.amount_naira),
  kind: KIND[t.channel] || 'a transaction', counterparty: t.counterparty, counterparty_bank: t.counterparty_bank, status: t.status }));
const m = matches[0];
const say = matches.length > 1
  ? `I can see ${matches.length} that could match: ${matches.map((x) => `${x.amount_spoken} ${x.when}`).join('; ')}. Which one is it?`
  : `I can see ${m.amount_spoken} ${m.when}, ${m.kind}${m.counterparty ? ` to ${m.counterparty}` : ''}.`;
return result(ok({ matches }, say, ['confirm_with_caller', 'get_transaction_status']));
