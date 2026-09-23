// Keeps the bank alive: a few realistic transactions every run, plus the occasional problem for the agent to handle.
const accounts = $input.all().map((i) => i.json).filter((a) => a.account_number && a.status === 'active');
const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];
const n = nowDate();
const MERCHANTS = ['Mama Put Kitchen', 'ShopRite-like Store (fictional)', 'Filling Station (fictional)', 'Pharmacy Plus (fictional)', 'QuickBuy Online (fictional)', 'Bolt-like Rides (fictional)'];
const BANKS = ['Fictional Trust Bank', 'Sample Savings Bank', 'Demo Microfinance Bank', 'Quick Fictional Bank'];
const PEOPLE = ['Chioma O***r', 'Kunle B****e', 'Aminu Y***f', 'Efe O****e', 'Hauwa G***o'];
const out = [];
const count = 2 + Math.floor(Math.random() * 3);
for (let i = 0; i < count; i++) {
  const a = pick(accounts);
  let bal = Number(a.balance_naira) || 0;
  const r = Math.random();
  const base = { txn_id: `TXN-L${String(Date.now()).slice(-7)}${i}`, customer_id: a.customer_id, account_number: a.account_number, date_time: fmtWAT(n),
    counterparty_bank: '', beneficiary_credited: '', on_us: '', reversal_status: '', reversal_due: '', reversal_completed_at: '',
    reference: `ENT${Math.floor(1e11 + Math.random() * 9e11)}`, status: 'successful', debited: 'yes', direction: 'debit' };
  let t;
  if (r < 0.15) { const amt = pick([85000, 150000, 250000]); t = { ...base, channel: 'TRANSFER', direction: 'credit', debited: '', amount_naira: amt, counterparty: 'Sample Tech Hub', counterparty_bank: pick(BANKS), narration: 'Salary', beneficiary_credited: 'yes' }; bal += amt; }
  else if (r < 0.50) { const amt = pick([1500, 3500, 7800, 12500, 22000]); t = { ...base, channel: 'POS', amount_naira: amt, counterparty: pick(MERCHANTS), narration: 'POS purchase' }; bal -= amt; }
  else if (r < 0.75) { const amt = pick([5000, 10000, 20000, 50000]); t = { ...base, channel: 'TRANSFER', amount_naira: amt, counterparty: pick(PEOPLE), counterparty_bank: pick(BANKS), narration: 'Transfer', beneficiary_credited: 'yes' }; bal -= amt; }
  else if (r < 0.88) { const amt = pick([500, 1000, 2000]); t = { ...base, channel: 'USSD', amount_naira: amt, counterparty: 'Airtime (fictional network)', narration: 'Airtime purchase' }; bal -= amt; }
  else if (r < 0.95) { // problem: transfer debited but not credited, reversal scheduled within the CBN window
    const amt = pick([15000, 30000, 45000]);
    t = { ...base, channel: 'TRANSFER', amount_naira: amt, counterparty: pick(PEOPLE), counterparty_bank: pick(BANKS), narration: 'Transfer', status: 'reversal_pending',
      beneficiary_credited: 'no', reversal_status: 'scheduled', reversal_due: fmtWAT(new Date(n.getTime() + 72 * 3600e3)) }; bal -= amt;
  } else { // problem: other-bank ATM debited without dispensing
    const amt = pick([10000, 20000]); t = { ...base, channel: 'ATM', amount_naira: amt, counterparty: 'Other bank ATM', narration: 'ATM withdrawal - no cash dispensed', on_us: 'no' }; bal -= amt;
  }
  if (bal < 0) { bal += Number(t.amount_naira); t.status = 'failed'; t.debited = 'no'; t.narration += ' - insufficient funds'; }
  t.balance_after = bal;
  a.balance_naira = bal;
  out.push({ json: t });
}
return out;
