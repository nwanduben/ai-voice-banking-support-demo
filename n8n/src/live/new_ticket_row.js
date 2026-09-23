const c = ctx(); const b = c.body; const n = nowDate();
const category = INTENTS[b.category] ? b.category : 'COMPLAINT_GENERAL';
const priority = c.session.max_risk === 'HIGH' ? 'P1' : (b.callback_requested === true || String(b.callback_requested) === 'true') ? 'P2' : 'P3';
return [{ json: { ticket_id: newId('TKT'), customer_id: c.session.customer_id, category, linked_txn_id: b.linked_txn_id || '', status: 'open', priority,
  created_at: fmtWAT(n), sla_due: fmtWAT(new Date(n.getTime() + COMPLAINT_SLA_DAYS * 86400e3)), summary: String(b.summary || '').slice(0, 400), created_by: 'voice_agent' } }];
