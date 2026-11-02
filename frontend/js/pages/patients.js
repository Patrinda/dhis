/* Patient list, registration and patient detail. Owner: Mukeshimana Justine (patient service + this page). */
(function () {
  const D = window.DHIS;
  const { h, icon } = D.ui;

  D.pages.patientList = async function (container, params, user) {
    const state = { page: 1, size: 15, count: 0, q: (new URLSearchParams((location.hash.split("?")[1] || ""))).get("q") || "" };
    const holder = h("div");
    const canRegister = user.role === "REGISTRATION";

    async function load() {
      D.ui.clear(holder).appendChild(D.ui.spinner());
      const r = await D.api.get("patients/?page=" + state.page + "&page_size=" + state.size + (state.q ? "&q=" + encodeURIComponent(state.q) : ""));
      D.ui.clear(holder);
      if (!r.ok) { holder.appendChild(D.ui.errorBox(r, load)); return; }
      state.count = r.data.count;
      if (!r.data.results.length) {
        holder.appendChild(D.ui.empty(state.q ? "No patient matches “" + state.q + "”" : "No patients registered yet",
          state.q ? "Check the spelling, or search with the first digits of the national ID." : (canRegister ? "Register the first patient to begin." : "Registered patients will appear here."),
          canRegister && !state.q ? h("button", { class: "btn primary", onclick: () => registerDialog(load) }, "Register patient") : null));
        return;
      }
      holder.append(D.ui.table([
        { label: "Name", render: (p) => h("strong", null, p.full_name) },
        { label: "National ID", render: (p) => h("span", { class: "id-line" }, p.national_id) },
        { label: "Sex and age", render: (p) => (p.sex === "F" ? "Female" : "Male") + ", " + D.ui.age(p.date_of_birth) },
        { label: "Phone", render: (p) => p.phone || "–" },
        { label: "Registered", render: (p) => D.ui.fmtDate(p.created_at) },
      ], r.data.results, { onRow: (p) => (location.hash = "#/patients/" + p.id) }), D.ui.pager(state, (pg) => { state.page = pg; load(); }));
    }

    container.append(
      D.ui.pageHeader("Patients", state.q ? "Results for “" + state.q + "”" : (user.role === "SYSTEM_ADMIN" ? "All hospitals" : "Patients registered at your hospital"),
        [state.q ? h("a", { class: "btn", href: "#/patients" }, "Clear search") : null,
          canRegister ? h("button", { class: "btn primary", onclick: () => registerDialog(load) }, icon("person-plus"), "Register patient") : null]),
      D.ui.panel(null, holder));
    await load();
  };

  function registerDialog(onDone) {
    const info = h("div", { class: "banner info", hidden: true, role: "status" });
    const checkBtn = h("button", { class: "btn", type: "button" }, "Check other hospitals");
    let checked = false, blocked = false;
    const fields = [
      { name: "national_id", label: "National ID", required: true, maxlength: 16, inputmode: "numeric", hint: "16 digits. We check every hospital before registering." },
      { name: "first_name", label: "First name", required: true, half: true }, { name: "last_name", label: "Last name", required: true, half: true },
      { name: "sex", label: "Sex", type: "select", required: true, options: [["F", "Female"], ["M", "Male"]], half: true },
      { name: "date_of_birth", label: "Date of birth", type: "date", required: true, half: true, max: new Date().toISOString().slice(0, 10) },
      { name: "phone", label: "Phone", inputmode: "tel", half: true, hint: "For example 0788123456" }, { name: "district", label: "District of residence", half: true },
      { name: "next_of_kin_name", label: "Next of kin", half: true }, { name: "next_of_kin_phone", label: "Next of kin phone", half: true },
    ];
    const dlg = D.ui.formDialog({
      title: "Register patient", wide: true, submitLabel: "Register patient", fields,
      async onSubmit(v, f) {
        if (blocked) { f.showErrors({ error: { message: "This person is already registered elsewhere. Request a transfer instead." } }); return false; }
        if (!checked) { const ok = await check(); if (!ok) return false; }
        const r = await D.api.post("patients/", v, { idempotent: true });
        if (!r.ok) {
          if (r.error && r.error.code === "duplicate_elsewhere") { blocked = true; showInfo(r.error.message, "bad"); }
          f.showErrors(r); return false;
        }
        D.ui.toast("Registered " + r.data.full_name + (r.data.lookup_partial ? ". One hospital could not be checked; the ID claim still protects against duplicates." : "."), "ok");
        onDone(); location.hash = "#/patients/" + r.data.id; return true;
      },
    });
    const f = dlg.form;
    const idField = f.refs.national_id.field;
    idField.appendChild(h("div", { style: "margin-top:.5rem" }, checkBtn));
    f.el.insertBefore(info, f.el.firstChild.nextSibling);
    function showInfo(text, kind) { info.className = "banner " + (kind || "info"); info.textContent = text; info.hidden = false; }
    async function check() {
      const id = f.refs.national_id.input.value.trim();
      if (!/^\d{16}$/.test(id)) { f.showErrors({ error: { code: "validation_error", message: "Check the highlighted fields.", details: { national_id: ["National ID must be exactly 16 digits."] } } }); return false; }
      checkBtn.disabled = true;
      const r = await D.api.post("patients/lookup/", { national_id: id });
      checkBtn.disabled = false;
      if (!r.ok) { f.showErrors(r); return false; }
      if (r.data.local) { blocked = true; showInfo("This person is already registered at your hospital.", "bad"); return false; }
      if (r.data.found_at.length) { blocked = true; showInfo("Already registered at " + r.data.found_at.join(", ") + ". Request a transfer instead of registering again.", "bad"); return false; }
      blocked = false; checked = true;
      showInfo(r.data.partial ? "Not found, but " + r.data.unreachable.join(", ") + " could not be checked. You can continue; duplicates are still blocked." : "Not registered at any hospital. You can continue.", r.data.partial ? "warn" : "info");
      return true;
    }
    checkBtn.addEventListener("click", check);
    f.refs.national_id.input.addEventListener("input", () => { checked = false; blocked = false; info.hidden = true; });
  }

  D.pages.patientDetail = async function (container, params, user) {
    const r = await D.api.get("patients/" + params[0] + "/");
    if (!r.ok) {
      container.append(D.ui.pageHeader("Patient not found", null, h("a", { class: "btn", href: "#/patients" }, "Back to patients")), D.ui.errorBox(r));
      return;
    }
    const p = r.data;
    const canEdit = user.role === "REGISTRATION";
    const actions = [h("a", { class: "btn", href: "#/patients" }, "All patients")];
    if (canEdit) actions.push(h("button", { class: "btn", onclick: () => editDialog(p) }, icon("pencil"), "Edit contact details"));
    if (user.role === "DOCTOR") actions.push(h("button", { class: "btn primary", onclick: () => D.transfers.requestDialog(p) }, icon("arrow-left-right"), "Request transfer"));

    container.append(D.ui.identityHeader(p.full_name, [h("span", { class: "muted" }, (p.sex === "F" ? "Female" : "Male") + ", " + D.ui.age(p.date_of_birth) + " years"), h("span", { class: "muted" }, "Registered at " + p.hospital_code + " on " + D.ui.fmtDate(p.created_at))], actions));
    container.append(D.ui.panel("Details", h("div", { class: "panel-body" }, h("dl", { class: "kv" },
      h("dt", null, "National ID"), h("dd", { class: "id-line" }, p.national_id),
      h("dt", null, "Sex and age"), h("dd", null, (p.sex === "F" ? "Female" : "Male") + ", " + D.ui.age(p.date_of_birth) + " years (born " + D.ui.fmtDate(p.date_of_birth) + ")"),
      h("dt", null, "Phone"), h("dd", null, p.phone || "–"),
      h("dt", null, "District"), h("dd", null, p.district || "–"),
      h("dt", null, "Next of kin"), h("dd", null, p.next_of_kin_name ? p.next_of_kin_name + (p.next_of_kin_phone ? ", " + p.next_of_kin_phone : "") : "–")))));

    if (["REGISTRATION", "DOCTOR"].includes(user.role)) {
      const slot = h("div");
      container.append(h("div", { style: "margin-top:1.25rem" }, D.ui.panel("Consent for transfers", slot)));
      await consentBlock(slot, p, user);
    }
    if (["DOCTOR", "NURSE"].includes(user.role)) {
      const slot = h("div", { style: "margin-top:1.25rem" });
      container.append(slot);
      await D.pages.recordsPanel(slot, p, user);
    }
  };

  async function consentBlock(slot, p, user) {
    const r = await D.api.post("consents/status/", { national_id: p.national_id });
    D.ui.clear(slot);
    if (!r.ok) { slot.appendChild(D.ui.errorBox(r)); return; }
    const granted = r.data.granted;
    slot.appendChild(h("div", { class: "panel-body", style: "display:flex;justify-content:space-between;gap:1rem;align-items:center;flex-wrap:wrap" },
      h("div", null, h("span", { class: "badge " + (granted ? "ok" : "warn") }, granted ? "Consent recorded" : "No consent recorded"),
        h("p", { class: "muted small", style: "margin:.5rem 0 0" }, "A transfer request needs the patient's consent to share a short clinical summary with the receiving hospital.")),
      h("button", { class: "btn" + (granted ? "" : " primary"), onclick: async () => {
        const res = await D.api.post(granted ? "consents/withdraw/" : "consents/", { national_id: p.national_id });
        if (!res.ok) { D.ui.toast(res.error.message, "bad"); return; }
        D.ui.toast(granted ? "Consent withdrawn." : "Consent recorded.", "ok"); consentBlock(slot, p, user);
      } }, granted ? "Withdraw consent" : "Record consent")));
  }

  function editDialog(p) {
    D.ui.formDialog({
      title: "Edit contact details", submitLabel: "Save changes", intro: "Name, sex, date of birth and national ID cannot be changed here.",
      fields: [{ name: "phone", label: "Phone", value: p.phone }, { name: "district", label: "District", value: p.district },
        { name: "next_of_kin_name", label: "Next of kin", value: p.next_of_kin_name }, { name: "next_of_kin_phone", label: "Next of kin phone", value: p.next_of_kin_phone }],
      async onSubmit(v, f) {
        const r = await D.api.patch("patients/" + p.id + "/", Object.assign({}, v, { version: p.version }));
        if (r.status === 409) { f.showErrors({ error: { message: "Someone else changed this record. Close this window and reload the page, then try again." } }); return false; }
        if (!r.ok) { f.showErrors(r); return false; }
        D.ui.toast("Details saved.", "ok"); D.render(); return true;
      },
    });
  }
})();
