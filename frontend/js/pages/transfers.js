/* Transfers: worklist, request, decide, track. Owner: Mudahogora Justine (referral service + this page). */
(function () {
  const D = window.DHIS;
  const { h, icon } = D.ui;
  D.transfers = {};

  // What does this person need to do on this transfer? (null = nothing)
  function nextAction(t, user) {
    const mine = (code) => user.hospital === code;
    if (t.status === "PENDING" && mine(t.to_hospital) && ["DOCTOR", "HOSPITAL_MANAGER"].includes(user.role)) return "Decide";
    if (t.status === "ACCEPTED" && mine(t.from_hospital) && ["DOCTOR", "NURSE"].includes(user.role)) return "Mark as in transit";
    if (t.status === "IN_TRANSIT" && mine(t.to_hospital) && ["DOCTOR", "NURSE"].includes(user.role)) return "Confirm arrival";
    return null;
  }

  D.pages.transferList = async function (container, params, user) {
    const r = await D.api.get("transfers/?page_size=100");
    if (!r.ok) { container.append(D.ui.pageHeader("Transfers"), D.ui.errorBox(r, () => D.render())); return; }
    const all = r.data.results;
    const views = {
      action: all.filter((t) => nextAction(t, user)),
      incoming: all.filter((t) => t.to_hospital === user.hospital),
      outgoing: all.filter((t) => t.from_hospital === user.hospital),
      all,
    };
    let tab = views.action.length ? "action" : (user.hospital ? "incoming" : "all");
    const holder = h("div"), tabsEl = h("div");

    function draw() {
      D.ui.clear(tabsEl).appendChild(D.ui.tabs([
        { id: "action", label: "Needs your action", count: views.action.length, alert: true },
        { id: "incoming", label: "Incoming", count: views.incoming.length }, { id: "outgoing", label: "Outgoing", count: views.outgoing.length },
        { id: "all", label: "All", count: views.all.length }].filter((x) => user.hospital || x.id === "all"), tab, (t) => { tab = t; draw(); }));
      D.ui.clear(holder);
      const rows = views[tab];
      if (!rows.length) {
        holder.appendChild(D.ui.empty(tab === "action" ? "Nothing needs your action" : "No transfers here yet",
          user.role === "DOCTOR" ? "To move a patient, open the patient and choose Request transfer." : "Transfers involving your hospital appear here."));
        return;
      }
      holder.appendChild(D.ui.table([
        { label: "Patient", render: (t) => h("strong", null, t.patient_name) },
        { label: "Route", render: (t) => t.from_hospital + " to " + t.to_hospital },
        { label: "Priority", render: (t) => h("span", { class: "priority-" + t.priority }, D.ui.priorityLabel(t.priority)) },
        { label: "Status", render: (t) => D.ui.badge(t.status) },
        { label: "Requested", render: (t) => D.ui.fmtDateTime(t.created_at) },
        { label: tab === "action" ? "Next step" : "Deadline", render: (t) => (tab === "action" ? h("span", { class: "badge warn" }, nextAction(t, user)) : (t.status === "PENDING" ? D.ui.timeLeft(t.expires_at) : "–")) },
      ], rows, { onRow: (t) => (location.hash = "#/transfers/" + t.id) }));
    }
    container.append(D.ui.pageHeader("Transfers", user.hospital ? "Patients moving to or from " + user.hospital : "All hospitals",
      user.role === "DOCTOR" ? h("button", { class: "btn primary", onclick: () => D.transfers.requestDialog(null) }, icon("plus-lg"), "Request transfer") : null),
      tabsEl, D.ui.panel(null, holder));
    draw();
  };

  // Called from the patient page (patient given) or from the list (patient = null).
  D.transfers.requestDialog = async function (patient) {
    const user = D.session.get().user;
    const hs = await D.api.get("auth/hospitals/");
    const others = hs.ok ? hs.data.filter((x) => x.code !== user.hospital) : [];
    D.ui.formDialog({
      title: "Request a transfer", submitLabel: "Send request", wide: true,
      intro: patient ? "Moving " + patient.full_name + " to another hospital. The patient's consent must be recorded first." : "The patient must be registered at your hospital and must have given consent.",
      fields: [
        { name: "national_id", label: "National ID", required: true, value: patient ? patient.national_id : "", readonly: !!patient, maxlength: 16, inputmode: "numeric" },
        { name: "to_hospital", label: "Receiving hospital", type: "select", required: true, options: [["", "Choose a hospital"]].concat(others.map((x) => [x.code, x.code + " – " + x.name])) },
        { name: "priority", label: "Priority", type: "select", required: true, options: [["ROUTINE", "Routine (decision within 48 hours)"], ["URGENT", "Urgent (decision within 6 hours)"], ["EMERGENCY", "Emergency (decision within 1 hour)"]] },
        { name: "reason", label: "Reason for transfer", type: "textarea", required: true, rows: 4, hint: "At least 10 characters. Say what care the patient needs and why it is not available here." },
      ],
      async onSubmit(v, f) {
        const r = await D.api.post("transfers/", v, { idempotent: true });
        if (r.status === 202) { D.ui.toast("The transfer service is not reachable. Your request is saved and will be sent automatically.", "warn"); D.render(); return true; }
        if (!r.ok) { f.showErrors(r); return false; }
        D.ui.toast("Transfer requested. " + v.to_hospital + " has until " + D.ui.fmtDateTime(r.data.expires_at) + " to decide.", "ok");
        location.hash = "#/transfers/" + r.data.id; return true;
      },
    });
  };

  // ---------- detail page
  const STEPS = [["PENDING", "Requested"], ["ACCEPTED", "Accepted"], ["IN_TRANSIT", "In transit"], ["COMPLETED", "Completed"]];
  const ORDER = { PENDING: 0, ACCEPTED: 1, IN_TRANSIT: 2, COMPLETED: 3 };

  function trail(t) {
    const stoppedStates = ["REJECTED", "CANCELLED", "EXPIRED"];
    const stopped = stoppedStates.includes(t.status);
    const reached = (s) => t.history.find((x) => x.to_status === s);
    // How far did it get before stopping? A cancelled transfer may have been accepted first.
    const furthest = stopped ? (reached("ACCEPTED") ? 1 : 0) : ORDER[t.status];
    const nodes = STEPS.map(([state, label], i) => {
      let cls = i < furthest ? "done" : i === furthest ? (stopped ? "done" : (t.status === "COMPLETED" ? "done" : "current")) : "pending";
      if (t.status === "COMPLETED") cls = "done";
      const ev = i === 0 ? t.history[0] : reached(state);
      return h("div", { class: "trail-step " + cls }, h("div", { class: "trail-dot" }, cls === "done" ? icon("check-lg") : null),
        h("div", { class: "trail-label" }, label), h("div", { class: "trail-when" }, ev ? D.ui.fmtDateTime(ev.at) : (cls === "current" && state === "PENDING" ? D.ui.timeLeft(t.expires_at) : "")));
    });
    if (stopped) {
      const ev = reached(t.status);
      nodes.push(h("div", { class: "trail-step stopped" }, h("div", { class: "trail-dot" }, icon("x-lg")),
        h("div", { class: "trail-label", style: "color:var(--bad)" }, D.ui.statusLabel(t.status)), h("div", { class: "trail-when" }, ev ? D.ui.fmtDateTime(ev.at) : "")));
    }
    return h("div", { class: "trail", role: "img", "aria-label": "Transfer progress: " + D.ui.statusLabel(t.status) }, nodes);
  }

  D.pages.transferDetail = async function (container, params, user) {
    const r = await D.api.get("transfers/" + params[0] + "/");
    if (!r.ok) { container.append(D.ui.pageHeader("Transfer not found", null, h("a", { class: "btn", href: "#/transfers" }, "Back to transfers")), D.ui.errorBox(r)); return; }
    const t = r.data;
    const mine = (code) => user.hospital === code || user.role === "SYSTEM_ADMIN";
    const actions = [h("a", { class: "btn", href: "#/transfers" }, "All transfers")];

    async function act(action, label, needsReason, danger) {
      const run = async (reason, f) => {
        const res = await D.api.post("transfers/" + t.id + "/" + action + "/", { version: t.version, reason: reason || "" });
        if (res.status === 409) { D.ui.toast(res.error.message + " The page will reload.", "warn"); D.render(); return true; }
        if (!res.ok) { if (f) f.showErrors(res); else D.ui.toast(res.error.message, "bad"); return false; }
        D.ui.toast(label + " done.", "ok"); D.render(); return true;
      };
      if (needsReason) {
        D.ui.formDialog({ title: label, submitLabel: label, danger, intro: "Write a short reason. The other hospital will see it.",
          fields: [{ name: "reason", label: "Reason", type: "textarea", required: true, hint: "At least 5 characters." }], onSubmit: (v, f) => run(v.reason, f) });
      } else {
        D.ui.confirmDialog(label + "?", action === "complete" ? "This confirms the patient has arrived. The sending hospital's clinical summary will be fetched and shown to your team." : "Confirm this step.", label, () => run("", null).then((ok) => ok));
      }
    }

    const canDecide = t.status === "PENDING" && mine(t.to_hospital) && ["DOCTOR", "HOSPITAL_MANAGER", "SYSTEM_ADMIN"].includes(user.role);
    if (canDecide) actions.push(h("button", { class: "btn primary", onclick: () => act("accept", "Accept transfer", false) }, "Accept"), h("button", { class: "btn", onclick: () => act("reject", "Reject transfer", true, true) }, "Reject"));
    if (t.status === "ACCEPTED" && mine(t.from_hospital) && ["DOCTOR", "NURSE", "SYSTEM_ADMIN"].includes(user.role)) actions.push(h("button", { class: "btn primary", onclick: () => act("in-transit", "Mark as in transit", false) }, "Mark as in transit"));
    if (t.status === "IN_TRANSIT" && mine(t.to_hospital) && ["DOCTOR", "NURSE", "SYSTEM_ADMIN"].includes(user.role)) actions.push(h("button", { class: "btn primary", onclick: () => act("complete", "Confirm arrival", false) }, "Confirm arrival"));
    const canCancel = (t.status === "PENDING" && mine(t.from_hospital) && ["DOCTOR", "HOSPITAL_MANAGER", "SYSTEM_ADMIN"].includes(user.role)) ||
      (t.status === "ACCEPTED" && (mine(t.from_hospital) || mine(t.to_hospital)) && ["HOSPITAL_MANAGER", "SYSTEM_ADMIN"].includes(user.role));
    if (canCancel) actions.push(h("button", { class: "btn quiet", onclick: () => act("cancel", "Cancel transfer", true, true) }, "Cancel transfer"));

    container.append(D.ui.identityHeader(t.patient_name, [h("span", { class: "muted" }, t.from_hospital + " to " + t.to_hospital), D.ui.pill(t.priority)], actions));
    container.append(D.ui.panel("Progress", trail(t)));
    const info = [h("dt", null, "Status"), h("dd", null, D.ui.badge(t.status)),
      h("dt", null, "National ID"), h("dd", { class: "id-line" }, t.national_id),
      h("dt", null, "Requested by"), h("dd", null, t.requested_by + ", " + D.ui.fmtDateTime(t.created_at)),
      h("dt", null, "Reason"), h("dd", null, t.reason)];
    if (t.decision_reason) info.push(h("dt", null, "Reason given"), h("dd", null, t.decision_reason));
    const side = [h("dt", null, "From"), h("dd", null, t.from_hospital),
      h("dt", null, "To"), h("dd", null, t.to_hospital),
      h("dt", null, "Priority"), h("dd", null, D.ui.pill(t.priority))];
    if (t.status === "PENDING") side.push(h("dt", null, "Decision due"), h("dd", null, D.ui.fmtDateTime(t.expires_at) + " (" + D.ui.timeLeft(t.expires_at) + ")"));
    container.append(h("div", { style: "margin-top:1.25rem" }, D.ui.panel("Details", h("div", { class: "panel-body kv-cols" }, h("dl", { class: "kv" }, info), h("dl", { class: "kv kv-side" }, side)))));

    if (t.clinical_summary) container.append(h("div", { style: "margin-top:1.25rem" }, D.ui.panel("Clinical summary from " + (t.clinical_summary.source_hospital || t.from_hospital),
      h("div", { class: "panel-body" }, h("p", { class: "muted small" }, "Shared because the transfer was accepted. It holds codes and medicines only, not free-text notes."), D.summaryBlock(t.clinical_summary)))));
    else if (t.status === "IN_TRANSIT" && mine(t.to_hospital)) container.append(h("div", { class: "banner info", style: "margin-top:1.25rem" }, icon("info-circle"), "The clinical summary appears here after you confirm arrival."));

    container.append(h("div", { style: "margin-top:1.25rem" }, D.ui.panel("History", h("ol", { class: "timeline" }, t.history.map((e) =>
      h("li", null, h("span", { class: "muted" }, D.ui.fmtDateTime(e.at)),
        h("span", null, h("strong", null, e.from_status ? D.ui.statusLabel(e.to_status) : "Requested"), " by " + e.actor_name + (e.actor_hospital ? " (" + e.actor_hospital + ")" : ""),
          e.note ? h("div", { class: "muted" }, e.note) : null)))))));
  };
})();
