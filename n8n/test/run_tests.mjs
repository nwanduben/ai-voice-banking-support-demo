// End-to-end tests: run the exported n8n workflow JSON against the 500-customer bank (data/csv).
//   node n8n/test/run_tests.mjs
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { Runner, loadBank } from './engine.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const wf = (f) => JSON.parse(fs.readFileSync(path.join(here, '..', f), 'utf8'));
const tables = loadBank(path.join(here, '..', '..', 'data', 'csv'));
const env = { ENTIN_ELEVENLABS_WEBHOOK_SECRET: 'whsec_test', ENTIN_ALERT_EMAIL: 'demo@example.com' };
const live = new Runner(wf('1-live-call-tools.json'), tables, env);
const who = Object.fromEntries(tables['Test Callers'].rows.map((r) => [r.full_name, r]));

let passed = 0; const failures = [];
const test = (name, fn) => { try { fn(); passed++; console.log(`  ok  ${name}`); } catch (e) { failures.push(name); console.log(`  FAIL ${name}\n       ${e.message}`); } };
const tab = (t) => tables[t].rows;

function call(conv, tool, args = {}) {
  const res = live.run(`Webhook: ${tool}`, [{ json: { body: { conversation_id: conv, ...args }, headers: {} } }]);
  assert.equal(res.responses.length, 1, `${tool}: expected exactly one webhook response, got ${res.responses.length}`);
  return { ...res.responses[0].body, _emails: res.emails };
}
const verify = (conv, name, full = true) => {
  const p = who[name];
  const args = { full_name: name, account_last4: p.account_last4 };
  if (full) Object.assign(args, { date_of_birth: p.date_of_birth, phone_last4: p.phone_last4 });
  const r = call(conv, 'verify_caller', args);
  assert.ok(r.ok && ['verified', 'partial'].includes(r.data.result), JSON.stringify(r));
  return r;
};
const yday = new Date(Date.now() - 86400e3 + 3600e3).toISOString().slice(0, 10);

console.log('\nReset demo scenarios (workflow 5)');
test('reset re-anchors Gerald to yesterday 16:05', () => {
  new Runner(wf('5-reset-demo.json'), tables, env).run('Run Before Demo', [{ json: {} }]);
  assert.equal(tab('Transactions').find((t) => t.txn_id === 'TXN-S37').date_time, `${yday} 16:05`);
});

