// Experiment shell: researcher setup (Latin square), briefing, practice, blocks of timed tasks,
// SEQ ratings, researcher area and export. Proposal 4.4-4.5 and Appendix C.

import * as store from "./store.js";
import { Tree, parseCsv } from "./tree.js";
import { Trial, recoverInterrupted } from "./logger.js";
import { buildDataset, deliver } from "./export.js";
import { PATTERNS, patternStatus, isReady } from "./patterns/index.js";
import practicePattern from "./patterns/practice.js";
import { el } from "./patterns/common.js";

let study, tree, treeRows, practiceTree;
const frame = document.getElementById("frame");
const app = document.getElementById("app");
let currentTrial = null;     // running Trial (experimental or practice)
let mounted = null;          // mounted pattern instance
let practiceState = null;    // in-memory practice phase (never stored)
let wakeLock = null;

// ---------------------------------------------------------------------------------------------
// boot
// ---------------------------------------------------------------------------------------------
async function boot() {
  try {
    const [s, t] = await Promise.all([
      fetch("data/study.json").then(r => r.json()),
      fetch("data/tree.csv").then(r => r.text()),
    ]);
    study = s;
    treeRows = parseCsv(t);
    tree = new Tree(treeRows);
    practiceTree = new Tree([
      { node_id: "ROOT", parent_id: "", level: 0, label: study.practice.siteName },
      ...study.practice.pages.map(p => ({ node_id: p.id, parent_id: "ROOT", level: 1, label: p.label })),
    ]);
    checkStudy();
  } catch (e) {
    app.replaceChildren(screen("error", [el("h1", {}, "Could not load the study files"), el("pre", {}, String(e.stack || e))]));
    return;
  }
  trapSystemBack();
  setupCorner();
  store.requestPersistence();
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible" && store.get().activeSession) keepAwake(); });

  // A reload in the middle of a timed trial: the half trial goes to the audit list, the trial re-runs.
  const s = store.get();
  if (s.activeTrial) {
    recoverInterrupted("app reloaded during trial");
    const sess = s.sessions[s.activeSession];
    if (sess) store.update(() => { sess.progress.phase = "interrupted"; });
  }
  if (s.activeSession) keepAwake();
  render();
}

function checkStudy() {
  for (const [id, t] of Object.entries(study.tasks)) {
    if (!tree.has(t.target)) throw new Error(`study.json: target ${t.target} of ${id} is not in tree.csv`);
    if (!tree.isLeaf(t.target)) throw new Error(`study.json: target ${t.target} of ${id} is not a leaf`);
  }
  if (!practiceTree.has(study.practice.target)) throw new Error("study.json: practice target not in practice pages");
}

const pin = () => store.get().pin ?? study.researcherPin;

// ---------------------------------------------------------------------------------------------
// session plan (Table 3 Latin square + within-pair alternation)
// ---------------------------------------------------------------------------------------------
function buildPlan(sequence, pairOrder) {
  const plan = [];
  let order = 0;
  study.latinSquare[sequence].forEach(([pattern, pair], i) => {
    const ids = [...study.pairs[pair]];
    if (pairOrder === "reversed") ids.reverse();
    for (const task_id of ids) {
      order += 1;
      plan.push({
        block_position: i + 1, trial_order: order, pattern, task_id, task_pair: pair,
        target_node: study.tasks[task_id].target, min_selections: study.minSelections[pattern],
      });
    }
  });
  return plan;
}

function buildSteps(sess) {
  const steps = [{ kind: "briefing" }, { kind: "practice" }];
  for (let b = 1; b <= 3; b++) {
    steps.push({ kind: "block", block: b });
    sess.plan.forEach((t, i) => { if (t.block_position === b) steps.push({ kind: "trial", index: i }); });
  }
  steps.push({ kind: "end" });
  return steps;
}

function trialMeta(sess, t) {
  return {
    participant_id: sess.participant_id,
    trial_id: `${sess.participant_id}_${t.task_id}`,
    sequence: sess.sequence,
    block_position: t.block_position,
    trial_order: t.trial_order,
    pattern: t.pattern,
    task_id: t.task_id,
    task_pair: t.task_pair,
    target_node: t.target_node,
    min_selections: t.min_selections,
  };
}

