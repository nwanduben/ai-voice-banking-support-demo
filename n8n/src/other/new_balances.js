const latest = {};
for (const i of $('Generate Activity').all()) latest[i.json.account_number] = i.json.balance_after;
return Object.entries(latest).map(([account_number, balance_naira]) => ({ json: { account_number, balance_naira } }));
