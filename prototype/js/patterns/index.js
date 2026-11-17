// Pattern registry. The shell looks patterns up here by the codes used in study.json / the pipeline.
//
// status "ready": used in sessions.
// status "todo" : not built yet. Researcher setup flags it, and the block is skipped (logged in session_info.csv).
//
// To add a pattern: create its file next to megamenu.js (contract in prototype/PATTERN_API.md),
// import it below, replace the stub and set status to "ready". Then bump appVersion in data/study.json
// and CACHE_VERSION in sw.js so installed phones pick up the new build.

import deephierarchical from "./deephierarchical.js";
import megamenu from "./megamenu.js";
import nesteddropdown from "./nesteddropdown.js";
import { makeStub } from "./stub.js"; // unused now; kept so a future pattern can be registered as "todo"

export const PATTERNS = {
  DH: { status: "ready", module: deephierarchical },

  MM: { status: "ready", module: megamenu },

  ND: { status: "ready", module: nesteddropdown },
};

export const patternStatus = () => Object.fromEntries(Object.entries(PATTERNS).map(([k, v]) => [k, v.status]));
export const isReady = code => PATTERNS[code]?.status === "ready";