function suggestions(excludeId = null) {
  const s = store.get();
  const ids = s.sessionOrder.filter(id => id !== excludeId && s.sessions[id]);
  const seqs = Object.keys(study.latinSquare);
  const nextSeq = seqs[ids.length % seqs.length];
  let maxN = 0;
  for (const id of ids) { const m = /^P(\d+)$/.exec(id); if (m) maxN = Math.max(maxN, Number(m[1])); }
  const nextId = `P${String(maxN + 1).padStart(2, "0")}`;
  const orderFor = seq => (ids.filter(id => s.sessions[id].sequence === seq).length % 2 === 0 ? "standard" : "reversed");
  return { nextSeq, nextId, orderFor };
}

// ---------------------------------------------------------------------------------------------
// rendering
// ---------------------------------------------------------------------------------------------
function screen(cls, children) { return el("div", { class: `screen ${cls}` }, children); }
function btn(label, onClick, cls = "") {
  const b = el("button", { class: `btn ${cls}`.trim(), type: "button" }, label);
  b.addEventListener("click", onClick);
  return b;
}
function show(node) {
  closeModals();
  unmountPattern();
  app.replaceChildren(node);
  app.scrollTop = 0;
}
function unmountPattern() { mounted?.unmount?.(); mounted = null; }

function activeSession() {
  const s = store.get();
  return s.activeSession ? s.sessions[s.activeSession] : null;
}

function render() {
  const sess = activeSession();
  if (!sess) { renderHome(); return; }
  const steps = buildSteps(sess);
  const step = steps[sess.progress.step];
  if (!step) { finishSession(sess); return; }
  if (sess.progress.phase === "interrupted") { renderInterrupted(sess); return; }
  switch (step.kind) {
    case "briefing": renderBriefing(sess); break;
    case "practice": renderPractice(sess); break;
    case "block": renderBlockIntro(sess, step.block); break;
    case "trial": renderTrialStep(sess, step.index); break;
    case "end": finishSession(sess); break;
  }
}

function advance(sess, by = 1) {
  store.update(() => { sess.progress.step += by; sess.progress.phase = "task"; });
  render();
}

// ---- home / researcher ------------------------------------------------------------------------
function renderHome() {
  const s = store.get();
  const todo = Object.entries(patternStatus()).filter(([, st]) => st !== "ready").map(([p]) => p);
  show(screen("home", [
    el("div", { class: "home-mark", "aria-hidden": "true" }),
    el("h1", {}, "Navigation Study"),
    el("p", { class: "muted" }, "HCI2000 · Group 6 · researcher device"),
    el("p", { class: "muted small" }, `Build ${study.appVersion} · ${s.sessionOrder.length} session(s) stored on this device`),
    todo.length ? el("p", { class: "banner warn" }, `TODO: ${todo.join(", ")} not built yet; sessions on this build are test-only.`) : null,
    btn("Researcher", () => askPin("Researcher PIN", renderResearcher), "primary block"),
  ]));
}