console.log('\nGerald demo call (workflow 1)');
test('S37 Gerald: 70,000 deducted yesterday, full call', () => {
  const c = 'conv_gerald';
  const a = call(c, 'assess_request', { intent: 'UNAUTHORIZED_TRANSACTION', signals: ['customer_denies_authorisation'], amount_naira: 70000 });
  assert.equal(a.data.risk_level, 'HIGH');
  assert.ok(a.next_actions.includes('verify_caller'));
  const v = verify(c, 'Gerald Okeke');
  assert.equal(v.data.tier, 'T2'); assert.equal(v.say, 'Thank you, Gerald.');
  const f = call(c, 'find_transactions', { date_from: yday, date_to: yday, amount_naira_approx: 70000 });
  assert.match(f.say, /70,000 naira yesterday at about 4 PM, an online card payment to QuickBuy Online/);
  const b = call(c, 'block_card', { reason: 'suspected_fraud', caller_confirmed: true });
  assert.ok(b.ok, JSON.stringify(b)); assert.match(b.say, /^Done\. I've blocked the card ending/);
  assert.equal(tab('Cards').find((x) => x.customer_id === 'CUS-0037').status, 'blocked_fraud');
  const d = call(c, 'create_dispute', { txn_id: f.data.matches[0].txn_id, type: 'UNAUTHORIZED', caller_statement: 'Did not make this payment' });
  assert.ok(d.data.dispute_id.startsWith('DSP-')); assert.equal(tab('Disputes').at(-1).txn_id, 'TXN-S37');
  const h = call(c, 'request_human_handoff', { reason: 'high_risk', summary: 'Unrecognised N70,000 online payment; card blocked; dispute logged' });
  assert.equal(h.data.queue, 'fraud'); assert.equal(h._emails.length, 1); assert.match(h._emails[0].subject, /^\[P1 · HIGH\] Customer handoff · Gerald Okeke · HOF-/);
  assert.match(h._emails[0].html, /ENTIN&nbsp;BANK/); assert.match(h._emails[0].html, /Fraud &amp; Security|Fraud & Security/); assert.ok(!h._emails[0].html.includes('{{'), 'all expressions filled');
  fs.writeFileSync(path.join(here, 'sample-handoff-email.html'), h._emails[0].html);
  const s = tab('Sessions').find((x) => x.conversation_id === c);
  assert.equal(s.tier, 'T2'); assert.equal(s.max_risk, 'HIGH'); assert.equal(s.customer_id, 'CUS-0037');
  assert.equal(tab('Call Log').filter((x) => x.conversation_id === c).length, 6);
  assert.equal(tab('Escalations').at(-1).priority, 'P1');
});

console.log('\nSecurity rules');
test('account lookups need verification first', () => {
  const r = call('conv_noverify', 'find_transactions', { amount_naira_approx: 70000 });
  assert.equal(r.error.code, 'VERIFICATION_REQUIRED');
});
test('T1 (name + last 4) can block a card but not read transactions', () => {
  verify('conv_t1', 'Kelechi Umeh', false);
  assert.equal(call('conv_t1', 'find_transactions', {}).error.code, 'VERIFICATION_REQUIRED');
  const b = call('conv_t1', 'block_card', { reason: 'lost' });
  assert.equal(b.error.code, 'CONFIRMATION_NEEDED');
  assert.ok(call('conv_t1', 'block_card', { reason: 'lost', caller_confirmed: true }).ok);
});
for (const [text, kind] of [['My OTP is 829114', 'otp'], ['my PIN is 4 4 2 1', 'pin'], ['My CVV is 999', 'cvv'], ['my password is Lagos2026!', 'password'], ['card 5399 1234 5678 9012', 'card_number']]) {
  test(`volunteered ${kind} is rejected, logged as a security case, never stored`, () => {
    const conv = `conv_secret_${kind}`;
    const r = call(conv, 'create_ticket', { category: 'FAQ_GENERAL', summary: text });
    assert.equal(r.error.code, 'SENSITIVE_DATA_REJECTED'); assert.equal(r.risk_level, 'HIGH');
    const sc = tab('Security Cases').find((x) => x.conversation_id === conv);
    assert.equal(sc.secret_kind, kind);
    const everything = JSON.stringify(Object.values(tables).map((t) => t.rows));
    assert.ok(!everything.includes(text), 'secret text must not be written to any tab');
  });
}
test('two failed verifications lock the call', () => {
  const bad = { full_name: 'Adaeze Okafor', date_of_birth: '1990-01-01', account_last4: who['Adaeze Okafor'].account_last4, phone_last4: '0001' };
  assert.equal(call('conv_lock', 'verify_caller', bad).data.result, 'failed');
  const r = call('conv_lock', 'verify_caller', bad);
  assert.equal(r.data.result, 'locked'); assert.equal(r.risk_level, 'HIGH');
  assert.equal(call('conv_lock', 'verify_caller', { ...bad, date_of_birth: '1991-03-14' }).error.code, 'VERIFICATION_LOCKED');
});
test("another customer's balance / prompt injection is logged as prohibited", () => {
  const r = call('conv_pi', 'report_security_event', { type: 'third_party_data_request' });
  assert.ok(r.data.case_id.startsWith('SEC-')); assert.equal(r.risk_level, 'HIGH');
  assert.equal(call('conv_pi2', 'assess_request', { intent: 'PROHIBITED_REQUEST', signals: ['prompt_injection'] }).data.risk_level, 'HIGH');
});
test('tolerates Google Sheets turning "0037" into 37 and DOB spoken as DD/MM/YYYY', () => {
  const g = tab('Customers').find((x) => x.customer_id === 'CUS-0037'); const keep = g.phone_last4; g.phone_last4 = '37';
  const r = call('conv_fmt', 'verify_caller', { full_name: 'gerald okeke', date_of_birth: '15/06/1990', account_last4: who['Gerald Okeke'].account_last4, phone_last4: '0037' });
  g.phone_last4 = keep;
  assert.equal(r.data.tier, 'T2');
});
test('risk never goes down during a call', () => {
  call('conv_risk', 'assess_request', { intent: 'CARD_LOST_STOLEN' });
  assert.equal(call('conv_risk', 'assess_request', { intent: 'FAQ_GENERAL' }).data.risk_level, 'HIGH');
});

console.log('\nBanking scenarios');
test('S01 transfer debited not received -> wait, CBN 72 hours', () => {
  verify('conv_s01', 'Adaeze Okafor');
  const m = call('conv_s01', 'find_transactions', { amount_naira_approx: 45000, channel: 'transfer' });
  const s = call('conv_s01', 'get_transaction_status', { txn_id: m.data.matches[0].txn_id });
  assert.equal(s.data.recommended_action, 'wait'); assert.match(s.say, /72 hours/);
});
test('S02 failed transfer, not debited', () => {
  verify('conv_s02', 'Tunde Bakare');
  assert.match(call('conv_s02', 'get_transaction_status', { txn_id: 'TXN-S02' }).say, /no money left your account/);
});
test('S04 overdue reversal -> create ticket', () => {
  verify('conv_s04', 'Halima Yusuf');
  assert.equal(call('conv_s04', 'get_transaction_status', { txn_id: 'TXN-S04' }).data.recommended_action, 'create_ticket');
  const t = call('conv_s04', 'create_ticket', { category: 'REVERSAL_STATUS', linked_txn_id: 'TXN-S04', summary: 'Reversal overdue' });
  assert.ok(tab('Tickets').some((x) => x.ticket_id === t.data.ticket_id && x.created_by === 'voice_agent'));
});
test("S31 no reference -> narrowed by amount", () => {
  verify('conv_s31', 'Obinna Chukwu');
  assert.equal(call('conv_s31', 'find_transactions', { channel: 'transfer' }).error.code, 'AMBIGUOUS_MATCH');
  assert.equal(call('conv_s31', 'find_transactions', { channel: 'transfer', amount_naira_approx: 25000 }).data.matches.length, 1);
});
test("S32 'I don't recognise this 150,000' is found", () => {
  verify('conv_s32', 'Zainab Lawal');
  assert.equal(call('conv_s32', 'find_transactions', { amount_naira_approx: 150000 }).data.matches[0].txn_id, 'TXN-S32');
});
test('S24 N2.5m -> escalate', () => {
  verify('conv_s24', 'Daniel Okoro');
  const s = call('conv_s24', 'get_transaction_status', { txn_id: 'TXN-S24' });
  assert.equal(s.data.recommended_action, 'escalate'); assert.equal(s.risk_level, 'HIGH');
});
test('S06 ATM no cash -> HIGH, dispute with 48 hours', () => {
  assert.equal(call('conv_s06', 'assess_request', { intent: 'ATM_CASH_DISPUTE' }).data.risk_level, 'HIGH');
  verify('conv_s06', 'Funke Adeyemi');
  assert.equal(call('conv_s06', 'create_dispute', { txn_id: 'TXN-S06', type: 'ATM_NO_CASH' }).data.expected_resolution_hours, 48);
});
test('S34 block every card (3 cards)', () => {
  verify('conv_s34', 'Bayo Ogunleye', false);
  const r = call('conv_s34', 'block_card', { all_cards: true, reason: 'suspected_fraud', caller_confirmed: true });
  assert.equal(r.data.cards_blocked.length, 3);
  assert.equal(tab('Cards').filter((x) => x.customer_id === 'CUS-0034' && x.status === 'blocked_fraud').length, 3);
});
test('S08 decline explained without reading the balance; S10 fraud review escalates', () => {
  verify('conv_s08', 'Ngozi Obi');
  const r = call('conv_s08', 'get_card_status');
  assert.match(r.say, /weren't enough available funds/); assert.ok(!/balance/i.test(r.say));
  verify('conv_s10', 'Aisha Bello');
  const f = call('conv_s10', 'get_card_status');
  assert.equal(f.risk_level, 'HIGH'); assert.ok(f.next_actions.includes('request_human_handoff'));
});
test('S20 restricted account -> specialist, no reason given', () => {
  const v = verify('conv_s20', 'Tope Salami');
  assert.equal(v.risk_level, 'HIGH'); assert.ok(v.next_actions.includes('request_human_handoff'));
});
test('S14 locked app is never unlocked; S16 OTP blocked by DND', () => {
  verify('conv_s14', 'Grace Etim');
  assert.match(call('conv_s14', 'get_digital_access_status').say, /can't unlock it/);
  verify('conv_s16', 'Musa Danjuma', false);
  assert.match(call('conv_s16', 'get_digital_access_status').say, /Do-Not-Disturb/);
});
test('S36 reported three times -> priority + human', () => {
  verify('conv_s36', 'Amaka Nwachukwu', false);
  const r = call('conv_s36', 'get_ticket_status', { reference: 'TKT 104302' });
  assert.ok(r.next_actions.includes('request_human_handoff')); assert.equal(r.risk_level, 'HIGH');
});
test('S25 wants a human -> handoff + email', () => {
  const r = call('conv_s25', 'request_human_handoff', { reason: 'caller_request', summary: 'Caller asked for a person' });
  assert.equal(r.data.mode, 'transfer'); assert.equal(r._emails.length, 1);
});
test('branch lookup needs no verification', () => {
  assert.match(call('conv_branch', 'find_branch_or_atm', { city: 'Lagos', area: 'Ikeja', type: 'branch' }).say, /ENTIN Ikeja Branch/);
});

test('13 separate webhooks, each with its own path', () => {
  const hooks = wf('1-live-call-tools.json').nodes.filter((n) => n.type === 'n8n-nodes-base.webhook');
  assert.equal(hooks.length, 13);
  assert.equal(new Set(hooks.map((h) => h.parameters.path)).size, 13);
  assert.ok(hooks.every((h) => h.parameters.path === `entin/${h.name.replace('Webhook: ', '')}` && h.parameters.authentication === 'headerAuth'));
});

console.log('\nBackground workflows');
test('bank activity adds transactions and updates balances (workflow 3)', () => {
  const before = tab('Transactions').length;
  const res = new Runner(wf('3-bank-activity.json'), tables, env).run('Every 5 Minutes', [{ json: {} }]);
  const added = tab('Transactions').slice(before);
  assert.ok(added.length >= 2 && added.length <= 4, `added ${added.length}`);
  for (const t of added) assert.equal(String(tab('Accounts').find((a) => a.account_number === t.account_number).balance_naira), String(res.runData['Generate Activity'].filter((i) => i.json.account_number === t.account_number).at(-1).json.balance_after));
});
test('post-call webhook: valid signature saves redacted summary (workflow 2)', () => {
  const w2 = wf('2-post-call-summary.json');
  const cryptoNode = w2.nodes.find((n) => n.type === 'n8n-nodes-base.crypto');
  assert.equal(cryptoNode.parameters.secret, 'PASTE_ELEVENLABS_WEBHOOK_SECRET_HERE');
  const placeholderRun = new Runner(w2, tables, env);
  cryptoNode.parameters.secret = env.ENTIN_ELEVENLABS_WEBHOOK_SECRET; // what the user pastes in n8n
  const r2 = new Runner(w2, tables, env);
  const payload = { type: 'post_call_transcription', data: { conversation_id: 'conv_gerald', transcript: [{ role: 'user', message: 'my OTP is 829114' }],
    analysis: { transcript_summary: 'Caller read OTP 829114; card blocked', evaluation_criteria_results: { no_secret_requested: { result: 'success' } } } } };
  const raw = JSON.stringify(payload); const t = Math.floor(Date.now() / 1000);
  const sig = crypto.createHmac('sha256', env.ENTIN_ELEVENLABS_WEBHOOK_SECRET).update(`${t}.${raw}`).digest('hex');
  const good = r2.run('ElevenLabs Post-call Webhook', [{ json: { headers: { 'elevenlabs-signature': `t=${t},v0=${sig}` } }, binary: { data: { data: Buffer.from(raw).toString('base64') } } }]);
  assert.equal(good.responses[0].status, 200);
  const s = tab('Sessions').find((x) => x.conversation_id === 'conv_gerald');
  assert.equal(s.secret_detected, 'yes'); assert.ok(!s.call_summary.includes('829114')); assert.equal(s.tier, 'T2');
  const bad = r2.run('ElevenLabs Post-call Webhook', [{ json: { headers: { 'elevenlabs-signature': `t=${t},v0=deadbeef` } }, binary: { data: { data: Buffer.from(raw).toString('base64') } } }]);
  assert.equal(bad.responses[0].status, 401);
  cryptoNode.parameters.secret = 'PASTE_ELEVENLABS_WEBHOOK_SECRET_HERE';
  const unset = new Runner(w2, tables, env).run('ElevenLabs Post-call Webhook', [{ json: { headers: { 'elevenlabs-signature': `t=${t},v0=${sig}` } }, binary: { data: { data: Buffer.from(raw).toString('base64') } } }]);
  assert.equal(unset.responses[0].status, 401, 'without the real secret pasted, calls must be rejected');
});
test('no workflow depends on n8n server settings ($env)', () => {
  for (const f of ['1-live-call-tools.json', '2-post-call-summary.json', '3-bank-activity.json', '4-daily-digest.json', '5-reset-demo.json']) {
    assert.ok(!fs.readFileSync(path.join(here, '..', f), 'utf8').includes('$env'), f);
  }
});
test('daily digest email (workflow 4)', () => {
  const res = new Runner(wf('4-daily-digest.json'), tables, env).run('Daily 08:00 WAT', [{ json: {} }]);
  assert.match(res.emails[0].html, /Daily voice support report/); assert.ok(!res.emails[0].html.includes('{{')); assert.match(res.emails[0].html, /Passed to a human/);
  fs.writeFileSync(path.join(here, 'sample-digest-email.html'), res.emails[0].html);
});
test('reset puts Gerald\'s blocked card back to active', () => {
  new Runner(wf('5-reset-demo.json'), tables, env).run('Run Before Demo', [{ json: {} }]);
  assert.equal(tab('Cards').find((x) => x.customer_id === 'CUS-0037').status, 'active');
});

fs.writeFileSync(path.join(here, 'sample-call-log.csv'), ['timestamp,conversation_id,group,step,caller_details,result,agent_says,risk_level',
  ...tab('Call Log').filter((r) => r.conversation_id === 'conv_gerald').map((r) => [r.timestamp, r.conversation_id, r.group, r.step, r.caller_details, r.result, r.agent_says, r.risk_level]
    .map((v) => `"${String(v).replace(/"/g, '""')}"`).join(','))].join('\n') + '\n');
console.log(`\n${passed} passed, ${failures.length} failed`);
process.exit(failures.length ? 1 : 0);
