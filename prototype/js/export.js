// Export a pipeline-ready dataset folder as a ZIP (docs/ANALYSIS_PLAN.md 1.1):
//   events.csv, ratings.csv, participants.csv (header template), exclusions.csv (header template),
//   reference/tree.csv, reference/tasks.csv, plus audit files session_info.csv and interrupted_trials.csv.
// No libraries: a minimal "stored" (uncompressed) ZIP writer is enough for a few hundred KB of CSV.

import { EVENT_COLUMNS } from "./logger.js";

export const RATING_COLUMNS = ["participant_id", "trial_id", "difficulty_rating"];
export const PARTICIPANT_COLUMNS = [
  "participant_id", "sequence", "age", "gender", "gov_familiarity", "used_reference_site",
  "rank_DH", "rank_MM", "rank_ND", "comments",
];
export const EXCLUSION_COLUMNS = ["trial_id", "reason"];

function cell(v) {
  const s = v === null || v === undefined ? "" : String(v);
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export function toCsv(columns, rows) {
  return [columns.join(","), ...rows.map(r => columns.map(c => cell(r[c])).join(","))].join("\n") + "\n";
}

// ---- ZIP (store method) -------------------------------------------------------------------
const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();

function crc32(bytes) {
  let c = 0xffffffff;
  for (let i = 0; i < bytes.length; i++) c = CRC_TABLE[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function dosDateTime(d) {
  const time = (d.getHours() << 11) | (d.getMinutes() << 5) | Math.floor(d.getSeconds() / 2);
  const date = ((d.getFullYear() - 1980) << 9) | ((d.getMonth() + 1) << 5) | d.getDate();
  return { time, date };
}

/** @param files {name: string, text: string}[]  @returns Blob (application/zip) */
export function makeZip(files) {
  const enc = new TextEncoder();
  const { time, date } = dosDateTime(new Date());
  const local = [], central = [];
  let offset = 0;
  for (const f of files) {
    const name = enc.encode(f.name);
    const data = enc.encode(f.text);
    const crc = crc32(data);
    const h = new DataView(new ArrayBuffer(30));
    h.setUint32(0, 0x04034b50, true); h.setUint16(4, 20, true); h.setUint16(6, 0x0800, true); // UTF-8 names
    h.setUint16(8, 0, true); h.setUint16(10, time, true); h.setUint16(12, date, true);
    h.setUint32(14, crc, true); h.setUint32(18, data.length, true); h.setUint32(22, data.length, true);
    h.setUint16(26, name.length, true); h.setUint16(28, 0, true);
    local.push(new Uint8Array(h.buffer), name, data);

    const c = new DataView(new ArrayBuffer(46));
    c.setUint32(0, 0x02014b50, true); c.setUint16(4, 20, true); c.setUint16(6, 20, true);
    c.setUint16(8, 0x0800, true); c.setUint16(10, 0, true); c.setUint16(12, time, true); c.setUint16(14, date, true);
    c.setUint32(16, crc, true); c.setUint32(20, data.length, true); c.setUint32(24, data.length, true);
    c.setUint16(28, name.length, true); c.setUint16(30, 0, true); c.setUint16(32, 0, true);
    c.setUint16(34, 0, true); c.setUint16(36, 0, true); c.setUint32(38, 0, true); c.setUint32(42, offset, true);
    central.push(new Uint8Array(c.buffer), name);
    offset += 30 + name.length + data.length;
  }
  const cdSize = central.reduce((n, a) => n + a.length, 0);
  const e = new DataView(new ArrayBuffer(22));
  e.setUint32(0, 0x06054b50, true); e.setUint16(8, files.length, true); e.setUint16(10, files.length, true);
  e.setUint32(12, cdSize, true); e.setUint32(16, offset, true);
  return new Blob([...local, ...central, new Uint8Array(e.buffer)], { type: "application/zip" });
}

// ---- dataset ------------------------------------------------------------------------------
/**
 * Build the export file list.
 * @param s       store state
 * @param ids     participant ids to include
 * @param study   study.json
 * @param treeRows rows of data/tree.csv
 * @param patternStatus {DH: "todo"|"ready", ...}
 */
export function buildDataset(s, ids, study, treeRows, patternStatus) {
  const want = new Set(ids);
  const events = s.events.filter(r => want.has(r.participant_id));
  const ratings = s.ratings.filter(r => want.has(r.participant_id));
  const interrupted = s.interrupted.filter(r => want.has(r.participant_id));

  const tasks = Object.entries(study.tasks).map(([task_id, t]) => ({ task_id, task_pair: t.pair, target_node: t.target }));
  const participants = ids.map(id => ({ participant_id: id, sequence: s.sessions[id]?.sequence ?? "" }));

  const info = ids.map(id => {
    const ss = s.sessions[id] ?? {};
    return {
      participant_id: id,
      sequence: ss.sequence,
      pair_order: ss.pairOrder,
      started_at: ss.createdAt,
      finished_at: ss.finishedAt ?? "",
      completed_trials: events.filter(r => r.participant_id === id && r.event_type === "start").length,
      skipped_blocks: (ss.skipped ?? []).map(b => `block${b.block_position}:${b.pattern}`).join(" "),
      test_session: ss.testSession ? 1 : 0,
      app_version: study.appVersion,
      pattern_status: Object.entries(patternStatus).map(([p, st]) => `${p}=${st}`).join(" "),
      exported_at: new Date().toISOString(),
    };
  });

  const files = [
    { name: "events.csv", text: toCsv(EVENT_COLUMNS, events) },
    { name: "ratings.csv", text: toCsv(RATING_COLUMNS, ratings) },
    // Only participant_id and sequence are known on the device; fill the rest from the Google Form.
    { name: "participants.csv", text: toCsv(PARTICIPANT_COLUMNS, participants) },
    { name: "exclusions.csv", text: toCsv(EXCLUSION_COLUMNS, []) },
    { name: "reference/tree.csv", text: toCsv(["node_id", "parent_id", "level", "label"], treeRows) },
    { name: "reference/tasks.csv", text: toCsv(["task_id", "task_pair", "target_node"], tasks) },
    { name: "session_info.csv", text: toCsv(Object.keys(info[0] ?? { participant_id: "" }), info) },
  ];
  if (interrupted.length) {
    files.push({ name: "interrupted_trials.csv", text: toCsv([...EVENT_COLUMNS, "interrupt_reason", "interrupted_at"], interrupted) });
  }
  return files;
}

function stamp(d = new Date()) {
  const p = n => String(n).padStart(2, "0");
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}`;
}

/** Hand the ZIP to the user: share sheet where supported (e.g. save to Drive), else a download. */
export async function deliver(files, label) {
  const name = `hci2000_export_${label}_${stamp()}.zip`;
  const blob = makeZip(files);
  const file = new File([blob], name, { type: "application/zip" });
  if (navigator.canShare?.({ files: [file] })) {
    try {
      await navigator.share({ files: [file], title: name });
      return { name, via: "share" };
    } catch (e) {
      if (e.name === "AbortError") return { name, via: "cancelled" };
      // fall through to download
    }
  }
  downloadBlob(blob, name);
  return { name, via: "download" };
}

export function downloadBlob(blob, name) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}
