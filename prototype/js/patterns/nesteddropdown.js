// Nested dropdown (ND), proposal Table 2:
//   Tapping an L1 item opens its L2 list directly beneath it; tapping an L2 item opens its L3 list
//   beneath it (indented). Tapping an open item collapses it. One branch open per level (opening a
//   sibling closes the previous one). Visible: L1 list plus the open branch. Minimum selections: 3.
//
// Logged actions (all through the shell API, never directly):
//   tap a closed L1/L2       -> api.select(item)                    its children open, current = item
//   tap an open L1/L2        -> api.nav("collapse", parentOfItem)   it (and anything below) closes
//   tap L3 item              -> api.select(leaf)                    shell opens the page
//   tap logo                 -> api.nav("logo", ROOT)               everything collapses

import { el, siteHeader } from "./common.js";

export default {
  id: "ND",
  mount(container, { tree, api }) {
    const open = []; // open[i] = id of the open node at depth i+1 (L1, L2); path of the open branch

    const menu = el("nav", { class: "nd-menu", "aria-label": "Main menu" });
    const root = el("div", { class: "site nd" }, [
      siteHeader(() => { open.length = 0; render(); menu.scrollTop = 0; api.nav("logo", tree.root); }),
      menu,
    ]);
    container.append(root);

    const parentOf = id => tree.get(id)?.parent ?? tree.root;

    function list(parentId, depth) {
      return el("ul", { class: `nd-list nd-d${depth}`, role: "list" }, tree.children(parentId).map(n => {
        const hasKids = n.children.length > 0;
        const isOpen = open[depth] === n.id;
        return el("li", { class: "nd-li" }, [
          el("button", {
            class: `nd-item nd-l${depth + 1}` + (hasKids ? " has-kids" : ""),
            "data-node": n.id,
            "data-depth": String(depth),
            "aria-expanded": hasKids ? String(isOpen) : null,
          }, [el("span", {}, n.label), hasKids ? el("span", { class: "nd-caret", "aria-hidden": "true" }, isOpen ? "▴" : "▾") : null]),
          hasKids && isOpen ? list(n.id, depth + 1) : null,
        ]);
      }));
    }

    function render() { menu.replaceChildren(list(tree.root, 0)); }

    menu.addEventListener("click", e => {
      const b = e.target.closest(".nd-item");
      if (!b) return;
      const id = b.dataset.node;
      const depth = Number(b.dataset.depth);
      if (tree.isLeaf(id)) { api.select(id); return; } // keep the open branch as it is underneath
      if (open[depth] === id) {
        open.length = depth; // collapse it and everything below
        render();
        api.nav("collapse", parentOf(id));
        return;
      }
      open.length = depth; // a sibling branch (if any) closes
      open[depth] = id;
      render();
      menu.querySelector(`[data-node="${CSS.escape(id)}"]`)?.scrollIntoView({ block: "nearest" });
      api.select(id);
    });

    render();
    return { unmount() { root.remove(); } };
  },
};
