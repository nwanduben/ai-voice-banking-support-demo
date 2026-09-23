const x = $input.first().json;
const fresh = Math.abs(Date.now() / 1000 - Number(x.t)) < 30 * 60;
const valid = !!x.v0 && fresh && String(x.expected || '').toLowerCase() === String(x.v0).toLowerCase();
let body = null;
if (valid) { try { body = JSON.parse(x.raw); } catch (e) { body = null; } }
return [{ json: { valid: valid && !!body, body } }];
