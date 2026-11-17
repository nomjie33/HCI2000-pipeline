// Navigation tree T = (V, E) (proposal 3.2), loaded from data/tree.csv.
// Mirrors pipeline/io.py Tree so the logged on_path flag equals the pipeline's recomputed one.

export function parseCsv(text) {
  const rows = [];
  let row = [], field = "", i = 0, quoted = false;
  text = text.replace(/^﻿/, "");
  while (i < text.length) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') { field += '"'; i += 2; continue; }
      if (c === '"') { quoted = false; i++; continue; }
      field += c; i++; continue;
    }
    if (c === '"') { quoted = true; i++; continue; }
    if (c === ",") { row.push(field); field = ""; i++; continue; }
    if (c === "\r") { i++; continue; }
    if (c === "\n") { row.push(field); rows.push(row); row = []; field = ""; i++; continue; }
    field += c; i++;
  }
  if (field !== "" || row.length) { row.push(field); rows.push(row); }
  const [header, ...body] = rows.filter(r => r.length && !(r.length === 1 && r[0] === ""));
  return body.map(r => Object.fromEntries(header.map((h, j) => [h.trim(), (r[j] ?? "").trim()])));
}

export class Tree {
  constructor(rows) {
    this.rows = rows;
    this.nodes = new Map();
    for (const r of rows) {
      this.nodes.set(r.node_id, { id: r.node_id, parent: r.parent_id || null, level: Number(r.level), label: r.label, children: [] });
    }
    for (const n of this.nodes.values()) {
      if (n.parent && this.nodes.has(n.parent)) this.nodes.get(n.parent).children.push(n.id);
    }
    const roots = [...this.nodes.values()].filter(n => !n.parent);
    if (roots.length !== 1) throw new Error(`tree.csv must have exactly one root, found ${roots.length}`);
    this.root = roots[0].id;
  }
  has(id) { return this.nodes.has(id); }
  get(id) { return this.nodes.get(id); }
  label(id) { return this.nodes.get(id)?.label ?? id; }
  children(id) { return (this.nodes.get(id)?.children ?? []).map(c => this.nodes.get(c)); }
  isLeaf(id) { return (this.nodes.get(id)?.children.length ?? 0) === 0; }
  /** Correct path P* from the root to `id`, root first. */
  path(id) {
    const out = [];
    let cur = id;
    const seen = new Set();
    while (cur && this.nodes.has(cur) && !seen.has(cur)) { out.push(cur); seen.add(cur); cur = this.nodes.get(cur).parent; }
    return out.reverse();
  }
  /** Breadcrumb text "L1 › L2 › L3" for researcher screens. */
  trail(id) { return this.path(id).slice(1).map(n => this.label(n)).join(" › "); }
}
