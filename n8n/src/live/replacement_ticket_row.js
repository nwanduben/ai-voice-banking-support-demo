const c = ctx(); const x = $('Choose Cards').first().json; const n = nowDate();
return [{ json: { ticket_id: newId('TKT'), customer_id: c.session.customer_id, category: 'CARD_LOST_STOLEN', linked_txn_id: '', status: 'open', priority: 'P2',
  created_at: fmtWAT(n), sla_due: fmtWAT(new Date(n.getTime() + COMPLAINT_SLA_DAYS * 86400e3)),
  summary: `Replacement for card(s) ending ${x.cards.map((cd) => cd.card_last4).join(', ')} blocked (${x.reason}) by voice agent`, created_by: 'voice_agent' } }];
