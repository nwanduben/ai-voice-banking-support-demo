// Minimal n8n workflow runner for tests: executes the exported workflow JSON against in-memory "Google Sheets" tabs.
// Supports the node types these workflows use. Code nodes run in "all items" mode without $json (as in real n8n),
// so a stray `$json` in Code fails here just as it would in n8n.
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);

export function parseCsv(text) {
  const rows = []; let row = []; let cell = ''; let q = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (q) {
      if (ch === '"' && text[i + 1] === '"') { cell += '"'; i++; } else if (ch === '"') q = false; else cell += ch;
    } else if (ch === '"') q = true;
    else if (ch === ',') { row.push(cell); cell = ''; }
    else if (ch === '\n') { row.push(cell); rows.push(row); row = []; cell = ''; }
    else if (ch !== '\r') cell += ch;
  }
  if (cell || row.length) { row.push(cell); rows.push(row); }
  const [headers, ...data] = rows;
  return { headers, rows: data.filter((r) => r.length > 1 || r[0]).map((r) => Object.fromEntries(headers.map((h, i) => [h, r[i] ?? '']))) };
}

const TAB_FILES = { Customers: 'customers', Accounts: 'accounts', Cards: 'cards', Transactions: 'transactions', 'Digital Access': 'digital-access',
  Tickets: 'tickets', Disputes: 'disputes', 'Security Cases': 'security-cases', Sessions: 'sessions', Escalations: 'escalations',
  'Call Log': 'call-log', 'Branches & ATMs': 'branches-atms', 'Demo Scenarios': 'demo-scenarios', 'Test Callers': 'test-callers' };

export function loadBank(csvDir) {
  const tables = {};
  for (const [tab, file] of Object.entries(TAB_FILES)) tables[tab] = parseCsv(fs.readFileSync(path.join(csvDir, `${file}.csv`), 'utf8'));
  return tables;
}

export class Runner {
  constructor(workflow, tables, env = {}) {
    this.wf = workflow; this.tables = tables; this.env = env;
    this.nodes = Object.fromEntries(workflow.nodes.map((n) => [n.name, n]));
  }

  accessor(runData, current) {
    return (name) => {
      if (!this.nodes[name]) throw new Error(`No node named "${name}" (from ${current})`);
      if (!(name in runData)) {
        const fail = () => { throw new Error(`Referenced node "${name}" has not run yet (from ${current})`); };
        return { isExecuted: false, all: fail, first: fail, last: fail, get item() { return fail(); } };
      }
      const items = runData[name];
      return { isExecuted: true, all: () => items, first: () => items[0], last: () => items[items.length - 1], get item() { return items[0]; } };
    };
  }

  evalExpr(value, item, runData, current) {
    if (typeof value !== 'string' || !value.startsWith('=')) return value;
    const tpl = value.slice(1);
    const ctx = [item ? item.json : {}, this.accessor(runData, current), this.env,
      { toFormat: () => new Date().toISOString().slice(0, 10) }];
    const run = (expr) => new Function('$json', '$', '$env', '$now', `return (${expr});`)(...ctx);
    const whole = tpl.match(/^\{\{([\s\S]*)\}\}$/);
    if (whole && !whole[1].includes('}}')) return run(whole[1]);
    return tpl.replace(/\{\{([\s\S]*?)\}\}/g, (_, e) => { const v = run(e); return typeof v === 'object' ? JSON.stringify(v) : String(v ?? ''); });
  }

  run(triggerName, triggerItems) {
    const runData = {}; const out = { responses: [], emails: [], order: [] };
    const stack = [[triggerName, triggerItems]];
    while (stack.length) {
      const [name, input] = stack.pop();
      const node = this.nodes[name];
      if (!node) throw new Error(`Unknown node ${name}`);
      out.order.push(name);
      const outputs = this.exec(node, input, runData, out);
      runData[name] = outputs[0] && outputs[0].length ? outputs[0] : (outputs.find((o) => o && o.length) || []);
      const conns = (this.wf.connections[name] || {}).main || [];
      const next = [];
      conns.forEach((targets, idx) => {
        const items = outputs[idx] || [];
        if (!items.length) return;
        for (const t of targets) next.push([t.node, items]);
      });
      for (const n of next.reverse()) stack.push(n);
    }
    out.runData = runData;
    return out;
  }

