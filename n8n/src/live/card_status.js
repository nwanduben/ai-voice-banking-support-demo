const c = ctx(); const b = c.body;
let cards = rowsOf('Read Customer Cards').filter((x) => x.customer_id === c.session.customer_id);
if (b.card_last4) cards = cards.filter((x) => last4(x.card_last4) === last4(b.card_last4));
if (!cards.length) return result(fail('NOT_FOUND', "I couldn't find a card ending in those digits.", []));
cards.sort((x, y) => (parseWAT(y.last_decline_at) || 0) - (parseWAT(x.last_decline_at) || 0));
const card = cards[0];
const PHRASE = { insufficient_funds: "there weren't enough available funds for that payment", card_blocked: 'the card is currently blocked',
  online_disabled: 'online payments are switched off on the card. You can switch them on in the ENTIN app under Cards',
  limit_reached: 'it went over your daily card limit', expired: 'the card has expired', needs_review: 'the payment needs a review by our team',
  temporary_issue: 'there was a temporary system issue' };
const l4 = last4(card.card_last4).split('').join(' ');
const data = { card_last4: last4(card.card_last4), status: card.status, online_enabled: yes(card.online_enabled) };
if (!card.last_decline_reason) return result(ok(data, `Your card ending ${l4} is ${String(card.status).replace(/_/g, ' ')}, and I don't see any recent declined payments.`));
const reason = PHRASE[card.last_decline_reason] ? card.last_decline_reason : 'needs_review';
data.latest_decline = { when: spokenWhen(card.last_decline_at), merchant: card.last_decline_merchant, reason_category: reason };
const review = reason === 'needs_review';
return result(ok(data, `The payment ${data.latest_decline.when} was declined because ${PHRASE[reason]}.`, review ? ['request_human_handoff'] : []),
  review ? { session_update: { max_risk: 'HIGH', intents_add: 'CARD_DECLINED' } } : { session_update: { intents_add: 'CARD_DECLINED' } });
