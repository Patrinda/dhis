/* Shell: sidebar, router, status strip. Owner: Patrick (shared core).
   Pages register themselves as DHIS.pages.<name> = async (container, params) => {} */
(function () {
  const D = window.DHIS;
  const { h, icon, clear } = D.ui;
  const ALL_CLINICAL = ["DOCTOR", "NURSE", "REGISTRATION"];

  const NAV = [
    { hash: "#/dashboard", label: "Overview", icon: "bar-chart-line", roles: ["HOSPITAL_MANAGER", "SYSTEM_ADMIN", "DPO"] },
    { hash: "#/patients", label: "Patients", icon: "people", roles: ["REGISTRATION", "NURSE", "DOCTOR", "SYSTEM_ADMIN"] },
    { hash: "#/transfers", label: "Transfers", icon: "arrow-left-right", roles: ["DOCTOR", "NURSE", "HOSPITAL_MANAGER", "SYSTEM_ADMIN", "REGISTRATION", "DPO"] },
    { hash: "#/pharmacy", label: "Pharmacy", icon: "capsule", roles: ["PHARMACIST", "DOCTOR"] },
    { hash: "#/lab", label: "Laboratory", icon: "eyedropper", roles: ["LAB_TECH", "DOCTOR"] },
    { hash: "#/emergency", label: "Emergency access", icon: "shield-exclamation", roles: ["DOCTOR"] },
    { hash: "#/audit", label: "Audit log", icon: "journal-check", roles: ["DPO", "SYSTEM_ADMIN"] },
    { hash: "#/consents", label: "Consent register", icon: "file-earmark-check", roles: ["DPO", "SYSTEM_ADMIN"] },
    { hash: "#/admin", label: "Users and hospitals", icon: "gear", roles: ["SYSTEM_ADMIN"] },
    { hash: "#/status", label: "System status", icon: "activity", roles: ["SYSTEM_ADMIN", "HOSPITAL_MANAGER"] },
  ];
  const ROUTES = [
    [/^#\/login$/, "login", true],
    [/^#\/patients$/, "patientList"], [/^#\/patients\/([\w-]+)$/, "patientDetail"],
    [/^#\/transfers$/, "transferList"], [/^#\/transfers\/([\w-]+)$/, "transferDetail"],
    [/^#\/pharmacy$/, "pharmacy"], [/^#\/lab$/, "lab"], [/^#\/emergency$/, "emergency"],
    [/^#\/dashboard$/, "dashboard"], [/^#\/audit$/, "audit"], [/^#\/consents$/, "consents"],
    [/^#\/admin$/, "admin"], [/^#\/status$/, "status"],
  ];
  const HOME = { PHARMACIST: "#/pharmacy", LAB_TECH: "#/lab", HOSPITAL_MANAGER: "#/dashboard", DPO: "#/audit", SYSTEM_ADMIN: "#/dashboard" };

  const app = document.getElementById("app");
  let shell = null, mainEl = null, timers = [], renderToken = 0;

  function stopTimers() { timers.forEach(clearInterval); timers = []; }

  function buildShell(user) {
    stopTimers();
    const nav = h("nav", { class: "nav", "aria-label": "Main" },
      NAV.filter((n) => n.roles.includes(user.role)).map((n) => h("a", { href: n.hash, "data-hash": n.hash }, icon(n.icon), n.label)));
    const fullName = user.first_name ? user.first_name + " " + user.last_name : user.username;
    const hospital = user.hospital_name || (user.hospital_code ? user.hospital_code : "All hospitals");
    const dot = h("a", { class: "status-dot", href: "#/status" }, "Checking services");
    const rail = h("aside", { class: "rail", id: "rail" },
      h("div", { class: "rail-head" },
        h("div", { class: "brand" }, h("span", { class: "brand-mark" }, icon("plus-lg")), "DHIS"),
        h("div", { class: "hospital-name" }, hospital),
        h("div", { class: "hospital-meta" }, user.hospital_code ? "Node " + user.hospital_code : "National level")),
      nav,
      h("div", { class: "rail-foot" },
        dot,
        h("div", { class: "who-row" }, D.ui.avatar(fullName), h("div", null, h("div", { class: "who" }, fullName), h("div", { class: "who-role" }, D.ui.ROLE_LABEL[user.role] || user.role))),
        h("div", { style: "margin-top:.6rem" }, h("button", { class: "link-btn", onclick: signOut }, "Sign out"))));
    mainEl = h("main", { class: "main", id: "main", tabindex: "-1" });
    const toggle = h("button", { class: "btn menu-toggle", "aria-label": "Open menu", onclick: () => rail.classList.toggle("open") }, icon("list"), "Menu");
    const canSearch = ["REGISTRATION", "NURSE", "DOCTOR", "SYSTEM_ADMIN"].includes(user.role);
    const q = h("input", { type: "search", placeholder: "Search patients by name or ID", "aria-label": "Search patients" });
    q.addEventListener("keydown", (e) => { if (e.key === "Enter" && q.value.trim()) { location.hash = "#/patients?q=" + encodeURIComponent(q.value.trim()); q.value = ""; } });
    const today = new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" }).format(new Date());
    const topbar = h("header", { class: "topbar" }, toggle, canSearch ? h("div", { class: "search" }, icon("search"), q) : null, h("div", { class: "today" }, today));
    shell = h("div", { class: "shell" }, rail, h("div", { class: "content" }, topbar, mainEl));
    clear(app).appendChild(shell);
    rail.addEventListener("click", (e) => { if (e.target.closest("a")) rail.classList.remove("open"); });

    async function pollHealth() {
      try {
        const r = await fetch("/api/health/"); const j = await r.json();
        const down = Object.entries(j.services).filter(([, v]) => !v.up).map(([k]) => k);
        dot.className = "status-dot " + (down.length ? "down" : "up");
        dot.textContent = down.length ? down.length + (down.length === 1 ? " service is down" : " services are down") : "All services running";
        dot.title = down.length ? "Not responding: " + down.join(", ") : "";
      } catch (e) { dot.className = "status-dot down"; dot.textContent = "Server not reachable"; }
    }
    pollHealth(); timers.push(setInterval(pollHealth, 15000));
    if (["DOCTOR", "HOSPITAL_MANAGER", "SYSTEM_ADMIN"].includes(user.role)) {
      pollQueue(); timers.push(setInterval(pollQueue, 8000));
    }
  }

  async function pollQueue() {
    const r = await D.api.get("queue/");
    let el = document.getElementById("queue-banner");
    if (!r.ok || !r.data.pending) { if (el) el.remove(); return; }
    if (!el && mainEl) { el = h("div", { class: "banner warn", id: "queue-banner", role: "status" }); mainEl.prepend(el); }
    if (el) { clear(el).append(icon("hourglass-split"), h("div", null, r.data.pending + (r.data.pending === 1 ? " transfer request is" : " transfer requests are") + " not yet sent because the transfer service cannot be reached. They are sent automatically when it returns."),
      h("a", { class: "btn small", href: "#/status" }, "View")); }
  }

  function signOut() { D.session.clear(); stopTimers(); shell = null; location.hash = "#/login"; }

  function markNav(hash) {
    document.querySelectorAll(".nav a").forEach((a) => {
      const active = hash === a.dataset.hash || hash.startsWith(a.dataset.hash + "/");
      if (active) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
  }

  async function render() {
    const hash = (location.hash || "#/").split("?")[0];
    const session = D.session.get();
    const token = ++renderToken;
    const route = ROUTES.map(([re, page, pub]) => ({ m: hash.match(re), page, pub })).find((r) => r.m);

    if (!session) {
      if (!route || !route.pub) { location.hash = "#/login"; return; }
      shell = null; stopTimers();
      clear(app); document.title = "Sign in – DHIS";
      await D.pages.login(app);
      return;
    }
    if (!route || route.pub) { location.hash = HOME[session.user.role] || "#/patients"; return; }
    if (!shell) buildShell(session.user);
    const allowed = NAV.some((n) => n.roles.includes(session.user.role) && (hash === n.hash || hash.startsWith(n.hash + "/")))
      || /^#\/(patients|transfers)\//.test(hash);
    markNav(hash);
    const old = document.getElementById("queue-banner");
    clear(mainEl); if (old) mainEl.appendChild(old);
    if (!allowed) {
      mainEl.appendChild(D.ui.empty("This page is not available for your role", "Choose another page from the menu.", h("a", { class: "btn", href: HOME[session.user.role] || "#/patients" }, "Go to your home page")));
      return;
    }
    const container = h("div", null, D.ui.spinner());
    mainEl.appendChild(container);
    try {
      const page = D.pages[route.page];
      if (!page) throw new Error("Page not installed: " + route.page);
      const body = h("div");
      await page(body, route.m.slice(1), session.user);
      if (token !== renderToken) return; // the user already moved on
      container.replaceWith(body);
      body.dispatchEvent(new Event("mounted"));
      document.title = (body.querySelector("h1") ? body.querySelector("h1").textContent : "DHIS") + " – DHIS";
      mainEl.focus({ preventScroll: true });
    } catch (e) {
      console.error(e);
      container.replaceWith(D.ui.errorBox({ error: { message: "This page could not be shown. " + (e.message || "") } }, () => render()));
    }
  }

  window.addEventListener("hashchange", render);
  window.addEventListener("DOMContentLoaded", render);
  D.render = render;
})();
