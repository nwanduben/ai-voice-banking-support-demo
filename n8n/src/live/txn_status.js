const c = ctx(); const n = nowDate();
const t = rowsOf('Read Transaction')[0];
if (!t || t.customer_id !== c.session.customer_id) return result(fail('NOT_FOUND', "I couldn't find that transaction on your account."));
const tickets = rowsOf('Read Related Tickets').filter((k) => k.customer_id === c.session.customer_id);
const key = t.channel === 'ATM' ? (yes(t.on_us) ? 'ATM_ON_US' : 'ATM_NOT_ON_US') : t.channel;
const wh = WINDOW_HOURS[key] ?? 72;
const within = n - parseWAT(t.date_time) <= wh * 3600e3;
const amt = naira(t.amount_naira);
let action = 'none'; let say = ''; const extra = {};
const due = parseWAT(t.reversal_due);
if (t.status === 'failed' && !yes(t.debited)) say = `That transfer of ${amt} failed, but the good news is no money left your account. You can try again.`;
else if (t.reversal_status === 'completed') say = `The ${amt} was reversed to your account ${spokenWhen(t.reversal_completed_at)}.`;
else if (due && due < n) { action = 'create_ticket'; say = `The reversal of ${amt} is overdue. I'm sorry about that. I'll log a complaint so it's escalated.`; }
else if (t.channel === 'ATM' && yes(t.debited)) { action = 'create_dispute'; say = `I can see the ${amt} ATM debit. I'll log a dispute so it's investigated and refunded if the cash wasn't dispensed.`; }
else if (t.channel === 'POS' && yes(t.debited)) { action = 'create_dispute'; say = `I can see the ${amt} POS debit. If you were charged twice or the payment failed, I can log a dispute.`; }
else if (['pending', 'reversal_pending'].includes(t.status) && yes(t.debited) && !yes(t.beneficiary_credited)) {
  if (within) { action = 'wait'; say = `Your ${amt} transfer is still being processed. Under CBN guidelines it should either reach the recipient or come back to you within ${wh} hours of the transfer.`; }
  else { action = 'create_ticket'; say = `Your ${amt} transfer has been pending longer than it should. I'll raise a complaint so it's escalated.`; }
} else if (t.status === 'successful' && t.direction === 'debit') {
  say = `That ${amt} ${t.channel === 'TRANSFER' ? 'transfer was successful and the receiving bank confirmed it' : 'payment went through successfully'}. If you don't recognise it, I can block your card and report it.`;
}
const recent = tickets.filter((k) => n - parseWAT(k.created_at) <= 7 * 86400e3).length;
if (Number(t.amount_naira) >= HIGH_AMOUNT_NAIRA || recent >= REPEAT_CONTACT_THRESHOLD) {
  action = 'escalate'; extra.session_update = { max_risk: 'HIGH' };
  say += " Because of the amount or how many times you've had to contact us, I'm going to get a senior colleague to handle this.";
}
return result(ok({ txn_id: t.txn_id, status: t.status, debited: yes(t.debited), beneficiary_credited: t.beneficiary_credited || null,
  reversal_status: t.reversal_status || null, within_policy_window: within, policy_window_hours: wh, recommended_action: action },
  say.trim(), action === 'none' ? [] : [action === 'escalate' ? 'request_human_handoff' : action]), extra);