function renderResearcher() {
  const s = store.get();
  const sess = activeSession();
  const rows = s.sessionOrder.filter(id => s.sessions[id]).map(id => {
    const ss = s.sessions[id];
    const done = new Set(s.events.filter(r => r.participant_id === id && r.event_type === "start").map(r => r.trial_id)).size;
    const status = ss.finishedAt ? "finished" : (s.activeSession === id ? "in progress" : "stopped");
    return el("tr", {}, [
      el("td", {}, [id, ss.testSession ? el("span", { class: "badge" }, "test") : null]),
      el("td", {}, ss.sequence),
      el("td", {}, ss.pairOrder === "reversed" ? "rev" : "std"),
      el("td", {}, `${done}/6`),
      el("td", {}, [status, ss.exportedAt ? el("div", { class: "tiny" }, "exported") : null]),
      el("td", { class: "actions" }, [
        btn("Export", () => doExport([id], id), "small"),
        btn("Delete", () => confirmDelete(id), "small danger"),
      ]),
    ]);
  });
  const persisted = el("span", {}, "checking…");
  navigator.storage?.persisted?.().then(p => { persisted.textContent = p ? "persistent" : "not guaranteed (export after every session)"; })
    .catch(() => { persisted.textContent = "unknown"; });

  show(screen("researcher", [
    el("h1", {}, "Researcher area"),
    sess ? el("div", { class: "card" }, [
      el("p", {}, ["Session ", el("b", {}, sess.participant_id), ` (${sess.sequence}) is in progress.`]),
      el("div", { class: "row" }, [
        btn("Resume session", () => render(), "primary"),
        btn("End session now", () => confirmText("End this session now?", "Remaining tasks will not be run. Type END to confirm.", "END", () => finishSession(sess, true)), "danger"),
      ]),
    ]) : btn("New session", renderSetup, "primary block"),
    el("h2", {}, "Sessions on this device"),
    rows.length
      ? el("table", { class: "tbl" }, [el("thead", {}, el("tr", {}, ["ID", "Seq", "Order", "Trials", "Status", ""].map(h => el("th", {}, h)))), el("tbody", {}, rows)])
      : el("p", { class: "muted" }, "No sessions yet."),
    el("div", { class: "row" }, [
      btn("Export all sessions", () => doExport(s.sessionOrder.filter(id => s.sessions[id]), "all"), rows.length ? "primary" : "", ),
    ]),
    el("p", { class: "small muted" }, "Export after every session and upload the ZIP to the team Google Drive. Data never leaves this phone otherwise."),
    el("h2", {}, "Patterns in this build"),
    el("ul", { class: "plain" }, Object.entries(PATTERNS).map(([code, p]) =>
      el("li", {}, [el("b", {}, code), ` ${study.patterns[code]} `, p.status === "ready" ? el("span", { class: "badge ok" }, "ready") : el("span", { class: "badge todo" }, "TODO – not built")]))),
    el("h2", {}, "Device"),
    el("ul", { class: "plain small" }, [
      el("li", {}, ["Storage: ", persisted]),
      el("li", {}, `Stored rows: ${s.events.length} events, ${s.ratings.length} ratings, ${s.interrupted.length} interrupted`),
      el("li", {}, `Build ${study.appVersion}`),
      store.isMemoryOnly() ? el("li", { class: "banner warn" }, "Storage is failing: data is in memory only. Export now.") : null,
    ]),
    el("div", { class: "row" }, [
      btn("Change PIN", changePin),
      btn("Clear all data", () => confirmText("Delete ALL data on this device?", "This cannot be undone. Export first. Type DELETE to confirm.", "DELETE", () => { store.clearAll(); renderResearcher(); }), "danger"),
    ]),
    btn("Close researcher area", () => render(), "block"),
  ]));
}

async function doExport(ids, label) {
  if (!ids.length) { toast("Nothing to export yet."); return; }
  const files = buildDataset(store.get(), ids, study, treeRows, patternStatus());
  const res = await deliver(files, label);
  if (res.via !== "cancelled") {
    store.update(s => { for (const id of ids) if (s.sessions[id]) s.sessions[id].exportedAt = new Date().toISOString(); });
    toast(res.via === "share" ? `Shared ${res.name}` : `Downloaded ${res.name}`);
    if (app.querySelector(".researcher")) renderResearcher();
  }
}

function confirmDelete(id) {
  confirmText(`Delete session ${id}?`, `Its events, ratings and interrupted rows are removed from this device. Type ${id} to confirm.`, id, () => {
    store.update(s => {
      delete s.sessions[id];
      s.sessionOrder = s.sessionOrder.filter(x => x !== id);
      s.events = s.events.filter(r => r.participant_id !== id);
      s.ratings = s.ratings.filter(r => r.participant_id !== id);
      s.interrupted = s.interrupted.filter(r => r.participant_id !== id);
      if (s.activeSession === id) { s.activeSession = null; s.activeTrial = null; }
    });
    renderResearcher();
  });
}

