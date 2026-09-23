const c = ctx(); const b = c.body;
if (!(b.caller_confirmed === true || String(b.caller_confirmed).toLowerCase() === 'true')) {
  return result(fail('CONFIRMATION_NEEDED', "Before I block it, can you confirm you want the card blocked? It can't be used again once it's blocked.", []), { proceed: false });
}
if (!['lost', 'stolen', 'suspected_fraud'].includes(b.reason)) return result(fail('VALIDATION_ERROR', 'Is the card lost, stolen, or are you worried about fraud?', []), { proceed: false });
let cards = rowsOf('Read Cards To Block').filter((x) => x.customer_id === c.session.customer_id && x.status === 'active');
if (!yes(b.all_cards)) cards = b.card_last4 ? cards.filter((x) => last4(x.card_last4) === last4(b.card_last4)) : (cards.length === 1 ? cards : []);
if (!cards.length) return result(fail('NOT_FOUND', "I couldn't find an active card with those last four digits. Which card is it?", []), { proceed: false });
return [{ json: { proceed: true, reason: b.reason, cards: cards.map((x) => ({ card_id: x.card_id, card_last4: last4(x.card_last4) })) } }];
