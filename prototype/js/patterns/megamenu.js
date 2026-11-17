// Mega-menu (MM), proposal Table 2:
//   Tapping an L1 item opens a full-width panel that shows all L2 group headings with their L3
//   links at once, in one scrollable panel. L2 headings are labels, L3 links are selectable.
//   Visible: the L1 bar and the open panel. Minimum selections: 2 (L1, L3).
//
// Logged actions (all through the shell API, never directly):
//   tap L1 (closed or different)  -> api.select(L1)              current node = L1
//   tap the open L1 again / ×      -> api.nav("menu_close", ROOT)
//   tap logo                       -> api.nav("logo", ROOT)       panel closes
//   tap L3 link                    -> api.select(L3)              shell opens the page
//   L2 headings                    -> not interactive, not logged

import { el, siteHeader, homeBody } from "./common.js";

export default {
  id: "MM",
  mount(container, { tree, api }) {
    let open = null; // L1 id whose panel is showing

    const l1Items = tree.children(tree.root);
    const bar = el("nav", { class: "mm-bar", "aria-label": "Main menu" },
      l1Items.map(n => el("button", { class: "mm-l1", "data-l1": n.id, "aria-expanded": "false" }, n.label)));
    const panel = el("div", { class: "mm-panel", hidden: "" });
    const body = homeBody();

    const root = el("div", { class: "site mm" }, [
      siteHeader(() => { if (open) close(false); api.nav("logo", tree.root); }),
      bar,
      el("div", { class: "mm-stage" }, [body, panel]),
    ]);
    container.append(root);

    function renderPanel(l1) {
      const groups = tree.children(l1).map(l2 => {
        if (!l2.children.length) {
          // An L2 without children would be a page itself; keep it selectable.
          return el("button", { class: "mm-link", "data-node": l2.id }, l2.label);
        }
        return el("section", { class: "mm-group" }, [
          el("h3", { class: "mm-heading" }, l2.label),
          el("ul", { class: "mm-links" }, tree.children(l2.id).map(l3 =>
            el("li", {}, el("button", { class: "mm-link", "data-node": l3.id }, l3.label)))),
        ]);
      });
      panel.replaceChildren(
        el("div", { class: "mm-panel-head" }, [
          el("span", { class: "mm-panel-title" }, tree.label(l1)),
          el("button", { class: "mm-close", "aria-label": "Close menu", "data-close": "1" }, "×"),
        ]),
        el("div", { class: "mm-groups" }, groups),
      );
      panel.scrollTop = 0;
    }

    function show(l1) {
      open = l1;
      renderPanel(l1);
      panel.hidden = false;
      for (const b of bar.querySelectorAll(".mm-l1")) b.setAttribute("aria-expanded", String(b.dataset.l1 === l1));
    }

    function close(log = true) {
      open = null;
      panel.hidden = true;
      for (const b of bar.querySelectorAll(".mm-l1")) b.setAttribute("aria-expanded", "false");
      if (log) api.nav("menu_close", tree.root);
    }

    bar.addEventListener("click", e => {
      const b = e.target.closest(".mm-l1");
      if (!b) return;
      const id = b.dataset.l1;
      if (open === id) { close(); return; }
      show(id);
      api.select(id);
    });

    panel.addEventListener("click", e => {
      if (e.target.closest("[data-close]")) { close(); return; }
      const link = e.target.closest(".mm-link");
      if (link) api.select(link.dataset.node);
    });

    return { unmount() { root.remove(); } };
  },
};
