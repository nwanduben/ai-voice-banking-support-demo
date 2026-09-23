const c = ctx(); const n = nowDate();
let ref = String(c.body.reference || '').toUpperCase().replace(/[^A-Z0-9]/g, '').replace(/^(TKT|DSP)/, '$1-');
const tickets = rowsOf('Read Customer Tickets').filter((t) => t.customer_id === c.session.customer_id);
if (ref.startsWith('DSP')) { const d = rowsOf('Read Customer Disputes').find((x) => x.dispute_id === ref); if (d) ref = d.ticket_id; }
const t = tickets.find((x) => x.ticket_id === ref);
if (!t) return result(fail('NOT_FOUND', "I couldn't find that reference on your profile. Could you read it out again, slowly?", []));
const breached = parseWAT(t.sla_due) < n && !['resolved', 'closed'].includes(t.status);
const repeats = t.linked_txn_id ? tickets.filter((x) => x.linked_txn_id === t.linked_txn_id && n - parseWAT(x.created_at) <= 7 * 86400e3).length : 1;
let say = `Your complaint ${spokenRef(t.ticket_id)} is ${String(t.status).replace(/_/g, ' ')}.`;
if (breached || repeats >= REPEAT_CONTACT_THRESHOLD) {
  say += " I'm sorry it's taken this long. I'm treating it as a priority and connecting you to a senior colleague.";
  return result(ok({ ticket_id: t.ticket_id, status: t.status, sla_breached: breached, reports_last_7_days: repeats }, say, ['request_human_handoff']),
    { session_update: { max_risk: 'HIGH', intents_add: 'COMPLAINT_TICKET_STATUS' } });
}
return result(ok({ ticket_id: t.ticket_id, status: t.status, sla_breached: false, reports_last_7_days: repeats }, say), { session_update: { intents_add: 'COMPLAINT_TICKET_STATUS' } });
