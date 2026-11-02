/* Audit log and consent register. Owner: Masengesho Donatien. */
(function () {
  const D = window.DHIS;
  const { h, icon } = D.ui;

  D.pages.audit = async function (container, params, user) {
    const state = { page: 1, size: 25, count: 0, flagged: false, actor: "", hospital: "" };
    const holder = h("div");
    const actor = h("input", { type: "search", placeholder: "Search by person", "aria-label": "Search by person", style: "max-width:15rem" });
    const hosp = h("select", { "aria-label": "Hospital", style: "width:auto" }, h("option", { value: "" }, "All hospitals"), h("option", { value: "KRH" }, "KRH"), h("option", { value: "BDH" }, "BDH"));
    const flag = h("input", { type: "checkbox", id: "flagged", style: "width:auto;min-height:0" });
    actor.addEventListener("input", D.ui.debounce(() => { state.actor = actor.value.trim(); state.page = 1; load(); }, 300));
    hosp.addEventListener("change", () => { state.hospital = hosp.value; state.page = 1; load(); });
    flag.addEventListener("change", () => { state.flagged = flag.checked; state.page = 1; load(); });

    async function load() {
      D.ui.clear(holder).appendChild(D.ui.spinner());
      let q = "audit/?page=" + state.page + "&page_size=" + state.size;
      if (state.flagged) q += "&flagged=1"; if (state.actor) q += "&actor=" + encodeURIComponent(state.actor); if (state.hospital) q += "&hospital=" + state.hospital;
      const r = await D.api.get(q);
      D.ui.clear(holder);
      if (!r.ok) { holder.appendChild(D.ui.errorBox(r, load)); return; }
      state.count = r.data.count;
      if (!r.data.results.length) { holder.appendChild(D.ui.empty("No entries match", "Change the filters to see more.")); return; }
      holder.append(D.ui.table([
        { label: "No.", render: (e) => e.seq, class: "mono" }, { label: "When", render: (e) => D.ui.fmtDateTime(e.occurred_at), class: "nowrap" },
        { label: "Who", render: (e) => e.actor_name ? h("div", null, e.actor_name, h("div", { class: "muted small" }, (D.ui.ROLE_LABEL[e.role] || e.role) + (e.hospital ? ", " + e.hospital : ""))) : "System" },
        { label: "Action", render: (e) => h("span", null, e.action, e.flagged ? h("span", { class: "badge bad", style: "margin-left:.5rem" }, "Emergency access") : null) },
        { label: "About", render: (e) => h("span", { class: "muted small" }, e.target_ref || "–") },
        { label: "", render: (e) => (e.flagged ? reviewCell(e) : "") },
      ], r.data.results, { rowClass: (e) => (e.flagged ? "flagged" : "") }), D.ui.pager(state, (p) => { state.page = p; load(); }));
    }
    function reviewCell(e) {
      if (e.review) return h("span", { class: "badge " + (e.review.outcome === "JUSTIFIED" ? "ok" : "warn"), title: e.review.comment }, e.review.outcome === "JUSTIFIED" ? "Justified" : "Query raised");
      return user.role === "DPO" ? h("button", { class: "btn small", onclick: () => reviewDialog(e) }, "Review") : h("span", { class: "muted small" }, "Not reviewed");
    }
    function reviewDialog(e) {
      const reason = e.detail && e.detail.reason ? e.detail.reason : "No reason recorded";
      D.ui.formDialog({ title: "Review emergency access", submitLabel: "Save review",
        intro: e.actor_name + " (" + e.hospital + ") gave this reason: “" + reason + "”",
        fields: [{ name: "outcome", label: "Decision", type: "select", required: true, options: [["JUSTIFIED", "Justified"], ["QUERY", "Raise a query with the user"]] }, { name: "comment", label: "Comment", type: "textarea" }],
        async onSubmit(v, f) { const r = await D.api.post("audit/" + e.seq + "/review/", v); if (!r.ok) { f.showErrors(r); return false; } D.ui.toast("Review saved.", "ok"); load(); return true; } });
    }
    async function verify() {
      const r = await D.api.get("audit/verify/");
      if (!r.ok) { D.ui.toast(r.error.message, "bad"); return; }
      D.ui.dialog({ title: "Log integrity", content: h("div", null,
        h("div", { class: "banner " + (r.data.intact ? "info" : "bad") }, icon(r.data.intact ? "shield-check" : "shield-exclamation"),
          r.data.intact ? "All " + r.data.checked + " entries are intact. No line has been changed or removed." : "Entry number " + r.data.first_bad_seq + " does not match the chain. The log was altered after it was written."),
        h("p", { class: "muted" }, "Each entry stores a fingerprint of itself and of the entry before it. Changing any entry breaks every fingerprint after it.")) });
    }
    container.append(D.ui.pageHeader("Audit log", "Who did what, in order. Entries can be added but never edited or deleted.", h("button", { class: "btn", onclick: verify }, icon("shield-check"), "Check log integrity")),
      h("div", { class: "actions", style: "margin-bottom:1rem" }, actor, hosp, h("label", { for: "flagged", class: "actions", style: "gap:.4rem" }, flag, "Emergency access only")),
      D.ui.panel(null, holder));
    await load();
  };

  D.pages.consents = async function (container) {
    const r = await D.api.get("consents/");
    container.append(D.ui.pageHeader("Consent register", "Patient consent to share a short clinical summary for transfers. National IDs are not stored here, only a one-way fingerprint."));
    if (!r.ok) { container.append(D.ui.errorBox(r, () => D.render())); return; }
    container.append(D.ui.panel(null, r.data.length ? D.ui.table([
      { label: "Hospital", key: "hospital" }, { label: "Status", render: (c) => h("span", { class: "badge " + (c.status === "GRANTED" ? "ok" : "neutral") }, c.status === "GRANTED" ? "Granted" : "Withdrawn") },
      { label: "Recorded by", key: "recorded_by" }, { label: "Granted", render: (c) => D.ui.fmtDateTime(c.granted_at) }, { label: "Withdrawn", render: (c) => D.ui.fmtDateTime(c.withdrawn_at) },
    ], r.data) : D.ui.empty("No consent recorded yet", "Registration staff and doctors record consent on the patient page.")));
  };
})();
