const x = $('Choose Cards').first().json;
const STATUS = { lost: 'blocked_lost', stolen: 'blocked_stolen', suspected_fraud: 'blocked_fraud' };
return x.cards.map((cd) => ({ json: { card_id: cd.card_id, status: STATUS[x.reason], blocked_at: fmtWAT(nowDate()), block_reason: x.reason } }));
