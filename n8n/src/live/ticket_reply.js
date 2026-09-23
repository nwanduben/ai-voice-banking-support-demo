const t = $('New Ticket Row').first().json;
return result(ok({ ticket_id: t.ticket_id, ticket_id_spoken: spokenRef(t.ticket_id), priority: t.priority, sla_days: COMPLAINT_SLA_DAYS },
  `I've logged that for you. Your reference is ${spokenRef(t.ticket_id)}. We aim to resolve it within ${COMPLAINT_SLA_DAYS} days, and you'll get updates by SMS.`),
  { session_update: { intents_add: t.category } });
