/* Overview dashboard. Owner: Masengesho Donatien (dashboard + audit services and these pages). */
(function () {
  const D = window.DHIS;
  const { h } = D.ui;
  const INK = "#13212c", GRID = "#e3eaee", BLUE = "#0b6fa4", BLUE2 = "#7fb6d3", GREY = "#9aa9b3";
  const STATUS_COLOR = { PENDING: BLUE, ACCEPTED: "#2f8f6b", IN_TRANSIT: BLUE2, COMPLETED: "#17684a", REJECTED: "#b3463f", CANCELLED: GREY, EXPIRED: "#c9d3d9" };
  const MEASURE = { patients: ["Patients registered", BLUE], encounters: ["Visits", "#6b8ea3"], transfers_out: ["Transfers requested", "#c07a12"] };
  let charts = [];

  function chart(canvas, config) {
    Chart.defaults.font.family = '"Source Sans 3", sans-serif';
    Chart.defaults.color = "#4f616d";
    const c = new Chart(canvas, config); charts.push(c); return c;
  }
  const canvases = {};
  const box = (title, key) => { canvases[key] = h("canvas", { role: "img", "aria-label": title }); return D.ui.panel(title, h("div", { class: "chart-box" }, canvases[key])); };

  D.pages.dashboard = async function (container, params, user) {
    charts.forEach((c) => c.destroy()); charts = [];
    const state = { hospital: "" };
    const body = h("div");
    const filter = user.role === "HOSPITAL_MANAGER" ? null : h("select", { "aria-label": "Hospital", style: "width:auto", onchange: (e) => { state.hospital = e.target.value; load(); } },
      h("option", { value: "" }, "All hospitals"), h("option", { value: "KRH" }, "KRH"), h("option", { value: "BDH" }, "BDH"));
    container.append(D.ui.pageHeader("Overview", user.role === "HOSPITAL_MANAGER" ? "Figures for " + user.hospital : "Figures across hospitals", filter), body);

    async function load() {
      charts.forEach((c) => c.destroy()); charts = [];
      D.ui.clear(body).appendChild(D.ui.spinner());
      const q = state.hospital ? "?hospital=" + state.hospital : "";
      const [s, ts, cond, rec] = await Promise.all([D.api.get("dashboard/summary/" + q), D.api.get("dashboard/timeseries/" + q), D.api.get("dashboard/conditions/" + q), D.api.get("dashboard/transfers/" + q)]);
      D.ui.clear(body);
      if (!s.ok) { body.appendChild(D.ui.errorBox(s, load)); return; }
      const d = s.data;
      body.append(
        h("div", { class: "stats" },
          stat(d.patients_registered, "Patients registered"), stat(d.encounters, "Visits recorded"), stat(d.transfers_total, "Transfers"),
          stat(d.avg_decision_minutes === null ? "–" : (d.avg_decision_minutes < 1 ? "Under 1" : d.avg_decision_minutes), "Average minutes to a decision")),
        h("div", { class: "charts" }, box("Transfers by status", "status"), box("Top diagnoses (ICD-10 group)", "cond"), h("div", { class: "wide" }, box("Activity by day", "time"))),
        D.ui.panel("Latest transfers", rec.ok && rec.data.length ? D.ui.table([
          { label: "Route", render: (t) => t.from_hospital + " to " + t.to_hospital }, { label: "Priority", render: (t) => D.ui.priorityLabel(t.priority) },
          { label: "Status", render: (t) => D.ui.badge(t.status) }, { label: "Requested", render: (t) => D.ui.fmtDateTime(t.requested_at) },
        ], rec.data.slice(0, 8)) : D.ui.empty("No transfers yet", "Transfers appear here a few seconds after they are requested.")),
        h("p", { class: "muted small", style: "margin-top:1rem" }, "Figures are built from events, so they can be a few seconds behind the latest action."));

      const draw = () => {
      const entries = Object.entries(d.transfers_by_status);
      chart(canvases["status"], { type: "bar", data: { labels: entries.map(([k]) => D.ui.statusLabel(k)), datasets: [{ data: entries.map(([, v]) => v), backgroundColor: entries.map(([k]) => STATUS_COLOR[k]), borderRadius: 3 }] },
        options: { indexAxis: "y", maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: GRID } }, y: { grid: { display: false } } } } });
      const top = cond.ok ? cond.data : [];
      chart(canvases["cond"], { type: "bar", data: { labels: top.map((c) => c.code), datasets: [{ data: top.map((c) => c.count), backgroundColor: BLUE, borderRadius: 3 }] },
        options: { indexAxis: "y", maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: GRID } }, y: { grid: { display: false } } } } });
      const series = ts.ok ? ts.data : {};
      const dates = [...new Set(Object.values(series).flat().map((p) => p.date))].sort();
      chart(canvases["time"], { type: "line", data: { labels: dates.map((x) => D.ui.fmtDate(x)), datasets: Object.entries(MEASURE).filter(([k]) => series[k]).map(([k, [label, color]]) => ({
        label, borderColor: color, backgroundColor: color, borderWidth: 2, tension: 0.25, pointRadius: 3,
        data: dates.map((dt) => (series[k].find((p) => p.date === dt) || { value: 0 }).value) })) },
        options: { maintainAspectRatio: false, plugins: { legend: { position: "bottom" } }, scales: { y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: GRID } }, x: { grid: { display: false } } } } });
      };
      // Charts need the page to be on screen to measure their size.
      if (body.isConnected) draw(); else container.addEventListener("mounted", draw, { once: true });
    }
    const stat = (n, l) => h("div", { class: "stat" }, h("div", { class: "n" }, n), h("div", { class: "l" }, l));
    await load();
  };
})();