// ---- setup: participant + sequence (Latin square) --------------------------------------------
function renderSetup() {
  const sug = suggestions();
  const state = { id: sug.nextId, seq: sug.nextSeq, order: sug.orderFor(sug.nextSeq), orderTouched: false, testOk: false };
  const todoCodes = Object.keys(PATTERNS).filter(p => !isReady(p));

  const idInput = el("input", { class: "input", value: state.id, autocapitalize: "characters", autocomplete: "off", spellcheck: "false", inputmode: "text" });
  const idMsg = el("p", { class: "field-msg" });
  const seqBox = el("div", { class: "seg" });
  const orderBox = el("div", { class: "seg" });
  const matrix = el("div");
  const planBox = el("div");
  const testBox = el("label", { class: "check" });
  const startBtn = btn("Start session", start, "primary block");

  idInput.addEventListener("input", () => { state.id = idInput.value.trim().toUpperCase(); refresh(); });

  function refresh() {
    const s = store.get();
    let idErr = "";
    if (!/^P\d{2,3}$/.test(state.id)) idErr = "Use the format P01.";
    else if (s.sessions[state.id]) idErr = `${state.id} already exists on this device. Pick another ID, or delete that session first.`;
    idMsg.textContent = idErr;
    idMsg.className = `field-msg ${idErr ? "err" : ""}`;

    seqBox.replaceChildren(...Object.keys(study.latinSquare).map(seq => {
      const b = btn([seq, seq === sug.nextSeq ? el("span", { class: "tiny" }, "next") : null], () => {
        state.seq = seq;
        if (!state.orderTouched) state.order = sug.orderFor(seq);
        refresh();
      }, `seg-btn ${state.seq === seq ? "on" : ""}`);
      return b;
    }));
    const sugOrder = sug.orderFor(state.seq);
    orderBox.replaceChildren(...[["standard", "Standard (1st, 2nd)"], ["reversed", "Reversed (2nd, 1st)"]].map(([v, label]) =>
      btn([label, v === sugOrder ? el("span", { class: "tiny" }, "suggested") : null], () => { state.order = v; state.orderTouched = true; refresh(); },
        `seg-btn ${state.order === v ? "on" : ""}`)));

    matrix.replaceChildren(latinSquareTable(state.seq));

    const plan = buildPlan(state.seq, state.order);
    planBox.replaceChildren(el("table", { class: "tbl plan" }, [
      el("thead", {}, el("tr", {}, ["#", "Block", "Pattern", "Task", "Target (L1 › L2 › L3)"].map(h => el("th", {}, h)))),
      el("tbody", {}, [
        el("tr", { class: "practice-row" }, [el("td", {}, "–"), el("td", {}, "practice"), el("td", {}, "flat list"), el("td", {}, study.practice.task_id), el("td", {}, practiceTree.label(study.practice.target))]),
        ...plan.map(t => el("tr", { class: isReady(t.pattern) ? "" : "todo-row" }, [
          el("td", {}, t.trial_order), el("td", {}, t.block_position),
          el("td", {}, [t.pattern, isReady(t.pattern) ? null : el("span", { class: "badge todo" }, "TODO")]),
          el("td", {}, t.task_id), el("td", { class: "small" }, tree.trail(t.target_node)),
        ])),
      ]),
    ]));

    const needsTest = study.latinSquare[state.seq].some(([p]) => !isReady(p));
    testBox.replaceChildren();
    if (needsTest) {
      const cb = el("input", { type: "checkbox" });
      cb.checked = state.testOk;
      cb.addEventListener("change", () => { state.testOk = cb.checked; refresh(); });
      testBox.append(cb, ` I understand ${todoCodes.join(" and ")} ${todoCodes.length > 1 ? "are" : "is"} not built: this is a test session and those blocks will be skipped.`);
    }
    startBtn.disabled = !!idErr || (needsTest && !state.testOk);
  }

  function start() {
    const needsTest = study.latinSquare[state.seq].some(([p]) => !isReady(p));
    const sess = {
      participant_id: state.id, sequence: state.seq, pairOrder: state.order,
      plan: buildPlan(state.seq, state.order), createdAt: new Date().toISOString(),
      testSession: needsTest, skipped: [], progress: { step: 0, phase: "task" }, finishedAt: null,
    };
    store.update(s => { s.sessions[sess.participant_id] = sess; s.sessionOrder.push(sess.participant_id); s.activeSession = sess.participant_id; });
    keepAwake();
    render();
  }

  show(screen("setup", [
    el("h1", {}, "New session"),
    todoCodes.length ? el("p", { class: "banner warn" }, `${todoCodes.length} of 3 patterns not implemented (${todoCodes.join(", ")}): sessions on this build are test-only.`) : null,
    el("label", { class: "field" }, ["Participant ID", idInput]), idMsg,
    el("h2", {}, "Sequence"), seqBox,
    el("h2", {}, "Task order within each pair"),
    el("p", { class: "small muted" }, "Alternates between consecutive participants in the same sequence (proposal 4.4). Suggested from the sessions already on this device."),
    orderBox,
    el("h2", {}, "Latin square (Table 3)"), matrix,
    el("h2", {}, "This participant's tasks"), planBox,
    testBox,
    startBtn,
    btn("Cancel", renderResearcher, "block"),
  ]));
  refresh();
}

