const all = (n) => $(n).all().map((i) => i.json).filter((r) => r && Object.keys(r).length);
const since = Date.now() - 86400e3;
const recent = (rows, col) => rows.filter((r) => { const d = parseWAT(r[col]); return d && d.getTime() >= since; });
const sessions = recent(all('Read Sessions'), 'updated_at');
const esc = recent(all('Read Escalations'), 'created_at');
const sec = recent(all('Read Security Cases'), 'created_at');
const tickets = all('Read Tickets');
const breached = tickets.filter((t) => parseWAT(t.sla_due) < new Date() && !['resolved', 'closed'].includes(t.status));
const byRisk = sessions.reduce((m, s) => ({ ...m, [s.max_risk || 'LOW']: (m[s.max_risk || 'LOW'] || 0) + 1 }), {});
const breachedIds = breached.slice(0, 10).map((t) => t.ticket_id).join(', ');
const text = `ENTIN voice support - last 24 hours: ${sessions.length} calls, ${esc.length} handoffs, ${sec.length} security cases, ${breached.length} tickets past SLA.`;
return [{ json: { subject: `ENTIN daily voice-support report · ${fmtWAT(new Date()).slice(0, 10)}`, text, date: fmtWAT(new Date()).slice(0, 10),
  calls: sessions.length, high: byRisk.HIGH || 0, medium: byRisk.MEDIUM || 0, low: byRisk.LOW || 0,
  secrets: sessions.filter((s) => s.secret_detected === 'yes').length, handoffs: esc.length, security_cases: sec.length,
  tickets_created: recent(tickets, 'created_at').filter((t) => t.created_by === 'voice_agent').length,
  breached: breached.length, breached_ids: breachedIds } }];
