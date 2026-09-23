const c = ctx(); const b = c.body; const s = c.session;
if (s.locked === 'yes') return result(fail('VERIFICATION_LOCKED', "I'm not able to verify you on this call. Let me connect you to a colleague who can help."));
const customers = rowsOf('Read Customers');
const accounts = rowsOf('Read Accounts');
const name = normName(b.full_name);
const given = { dob: b.date_of_birth ? normDob(b.date_of_birth) : '', acct: b.account_last4 ? last4(b.account_last4) : '', phone: b.phone_last4 ? last4(b.phone_last4) : '' };
let match = null; let tier = 'T0';
for (const cu of customers.filter((x) => normName(x.full_name) === name)) {
  const accts = accounts.filter((a) => a.customer_id === cu.customer_id);
  const checks = {
    dob: given.dob ? normDob(cu.date_of_birth) === given.dob : null,
    acct: given.acct ? accts.some((a) => last4(a.account_number) === given.acct) : null,
    phone: given.phone ? last4(cu.phone_last4 || cu.phone) === given.phone : null,
  };
  const provided = Object.values(checks).filter((v) => v !== null);
  if (!provided.length || provided.includes(false)) continue;
  if (checks.dob && checks.acct && checks.phone) tier = 'T2';
  else if (checks.acct || checks.phone) tier = 'T1';
  else continue;
  match = { cu, accts }; break;
}
if (!match) {
  const failed = Number(s.failed_attempts || 0) + 1;
  if (failed >= 2) {
    return result(ok({ result: 'locked', tier: 'T0', attempts_remaining: 0, must_escalate: true },
      "I'm sorry, I couldn't confirm those details, so I can't access the account on this call. I'll connect you to a colleague.", ['request_human_handoff']),
      { session_update: { failed_attempts: failed, locked: 'yes', max_risk: 'HIGH', intents_add: 'VERIFICATION_FAILED' },
        security_case: { case_id: newId('SEC'), conversation_id: c.conv, customer_id: '', type: 'verification_failed', secret_kind: '', created_at: fmtWAT(nowDate()) } });
  }
  return result(ok({ result: 'failed', tier: 'T0', attempts_remaining: 2 - failed }, "Sorry, those details don't match our records. Let's try once more.", ['verify_caller']),
    { session_update: { failed_attempts: failed } });
}
if (s.customer_id === match.cu.customer_id && tierRank(s.tier) > tierRank(tier)) tier = s.tier;
const first = match.cu.full_name.split(' ')[0];
const hold = match.accts.some((a) => ['restricted', 'fraud_hold'].includes(String(a.status)));
return result(ok({ result: tier === 'T2' ? 'verified' : 'partial', tier, first_name: first, needs_specialist: hold },
  `Thank you, ${first}.`, hold ? ['request_human_handoff'] : []),
  { session_update: { customer_id: match.cu.customer_id, customer_name: match.cu.full_name, tier, verified_at: fmtWAT(nowDate()), max_risk: hold ? 'HIGH' : 'LOW' } });
