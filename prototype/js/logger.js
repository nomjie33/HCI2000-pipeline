// Trial clock and event logger (proposal 4.3 "Automated timer and logger", App. B).
//
// One row per selection or navigation action, in exactly the columns pipeline/config.py
// REQUIRED_COLUMNS["events"] expects. Patterns never build rows themselves: they call
// api.select(nodeId) / api.nav(type, currentNodeAfter) and this module does the rest, so all
// three patterns log identically.

import * as store from "./store.js";

export const EVENT_COLUMNS = [
  "participant_id", "trial_id", "sequence", "block_position", "trial_order", "pattern", "task_id",
  "task_pair", "target_node", "min_selections", "t_ms", "event_type", "node_id",
  "current_node_after", "on_path",
];

export const NAV_EVENTS = new Set(["menu_open", "menu_close", "collapse", "back", "logo"]);

export class Trial {
  /**
   * @param {object} meta   participant_id, trial_id, sequence, block_position, trial_order, pattern,
   *                        task_id, task_pair, target_node, min_selections
   * @param {Tree}   tree
   * @param {object} opts   { timeLimitMs, record (false for practice), onLeafPage(nodeId, isTarget), onEnd(reason) }
   */
  constructor(meta, tree, opts) {
    this.meta = meta;
    this.tree = tree;
    this.opts = opts;
    this.pathSet = new Set(tree.path(meta.target_node));
    this.current = tree.root;
    this.beforeLeaf = null;     // node shown before a leaf page opened (Back returns here)
    this.ended = false;
    this.rows = [];
    this.t0 = null;
    this.timer = null;
  }

  now() { return Math.round(performance.now() - this.t0); }

  log(event_type, node_id, current_node_after, t_ms) {
    const row = {
      ...this.meta,
      t_ms,
      event_type,
      node_id: node_id || "",
      current_node_after,
      on_path: this.pathSet.has(current_node_after) ? 1 : 0,
    };
    this.rows.push(row);
    if (this.opts.record) store.update(s => { s.activeTrial.rows.push(row); });
    return row;
  }

  start() {
    this.t0 = performance.now();
    if (this.opts.record) {
      store.update(s => { s.activeTrial = { trial_id: this.meta.trial_id, participant_id: this.meta.participant_id, rows: [] }; });
    }
    this.log("start", "", this.tree.root, 0);
    this.timer = setTimeout(() => this.timeout(), this.opts.timeLimitMs);
  }

  /** Returns the timestamp for an action, or null if the trial is over (ended or past the limit). */
  stamp() {
    if (this.ended) return null;
    const t = this.now();
    if (t >= this.opts.timeLimitMs) { this.timeout(); return null; }
    return t;
  }

  /** A tap on a menu node (proposal 3.2 "selection"). */
  select(nodeId) {
    if (!this.tree.has(nodeId)) throw new Error(`unknown node ${nodeId}`);
    const t = this.stamp();
    if (t === null) return;
    if (this.tree.isLeaf(nodeId)) {
      this.beforeLeaf = this.current;
      this.current = nodeId;
      this.log("select", nodeId, nodeId, t);
      const isTarget = nodeId === this.meta.target_node;
      if (isTarget) {
        this.log("target_reached", nodeId, nodeId, t);
        this.end("target");
      } else {
        this.opts.onLeafPage?.(nodeId);
      }
      return;
    }
    this.current = nodeId;
    this.log("select", nodeId, nodeId, t);
  }

  /** A navigation action that is not a selection (menu_open/close, collapse, back, logo). */
  nav(type, currentNodeAfter) {
    if (!NAV_EVENTS.has(type)) throw new Error(`not a navigation event: ${type}`);
    if (!this.tree.has(currentNodeAfter)) throw new Error(`unknown node ${currentNodeAfter}`);
    const t = this.stamp();
    if (t === null) return;
    this.current = currentNodeAfter;
    this.log(type, "", currentNodeAfter, t);
  }

  /** Back control on the placeholder ("not the page") screen: return to the view before the leaf. */
  backFromPage() {
    const to = this.beforeLeaf ?? this.tree.root;
    this.beforeLeaf = null;
    this.nav("back", to);
  }

  giveUp() {
    const t = this.stamp();
    if (t === null) return;
    this.log("give_up", "", this.current, t);
    this.end("give_up");
  }

  timeout() {
    if (this.ended) return;
    this.log("timeout", "", this.current, this.opts.timeLimitMs);
    this.end("timeout");
  }

  end(reason) {
    if (this.ended) return;
    this.ended = true;
    clearTimeout(this.timer);
    if (this.opts.record) {
      store.update(s => {
        s.events.push(...s.activeTrial.rows);
        s.activeTrial = null;
      });
    }
    this.opts.onEnd?.(reason);
  }

  /** Stop without a terminal event (researcher abort). The rows move to the interrupted audit list. */
  abort(reason) {
    if (this.ended) return;
    this.ended = true;
    clearTimeout(this.timer);
    if (this.opts.record) recoverInterrupted(reason);
  }
}

/** Move a half-finished trial (after reload or abort) into the interrupted audit list. */
export function recoverInterrupted(reason = "reload during trial") {
  const s = store.get();
  if (!s.activeTrial) return null;
  const at = s.activeTrial;
  store.update(st => {
    st.interrupted.push(...at.rows.map(r => ({ ...r, interrupt_reason: reason, interrupted_at: new Date().toISOString() })));
    st.activeTrial = null;
  });
  return at;
}