function latinSquareTable(selected) {
  return el("table", { class: "tbl matrix" }, [
    el("thead", {}, el("tr", {}, ["", "Block 1", "Block 2", "Block 3"].map(h => el("th", {}, h)))),
    el("tbody", {}, Object.entries(study.latinSquare).map(([seq, blocks]) =>
      el("tr", { class: seq === selected ? "sel" : "" }, [
        el("th", {}, seq),
        ...blocks.map(([p, pair]) => el("td", { class: isReady(p) ? "" : "todo-cell" }, [
          el("b", {}, p), ` · pair ${pair}`,
          el("div", { class: "tiny" }, `(${study.pairs[pair].join(", ")})`),
          isReady(p) ? null : el("span", { class: "badge todo", title: "Pattern not built yet" }, "TODO"),
        ])),
      ]))),
  ]);
}

// ---- participant screens ------------------------------------------------------------------------
function renderBriefing(sess) {
  show(screen("participant", [
    el("h1", {}, "Welcome"),
    el("p", {}, "Thank you for taking part. Today you will use a website on this phone to find pages about government services. We are testing the website's menus, not you, and there are no right or wrong ways to look."),
    el("p", {}, "For each task, you will see a short situation on the screen. Read it, then tap Start. A timer runs while you look for the page, so please work as you normally would. When you reach the right page, the screen will tell you the task is complete."),
    el("p", {}, "If you open a page that is not the one you need, you can go back and keep looking. If you cannot find the page, you can tap Give up at any time. After each task, you will rate how difficult it was."),
    el("p", {}, "You will start with one practice task on a different website."),
    btn("Continue", () => advance(sess), "primary block"),
  ]));
}

function renderPractice(sess) {
  const phase = practiceState?.sid === sess.participant_id ? practiceState.phase : "task";
  practiceState = { sid: sess.participant_id, phase };
  const p = study.practice;
  const meta = { participant_id: sess.participant_id, trial_id: `${sess.participant_id}_${p.task_id}`, pattern: "PRACTICE", task_id: p.task_id, target_node: p.target };
  if (phase === "task") {
    renderTaskScreen({ heading: "Practice task", sub: "This one is for practice only.", scenario: p.scenario }, () => {
      practiceState.phase = "running";
      runTrial({ meta, tree: practiceTree, pattern: practicePattern, record: false, scenario: p.scenario, extra: { siteName: p.siteName } },
        reason => { practiceState.phase = "done"; renderDone(reason, () => { practiceState.phase = "rating"; render(); }); });
    });
  } else if (phase === "done" || phase === "running") {
    practiceState.phase = "task"; render();
  } else if (phase === "rating") {
    renderRating(() => { practiceState = null; advance(sess); }, true);
  }
}

function renderBlockIntro(sess, block) {
  const t = sess.plan.find(x => x.block_position === block);
  const nTasks = sess.plan.filter(x => x.block_position === block).length;
  if (!isReady(t.pattern)) {
    show(screen("participant stub", [
      el("p", { class: "eyebrow" }, `Menu style ${block} of 3`),
      el("h1", {}, `Pattern not yet implemented (${t.pattern})`),
      el("p", {}, `${study.patterns[t.pattern]} is still TODO in this build (prototype/js/patterns/index.js). Its ${nTasks} tasks are skipped and recorded in session_info.csv.`),
      btn("Skip block", () => {
        store.update(() => sess.skipped.push({ block_position: block, pattern: t.pattern }));
        advance(sess, 1 + nTasks);
      }, "primary block"),
    ]));
    return;
  }
  show(screen("participant", [
    el("p", { class: "eyebrow" }, `Menu style ${block} of 3`),
    el("h1", {}, block === 1 ? "Let's begin" : "Next menu style"),
    el("p", {}, `The website now uses a different menu. You will do ${nTasks} tasks with it.`),
    block > 1 ? el("p", { class: "muted" }, "You can take a short break now. Tap Continue when you are ready.") : null,
    btn("Continue", () => advance(sess), "primary block"),
  ]));
}