  exec(node, input, runData, out) {
    const p = node.parameters; const t = node.type.replace('n8n-nodes-base.', '');
    const items = node.executeOnce ? input.slice(0, 1) : input;
    const ev = (v, item) => this.evalExpr(v, item, runData, node.name);
    switch (t) {
      case 'webhook': case 'manualTrigger': case 'scheduleTrigger': case 'noOp':
        return [input];
      case 'code': {
        const mode = p.mode || 'runOnceForAllItems';
        const $ = this.accessor(runData, node.name);
        if (mode === 'runOnceForAllItems') {
          const $input = { all: () => items, first: () => items[0], last: () => items[items.length - 1] };
          const res = new Function('$input', '$', '$env', 'require', p.jsCode)($input, $, this.env, require);
          if (!Array.isArray(res)) throw new Error(`Code node ${node.name} must return an array`);
          return [res.map((r) => (r.json ? r : { json: r }))];
        }
        return [items.map((item) => {
          const r = new Function('$json', '$input', '$', '$env', 'require', p.jsCode)(item.json, { item }, $, this.env, require);
          return r.json ? r : { json: r };
        })];
      }
      case 'if': {
        const yesI = []; const noI = [];
        for (const item of items) {
          const c = p.conditions.conditions[0];
          const v = ev(c.leftValue, item);
          (v === true || v === 'true' ? yesI : noI).push(item);
        }
        return [yesI, noI];
      }
      case 'switch': {
        const rules = p.rules.values; const outs = rules.map(() => []);
        for (const item of items) {
          const i = rules.findIndex((r) => r.conditions.conditions.every((c) => String(ev(c.leftValue, item)) === String(c.rightValue)));
          if (i >= 0) outs[i].push(item);
        }
        return outs;
      }
      case 'respondToWebhook': {
        const body = ev(p.responseBody, items[0]);
        out.responses.push({ status: (p.options && p.options.responseCode) || 200, body: typeof body === 'string' ? JSON.parse(body) : body });
        return [items];
      }
      case 'emailSend':
        for (const item of items) out.emails.push({ subject: ev(p.subject, item), text: ev(p.text, item), html: p.html ? ev(p.html, item) : null });
        return [items];
      case 'googleSheets': return [this.sheets(node, items, ev)];
      case 'crypto': {
        if (p.action !== 'hmac') throw new Error('engine: only crypto hmac supported');
        const c = require('crypto');
        return [items.map((item) => ({ ...item, json: { ...item.json,
          [p.dataPropertyName]: c.createHmac(p.type.toLowerCase(), p.secret).update(String(ev(p.value, item))).digest(p.encoding) } }))];
      }
      case 'stickyNote': return [[]];
      default: throw new Error(`Engine does not support node type ${node.type}`);
    }
  }

  sheets(node, items, ev) {
    const p = node.parameters; const tab = p.sheetName.value; const table = this.tables[tab];
    if (!table) throw new Error(`No tab named "${tab}" (node ${node.name})`);
    const pick = (json) => Object.fromEntries(table.headers.filter((h) => h in json).map((h) => [h, json[h] === null || json[h] === undefined ? '' : String(json[h])]));
    if (p.operation === 'read') {
      const res = [];
      for (const item of items.length ? items : [{ json: {} }]) {
        const filters = ((p.filtersUI || {}).values || []).map((f) => [f.lookupColumn, String(ev(f.lookupValue, item) ?? '')]);
        table.rows.forEach((row, i) => {
          if (filters.every(([col, val]) => String(row[col]) === val)) res.push({ json: { row_number: i + 2, ...row } });
        });
      }
      return res.length ? res : (node.alwaysOutputData ? [{ json: {} }] : []);
    }
    const match = (p.columns.matchingColumns || [])[0];
    for (const item of items) {
      const row = pick(item.json);
      const existing = match ? table.rows.find((r) => String(r[match]) === String(item.json[match])) : null;
      if (p.operation === 'append' || (p.operation === 'appendOrUpdate' && !existing)) {
        table.rows.push(Object.fromEntries(table.headers.map((h) => [h, row[h] ?? ''])));
      } else if (existing) Object.assign(existing, row);
    }
    return items;
  }
}
