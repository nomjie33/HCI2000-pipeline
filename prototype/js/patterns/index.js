// Pattern registry. The shell looks patterns up here by the codes used in study.json / the pipeline.
//
// status "ready": used in sessions.
// status "todo" : not built yet. Researcher setup flags it, and the block is skipped (logged in session_info.csv).
//
// To add a pattern: create its file next to megamenu.js (contract in prototype/PATTERN_API.md),
// import it below, replace the stub and set status to "ready". Then bump appVersion in data/study.json
// and CACHE_VERSION in sw.js so installed phones pick up the new build.

import megamenu from "./megamenu.js";
import { makeStub } from "./stub.js";

export const PATTERNS = {
  // TODO(DH): create js/patterns/deephierarchical.js. Table 2: single-panel drill-down, one level
  //   visible at a time; tapping an item -> api.select(node); Back control at top -> api.nav("back", parent).
  //   Then: import it above, set module to it and status to "ready".
  DH: { status: "todo", module: makeStub("DH") },

  MM: { status: "ready", module: megamenu },

  // TODO(ND): create js/patterns/nesteddropdown.js. Table 2: L1 opens its L2 list beneath it, L2 opens
  //   its L3 list beneath it (indented); tapping a closed item -> api.select(node); tapping an open
  //   item collapses it -> api.nav("collapse", parentOfCollapsed). Then: set module and status "ready".
  ND: { status: "todo", module: makeStub("ND") },
};

export const patternStatus = () => Object.fromEntries(Object.entries(PATTERNS).map(([k, v]) => [k, v.status]));
export const isReady = code => PATTERNS[code]?.status === "ready";