function renderTrialStep(sess, index) {
  const t = sess.plan[index];
  const meta = trialMeta(sess, t);
  const phase = sess.progress.phase;
  const setPhase = ph => store.update(() => { sess.progress.phase = ph; });

  if (phase === "running") {
    // Trial was committed but the phase write was lost, or it never started: recover safely.
    const committed = store.get().events.some(r => r.trial_id === meta.trial_id && ["target_reached", "give_up", "timeout"].includes(r.event_type));
    setPhase(committed ? "rating" : "task");
    render();
    return;
  }
  if (phase === "task") {
    renderTaskScreen({ heading: `Task ${t.trial_order} of ${sess.plan.length}`, scenario: study.tasks[t.task_id].scenario }, () => {
      // Remove leftovers of an earlier (interrupted) run of this trial id, so it is logged exactly once.
      store.update(s => {
        s.events = s.events.filter(r => r.trial_id !== meta.trial_id);
        s.ratings = s.ratings.filter(r => r.trial_id !== meta.trial_id);
      });
      setPhase("running");
      runTrial({ meta, tree, pattern: PATTERNS[t.pattern].module, record: true, scenario: study.tasks[t.task_id].scenario },
        reason => { store.update(() => { sess.progress.phase = "done"; sess.progress.reason = reason; }); render(); });
    });
  } else if (phase === "done") {
    renderDone(sess.progress.reason, () => { setPhase("rating"); render(); });
  } else if (phase === "rating") {
    renderRating(value => {
      store.update(s => {
        s.ratings = s.ratings.filter(r => r.trial_id !== meta.trial_id);
        s.ratings.push({ participant_id: sess.participant_id, trial_id: meta.trial_id, difficulty_rating: value });
      });
      advance(sess);
    });
  }
}

function renderTaskScreen({ heading, sub, scenario }, onStart) {
  show(screen("participant task", [
    el("p", { class: "eyebrow" }, heading),
    sub ? el("p", { class: "muted small" }, sub) : null,
    el("div", { class: "scenario" }, scenario),
    el("p", { class: "muted small" }, "The timer starts when you tap Start."),
    btn("Start", onStart, "primary block big"),
  ]));
}

function renderDone(reason, onNext) {
  const text = {
    target: ["Task complete", "You found the page."],
    give_up: ["Task ended", "That's fine. Let's move on."],
    timeout: ["Time is up", "That's fine. Let's move on."],
  }[reason] ?? ["Task ended", ""];
  show(screen(`participant done ${reason}`, [
    el("div", { class: "done-mark", "aria-hidden": "true" }, reason === "target" ? "✓" : "•"),
    el("h1", {}, text[0]),
    el("p", {}, text[1]),
    btn("Continue", onNext, "primary block"),
  ]));
}

/** Single Ease Question, 7-point (Sauro & Dumas 2009), proposal 4.5 step 4. */
function renderRating(onSubmit, practice = false) {
  let value = null;
  const submit = btn("Submit", () => { if (value !== null) onSubmit(value); }, "primary block");
  submit.disabled = true;
  const scale = el("div", { class: "seq-scale", role: "radiogroup" }, [1, 2, 3, 4, 5, 6, 7].map(v => {
    const b = el("button", { class: "seq-btn", type: "button", role: "radio", "aria-checked": "false" }, String(v));
    b.addEventListener("click", () => {
      value = v;
      for (const x of scale.children) x.setAttribute("aria-checked", String(x === b));
      submit.disabled = false;
    });
    return b;
  }));
  show(screen("participant rating", [
    practice ? el("p", { class: "eyebrow" }, "Practice") : null,
    el("h1", {}, "Overall, how difficult or easy was this task?"),
    scale,
    el("div", { class: "seq-ends" }, [el("span", {}, "1 Very difficult"), el("span", {}, "7 Very easy")]),
    submit,
  ]));
}

