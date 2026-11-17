// Deep hierarchical (DH), proposal Table 2:
//   Single-panel drill-down. One level of the menu is visible at a time; tapping an item replaces
//   the list with that item's children. A Back control at the top returns to the parent level.
//   Visible: the current level only. Minimum selections: 3 (L1, L2, L3).
//
// Logged actions (all through the shell API, never directly):
//   tap L1/L2 item   -> api.select(item)            list replaced by its children, current = item
//   tap L3 item      -> api.select(leaf)            shell opens the page
//   tap Back         -> api.nav("back", parent)     list shows the parent level, current = parent
//   tap logo         -> api.nav("logo", ROOT)       list resets to the L1 level

import { el, siteHeader } from "./common.js";

export default {
  id: "DH",
  mount(container, { tree, api }) {
    let level = tree.root; // node whose children are on screen

    const head = el("div", { class: "dh-head" });
    const list = el("ul", { class: "dh-list", role: "list" });
    const panel = el("nav", { class: "dh-panel", "aria-label": "Main menu" }, [head, list]);

    const root = el("div", { class: "site dh" }, [
      siteHeader(() => { show(tree.root); api.nav("logo", tree.root); }),
      panel,
    ]);
    container.append(root);

    const parentOf = id => tree.get(id)?.parent ?? tree.root;

    function show(id) {
      level = id;
      if (id === tree.root) {
        head.replaceChildren(el("span", { class: "dh-title" }, "Menu"));
      } else {
        head.replaceChildren(
          el("button", { class: "dh-back", "data-back": "1" }, [el("span", { "aria-hidden": "true" }, "‹ "), "Back"]),
          el("span", { class: "dh-title" }, tree.label(id)),
        );
      }
      list.replaceChildren(...tree.children(id).map(n =>
        el("li", {}, el("button", {
          class: "dh-item" + (n.children.length ? " has-kids" : ""),
          "data-node": n.id,
        }, [el("span", {}, n.label), n.children.length ? el("span", { class: "dh-chev", "aria-hidden": "true" }, "›") : null]))));
      panel.scrollTop = 0;
    }

    panel.addEventListener("click", e => {
      if (e.target.closest("[data-back]")) {
        const parent = parentOf(level);
        show(parent);
        api.nav("back", parent);
        return;
      }
      const item = e.target.closest(".dh-item");
      if (!item) return;
      const id = item.dataset.node;
      if (!tree.isLeaf(id)) show(id);
      api.select(id); // leaf: shell opens the page; our DOM stays as it was underneath
    });

    show(tree.root);
    return { unmount() { root.remove(); } };
  },
};
