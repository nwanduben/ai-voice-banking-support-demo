const b = ctx().body;
const city = normName(b.city); const area = normName(b.area); const type = b.type || 'any';
const alias = { abuja: 'abuja', fct: 'abuja', 'port harcourt': 'port harcourt', ph: 'port harcourt' };
const rows = rowsOf('Read Branches').filter((r) => (!city || normName(r.city) === (alias[city] || city)) && (!area || normName(r.area).includes(area)) && (type === 'any' || r.type === type));
if (!rows.length) return result(ok({ results: [] }, "I don't have an ENTIN location there. You can see every branch and ATM in the app under Locations."));
const top = rows.slice(0, 3).map((r) => ({ name: r.name, address: r.address, hours: r.hours, status: r.status }));
const f = top[0];
return result(ok({ results: top }, `The closest is ${f.name}, at ${f.address}. Opening hours: ${f.hours}.${f.status === 'out_of_service' ? " It's currently out of service." : ''}`));