function renderInterrupted(sess) {
  show(screen("participant interrupted", [
    el("h1", {}, "Task interrupted"),
    el("p", {}, "The app was closed or reloaded during a task. That attempt was set aside (interrupted_trials.csv) and the task will start again from the beginning."),
    el("p", { class: "muted small" }, "Researcher: note the fault, then enter the PIN to continue. If the screen recording shows a device or app fault, add the trial to exclusions.csv."),
    btn("Researcher: continue", () => askPin("Researcher PIN", () => { store.update(() => { sess.progress.phase = "task"; }); render(); }), "primary block"),
  ]));
}

function finishSession(sess, early = false) {
  store.update(s => {
    sess.finishedAt = new Date().toISOString();
    if (early) sess.endedEarly = true;
    if (s.activeSession === sess.participant_id) s.activeSession = null;
  });
  releaseWake();
  show(screen("participant end", [
    el("div", { class: "done-mark", "aria-hidden": "true" }, "✓"),
    el("h1", {}, early ? "Session ended" : "All tasks done"),
    el("p", {}, "Thank you! Please hand the phone back to the researcher."),
    btn("Researcher", () => askPin("Researcher PIN", renderResearcher), "primary block"),
  ]));
}

// ---- running a timed trial ------------------------------------------------------------------------
function runTrial({ meta, tree: t, pattern, record, scenario, extra = {} }, onEnd) {
  const site = el("div", { class: "run-site" });
  const giveUp = btn("Give up", () => confirmGiveUp(), "giveup");
  const view = btn("View task", () => modal([
    el("h2", {}, "Your task"), el("p", { class: "scenario" }, scenario),
    btn("Back to the website", closeModals, "primary block"),
  ]), "ghost");
  const bar = el("div", { class: "run-bar" }, [view, giveUp]);
  show(el("div", { class: "run" }, [site, bar]));

  let page = null;
  const trial = new Trial(meta, t, {
    timeLimitMs: study.timeLimitMs,
    record,
    onLeafPage(nodeId) {
      page = el("div", { class: "leaf-page" }, [
        el("div", { class: "leaf-top" }, btn("‹ Back", () => { page.remove(); page = null; trial.backFromPage(); }, "back")),
        el("h1", {}, t.label(nodeId)),
        el("p", { class: "leaf-msg" }, "This is not the page you were asked to find."),
        el("div", { class: "ph ph-line w80" }), el("div", { class: "ph ph-line w60" }), el("div", { class: "ph ph-line w70" }),
      ]);
      site.append(page);
    },
    onEnd(reason) { currentTrial = null; onEnd(reason); },
  });
  currentTrial = trial;
  mounted = pattern.mount(site, { tree: t, api: { select: id => trial.select(id), nav: (ty, n) => trial.nav(ty, n), current: () => trial.current }, ...extra });
  trial.start();

  function confirmGiveUp() {
    modal([
      el("h2", {}, "Give up on this task?"),
      el("div", { class: "row" }, [btn("Keep looking", closeModals), btn("Give up", () => { closeModals(); trial.giveUp(); }, "danger")]),
    ]);
  }
}

// ---------------------------------------------------------------------------------------------
// modals, PIN, misc
// ---------------------------------------------------------------------------------------------
function modal(children, cls = "") {
  const box = el("div", { class: `modal ${cls}`, role: "dialog", "aria-modal": "true" }, children);
  const overlay = el("div", { class: "overlay" }, box);
  frame.append(overlay);
  return { close: () => overlay.remove(), box };
}
function closeModals() { for (const o of frame.querySelectorAll(".overlay")) o.remove(); }

function toast(text) {
  const t = el("div", { class: "toast" }, text);
  frame.append(t);
  setTimeout(() => t.remove(), 3500);
}

function askPin(title, onOk) {
  const input = el("input", { class: "input pin", type: "password", inputmode: "numeric", autocomplete: "off" });
  const msg = el("p", { class: "field-msg err" });
  const check = () => {
    if (input.value === pin()) { m.close(); onOk(); }
    else { msg.textContent = "Wrong PIN."; input.value = ""; input.focus(); }
  };
  input.addEventListener("keydown", e => { if (e.key === "Enter") check(); });
  const forgot = el("button", { class: "linkish", type: "button" }, "Forgot PIN?");
  forgot.addEventListener("click", () => {
    m.close();
    confirmText("Reset the PIN?", "The PIN returns to the default in data/study.json. No data is deleted. Type RESET to confirm.", "RESET", () => {
      store.update(s => { s.pin = null; });
      toast("PIN reset to the study.json default.");
    });
  });
  const m = modal([el("h2", {}, title), input, msg, el("div", { class: "row" }, [btn("Cancel", () => m.close()), btn("OK", check, "primary")]), forgot]);
  setTimeout(() => input.focus(), 50);
}

