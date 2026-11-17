// Small helpers shared by all pattern modules. Keep patterns visually identical apart from the
// menu itself: same header, same logo, same placeholder home content.

export function el(tag, attrs = {}, children = []) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === false || v === null || v === undefined) continue;
    n.setAttribute(k, v === true ? "" : v);
  }
  for (const c of [].concat(children)) {
    if (c === null || c === undefined || c === false) continue;
    n.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return n;
}

/** Site header with the logo. Tapping the logo returns to the start state (proposal 4.3). */
export function siteHeader(onLogo, title = "Department of Foreign Affairs") {
  const logo = el("button", { class: "site-logo", "aria-label": "Home" }, [
    el("span", { class: "site-logo-mark", "aria-hidden": "true" }),
    el("span", { class: "site-logo-text" }, title),
  ]);
  logo.addEventListener("click", onLogo);
  return el("header", { class: "site-header" }, logo);
}

/** Low-fidelity placeholder home content: grey blocks, no links. */
export function homeBody() {
  return el("main", { class: "site-home", "aria-hidden": "true" }, [
    el("div", { class: "ph ph-hero" }),
    el("div", { class: "ph ph-line w80" }),
    el("div", { class: "ph ph-line w60" }),
    el("div", { class: "ph-row" }, [el("div", { class: "ph ph-card" }), el("div", { class: "ph ph-card" })]),
    el("div", { class: "ph ph-line w70" }),
    el("div", { class: "ph ph-line w50" }),
  ]);
}
