const d = $('Check Dispute').first().json; const r = $('Dispute Row').first().json;
return result(ok({ dispute_id: r.dispute_id, dispute_id_spoken: spokenRef(r.dispute_id), ticket_id: r.ticket_id, expected_resolution_hours: d.hours },
  `I've logged a dispute. Your reference is ${spokenRef(r.dispute_id)}. Under CBN timelines this type of case should be resolved within ${d.hours} hours.`,
  d.high ? ['request_human_handoff'] : []), { session_update: { max_risk: d.high ? 'HIGH' : 'MEDIUM', intents_add: d.intent } });
