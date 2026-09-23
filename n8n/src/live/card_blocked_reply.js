const x = $('Choose Cards').first().json; const t = $('Replacement Ticket Row').first().json;
const many = x.cards.length > 1;
const l4s = x.cards.map((cd) => cd.card_last4.split('').join(' ')).join(', and ');
return result(ok({ blocked: true, cards_blocked: x.cards.map((cd) => cd.card_last4), replacement_ticket_id: t.ticket_id },
  `Done. I've blocked the card${many ? 's' : ''} ending ${l4s}. Nobody can use ${many ? 'them' : 'it'} now. A replacement request is logged under ${spokenRef(t.ticket_id)}.`,
  x.reason === 'lost' ? [] : ['request_human_handoff']), { session_update: { max_risk: 'HIGH', intents_add: 'CARD_LOST_STOLEN' } });
