// Practice interface (proposal 4.5 step 2): a separate, NON-nested interface, so participants learn
// the task format (scenario, Start, Give up, wrong page, completion, rating) without seeing any of
// the three experimental patterns or the government content. One flat A-Z list of library pages.
// Same for every participant. Nothing from practice is written to the store or exported.

import { el, siteHeader } from "./common.js";

export default {
  id: "PRACTICE",
  mount(container, { tree, api, siteName }) {
    const list = el("ul", { class: "pr-list" }, tree.children(tree.root)
      .sort((a, b) => a.label.localeCompare(b.label))
      .map(n => el("li", {}, el("button", { class: "pr-link", "data-node": n.id }, n.label))));
    const root = el("div", { class: "site practice" }, [
      siteHeader(() => api.nav("logo", tree.root), siteName),
      el("h2", { class: "pr-title" }, "All pages A–Z"),
      list,
    ]);
    list.addEventListener("click", e => {
      const b = e.target.closest(".pr-link");
      if (b) api.select(b.dataset.node);
    });
    container.append(root);
    return { unmount() { root.remove(); } };
  },
};
