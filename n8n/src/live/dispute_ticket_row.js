const c = ctx(); const d = $('Check Dispute').first().json; const n = nowDate();
return [{ json: { ticket_id: newId('TKT'), customer_id: c.session.customer_id, category: d.intent, linked_txn_id: d.txn.txn_id, status: 'open',
  priority: d.high || c.session.max_risk === 'HIGH' ? 'P1' : 'P2', created_at: fmtWAT(n), sla_due: fmtWAT(new Date(n.getTime() + d.hours * 3600e3)),
  summary: String(c.body.caller_statement || `${d.intent} on ${d.txn.txn_id}`).slice(0, 400), created_by: 'voice_agent' } }];
