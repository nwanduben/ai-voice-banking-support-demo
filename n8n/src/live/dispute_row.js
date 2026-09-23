const c = ctx(); const d = $('Check Dispute').first().json; const t = $('Dispute Ticket Row').first().json; const n = nowDate();
return [{ json: { dispute_id: newId('DSP'), ticket_id: t.ticket_id, customer_id: c.session.customer_id, txn_id: d.txn.txn_id, type: c.body.type, status: 'open',
  created_at: fmtWAT(n), expected_resolution: fmtWAT(new Date(n.getTime() + d.hours * 3600e3)) } }];
