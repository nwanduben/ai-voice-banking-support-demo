// Re-anchor every scenario to "now" so Gerald's payment is always "yesterday around 4pm" on demo day.
const n = nowDate();
const rows = $input.all().map((i) => i.json).filter((r) => r.tab && r.id);
const merged = {};
for (const r of rows) {
  const key = `${r.tab}|${r.id}`;
  merged[key] = merged[key] || { tab: r.tab, [r.id_column]: r.id };
  if (r.offset_minutes !== '' && r.offset_minutes !== undefined && r.offset_minutes !== null) {
    let when = new Date(n.getTime() - Number(r.offset_minutes) * 60000);
    if (r.id === 'TXN-S37' && r.field === 'date_time') { when = new Date(n.getTime() - 86400e3); when = parseWAT(fmtWAT(when).slice(0, 10) + ' 16:05'); }
    merged[key][r.field] = fmtWAT(when);
  } else {
    merged[key][r.field] = r.value;
    if (r.tab === 'Cards' && r.field === 'status') Object.assign(merged[key], { blocked_at: '', block_reason: '' });
  }
}
return Object.values(merged).map((json) => ({ json }));
