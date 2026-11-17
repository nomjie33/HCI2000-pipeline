# Adding a navigation pattern (DH / ND)

The experiment shell is shared: researcher setup, Latin square, practice, timer, logging, SEQ rating
and export are already built. Adding a pattern means writing **one file** and changing **one line**.
Do not log events, start timers or show pages yourself. The shell does all of that, so every pattern
logs identically and the analysis pipeline can compare them.

## Status

| Code | Pattern | File | Status |
| :-- | :-- | :-- | :-- |
| MM | Mega-menu | `js/patterns/megamenu.js` | done (reference implementation) |
| DH | Deep hierarchical | `js/patterns/deephierarchical.js` | done |
| ND | Nested dropdown | `js/patterns/nesteddropdown.js` | done |

Both patterns are built; use `megamenu.js`, `deephierarchical.js` and `nesteddropdown.js` as references for any new one.

## The contract

```js
// js/patterns/deephierarchical.js
import { el, siteHeader, homeBody } from "./common.js";

export default {
  id: "DH",
  mount(container, { tree, api }) {
    // build your DOM inside `container`
    return { unmount() { /* remove what you added */ } };
  },
};
```

| You get | What it is |
| :-- | :-- |
| `tree.root` | `"ROOT"` |
| `tree.children(id)` | child nodes `{ id, label, level, children: [ids] }`, in tree.csv order |
| `tree.label(id)`, `tree.get(id)`, `tree.isLeaf(id)` | helpers |
| `api.select(nodeId)` | call when the participant **taps a menu item** (a selection, proposal 3.2) |
| `api.nav(type, currentNodeAfter)` | call for a **navigation action**: `"back"`, `"collapse"`, `"menu_open"`, `"menu_close"`, `"logo"` |
| `api.current()` | the node the shell thinks is current (for debugging) |

What the shell does for you:
- `api.select(leaf)` opens the leaf page. The target ends the trial; any other leaf shows the
  "This is not the page you were asked to find" page with a Back button. That Back returns to whatever your pattern was
  showing, because your DOM stays mounted underneath. **Keep your menu state as it was.**
- `on_path`, `t_ms`, the Give up button, the 180 s timeout and the completion screen are all handled.
- The top-right 48×48 px corner is reserved for the hidden researcher long-press.

### `currentNodeAfter` = the node whose children (or page) are on screen after the action

| Pattern | Gesture | Call |
| :-- | :-- | :-- |
| DH | tap an item (L1/L2) → list replaced by its children | `api.select(item)` |
| DH | tap an L3 item | `api.select(leaf)` |
| DH | Back control at the top | `api.nav("back", parentOfCurrentLevel)` |
| ND | tap a closed L1/L2 → its children open beneath it | `api.select(item)` |
| ND | tap an open item → it collapses | `api.nav("collapse", parentOfCollapsedItem)` |
| ND | tap an L3 item | `api.select(leaf)` |
| ND | open/close a hamburger, if you use one | `api.nav("menu_open" / "menu_close", "ROOT")` |
| all | tap the logo (use `siteHeader(onLogo)`) | `api.nav("logo", "ROOT")` and reset the menu |

Rules from proposal 4.3 / Table 2: tap only (no hover), no search box, no breadcrumbs, no cross-links. Use the same
`siteHeader` and `homeBody` as MM so only the menu differs between conditions.

## Checklist for each pattern

- [ ] Create `js/patterns/<name>.js` following the contract (copy the structure of `megamenu.js`).
- [ ] In `js/patterns/index.js`, import it, set `module` to it and set `status: "ready"`. Remove the `TODO(..)` comment.
- [ ] Add the file to `FILES` in `sw.js` (`pytest tests/test_prototype_config.py` fails if you forget).
- [ ] Add its CSS to `css/app.css` under a `/* ---- deep hierarchical ---- */` section.
- [ ] Bump `CACHE_VERSION` in `sw.js` and `appVersion` in `data/study.json`.
- [ ] Test on the desktop (`python -m http.server 8000 -d prototype`), run a session whose sequence uses your pattern,
      make one wrong selection and recover from it, export, then
      `python scripts/run_pipeline.py --data-dir <unzipped export> --out outputs/test`.
      Expect **no hard validation failures** and `on_path_matches_tree` = PASS.
- [ ] Update the status table above and in the root `README.md`.
