// Persistent store for everything the researcher will export. Kept in localStorage and written
// after every logged event, so a crash or reload loses at most the trial in progress.
// Nothing here is ever sent over the network.

const KEY = "hci2000.store.v1";

function blank() {
  return {
    sessions: {},        // participant_id -> session (plan, progress, skipped blocks)
    sessionOrder: [],    // participant ids in creation order
    events: [],          // committed event rows of finished trials (pipeline events.csv)
    ratings: [],         // SEQ rows (pipeline ratings.csv)
    interrupted: [],     // rows of trials cut short by a reload/abort (audit only)
    activeTrial: null,   // { trial_id, participant_id, rows: [...] } while a timed trial runs
    activeSession: null, // participant id currently running
    pin: null,           // device-specific PIN override (null -> study.json default)
  };
}

let state = load();
let memoryOnly = false;

function load() {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) return Object.assign(blank(), JSON.parse(raw));
  } catch (e) { console.warn("store load failed", e); }
  return blank();
}

export function save() {
  try { localStorage.setItem(KEY, JSON.stringify(state)); memoryOnly = false; }
  catch (e) { memoryOnly = true; console.error("store save failed", e); }
}

export function isMemoryOnly() { return memoryOnly; }
export function get() { return state; }

export function update(fn) { fn(state); save(); }

export function clearAll() {
  const pin = state.pin;
  state = blank();
  state.pin = pin;
  save();
}

/** Ask the browser not to evict our storage (best effort; Android Chrome honours it for installed apps). */
export async function requestPersistence() {
  try {
    if (navigator.storage?.persist && !(await navigator.storage.persisted())) await navigator.storage.persist();
    return await navigator.storage?.persisted?.();
  } catch { return false; }
}