function changePin() {
  const cur = el("input", { class: "input pin", type: "password", inputmode: "numeric", placeholder: "Current PIN" });
  const a = el("input", { class: "input pin", type: "password", inputmode: "numeric", placeholder: "New PIN (4+ digits)" });
  const b = el("input", { class: "input pin", type: "password", inputmode: "numeric", placeholder: "Repeat new PIN" });
  const msg = el("p", { class: "field-msg err" });
  const m = modal([el("h2", {}, "Change PIN"), cur, a, b, msg, el("div", { class: "row" }, [
    btn("Cancel", () => m.close()),
    btn("Save", () => {
      if (cur.value !== pin()) { msg.textContent = "Current PIN is wrong."; return; }
      if (!/^\d{4,}$/.test(a.value)) { msg.textContent = "Use at least 4 digits."; return; }
      if (a.value !== b.value) { msg.textContent = "New PINs do not match."; return; }
      store.update(s => { s.pin = a.value; });
      m.close(); toast("PIN changed on this device.");
    }, "primary"),
  ])]);
}

function confirmText(title, text, word, onOk) {
  const input = el("input", { class: "input", autocomplete: "off", autocapitalize: "characters", spellcheck: "false" });
  const go = btn("Confirm", () => { if (input.value.trim() === word) { m.close(); onOk(); } }, "danger");
  go.disabled = true;
  input.addEventListener("input", () => { go.disabled = input.value.trim() !== word; });
  const m = modal([el("h2", {}, title), el("p", {}, text), input, el("div", { class: "row" }, [btn("Cancel", () => m.close()), go])]);
}

/** Hidden researcher access: 3 s long-press on the top-right corner (PIN-protected). */
function setupCorner() {
  const corner = document.getElementById("corner");
  let timer = null;
  const cancel = () => { clearTimeout(timer); timer = null; };
  corner.addEventListener("pointerdown", () => { cancel(); timer = setTimeout(() => { timer = null; openCornerMenu(); }, 3000); });
  for (const ev of ["pointerup", "pointerleave", "pointercancel"]) corner.addEventListener(ev, cancel);
  corner.addEventListener("contextmenu", e => e.preventDefault());
}

function openCornerMenu() {
  if (frame.querySelector(".overlay")) return;
  askPin("Researcher PIN", () => {
    const sess = activeSession();
    if (currentTrial && sess && currentTrial.opts.record) {
      modal([
        el("h2", {}, "Task in progress"),
        el("p", { class: "small" }, "The task timer is still running."),
        btn("Resume task", closeModals, "block"),
        btn("Abort and re-run this task (app/device fault)", () => {
          currentTrial.abort("researcher abort (fault)"); currentTrial = null;
          store.update(() => { sess.progress.phase = "task"; });
          toast("Trial set aside in interrupted_trials.csv. Add it to exclusions.csv if needed.");
          render();
        }, "danger block"),
      ]);
    } else if (currentTrial) {
      modal([el("h2", {}, "Practice in progress"), btn("Resume", closeModals, "block"),
        btn("Restart practice", () => { currentTrial.abort(); currentTrial = null; practiceState = null; render(); }, "block")]);
    } else {
      renderResearcher();
    }
  });
}

/** The device back button/gesture must not navigate (proposal 4.3): swallow it. */
function trapSystemBack() {
  history.pushState({ trap: true }, "");
  window.addEventListener("popstate", () => history.pushState({ trap: true }, ""));
}

async function keepAwake() {
  try { if ("wakeLock" in navigator && !wakeLock) { wakeLock = await navigator.wakeLock.request("screen"); wakeLock.addEventListener("release", () => { wakeLock = null; }); } }
  catch { /* not supported or not allowed; ignore */ }
}
function releaseWake() { try { wakeLock?.release(); } catch { /* ignore */ } wakeLock = null; }

if ("serviceWorker" in navigator && location.protocol !== "file:") {
  navigator.serviceWorker.register("sw.js").catch(e => console.warn("service worker not registered", e));
}

boot();
