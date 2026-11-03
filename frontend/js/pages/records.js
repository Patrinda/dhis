/* Clinical records panel, pharmacy, laboratory and emergency access.
   Owner: John Seemore (records service + this page). */
(function () {
  const D = window.DHIS;
  const { h, icon } = D.ui;
  const ENC_TYPES = [["OUTPATIENT", "Outpatient"], ["EMERGENCY", "Emergency"], ["INPATIENT", "Inpatient"]];

  // ---- panel shown on the patient page (called by patients.js)
  D.pages.recordsPanel = async function (slot, patient, user) {
    const isDoctor = user.role === "DOCTOR";
    const wrap = h("div", { class: "stack" });
    slot.appendChild(wrap);

    async function load() {
      D.ui.clear(wrap).appendChild(D.ui.spinner());
      const [enc, alg] = await Promise.all([D.api.get("records/encounters/?patient_id=" + patient.id + "&page_size=50"), D.api.get("records/allergies/?patient_id=" + patient.id)]);
      D.ui.clear(wrap);
      // allergies first: the safety-critical fact
      wrap.appendChild(D.ui.panel("Allergies", h("div", { class: "panel-body" }, alg.ok && alg.data.length
        ? h("div", { class: "chips" }, alg.data.map((a) => h("span", { class: "chip " + a.severity, title: a.reaction || "" }, a.substance + (a.reaction ? " (" + a.reaction + ")" : ""))))
        : h("span", { class: "muted" }, alg.ok ? "No allergies recorded." : alg.error.message)),
        h("button", { class: "btn small", onclick: () => allergyDialog(patient, load) }, icon("plus-lg"), "Add allergy")));

      const body = !enc.ok ? D.ui.errorBox(enc, load) : !enc.data.results.length
        ? D.ui.empty("No visits recorded", "Record triage or a consultation to start this patient's history.")
        : h("div", null, enc.data.results.map((e) => encounterEntry(e, isDoctor, load)));
      wrap.appendChild(D.ui.panel("Visits", body, h("button", { class: "btn primary small", onclick: () => encounterDialog(patient, user, load) }, icon("plus-lg"), "New visit")));
    }
    await load();
  };

  function vitalsLine(e) {
    const parts = [];
    if (e.temperature_c) parts.push(["Temp", e.temperature_c + " °C"]);
    if (e.pulse) parts.push(["Pulse", e.pulse + "/min"]);
    if (e.systolic) parts.push(["BP", e.systolic + "/" + (e.diastolic || "?")]);
    if (e.spo2) parts.push(["SpO₂", e.spo2 + "%"]);
    if (e.weight_kg) parts.push(["Weight", e.weight_kg + " kg"]);
    return parts.length ? h("div", { class: "vitals" }, parts.map(([k, v]) => h("span", null, k + " ", h("b", null, v)))) : null;
  }

  function encounterEntry(e, isDoctor, reload) {
    const rx = e.prescriptions.length ? h("div", { class: "sublist" }, h("strong", null, "Medicines"), e.prescriptions.map((p) =>
      h("div", null, h("span", null, p.drug_name + ", " + p.dose + ", " + p.frequency + ", " + p.duration_days + " days"), D.ui.badge(p.status)))) : null;
    const labs = e.lab_orders.length ? h("div", { class: "sublist" }, h("strong", null, "Laboratory"), e.lab_orders.map((o) =>
      h("div", null, h("span", null, o.test_name + (o.status === "COMPLETED" ? ": " + o.result_value + " " + o.result_unit : "")),
        o.status === "COMPLETED" ? h("span", { class: "badge " + (o.result_flag === "NORMAL" ? "ok" : "bad") }, o.result_flag.toLowerCase()) : D.ui.badge(o.status)))) : null;
    return h("div", { class: "entry" },
      h("div", { class: "entry-head" },
        h("div", null, h("strong", null, D.ui.fmtDateTime(e.created_at)), " ", h("span", { class: "badge neutral" }, (ENC_TYPES.find((t) => t[0] === e.encounter_type) || [0, e.encounter_type])[1])),
        h("span", { class: "muted small" }, e.author_name + ", " + (D.ui.ROLE_LABEL[e.author_role] || e.author_role).toLowerCase())),
      e.complaint ? h("div", null, h("span", { class: "muted" }, "Complaint: "), e.complaint) : null,
      vitalsLine(e),
      e.diagnosis_code ? h("div", null, h("span", { class: "muted" }, "Diagnosis: "), h("strong", null, e.diagnosis_code), e.diagnosis_text ? " " + e.diagnosis_text : "") : null,
      e.plan ? h("div", null, h("span", { class: "muted" }, "Plan: "), e.plan) : null,
      rx, labs,
      isDoctor ? h("div", { class: "actions", style: "margin-top:.7rem" },
        h("button", { class: "btn small", onclick: () => diagnosisDialog(e, reload) }, "Diagnosis and plan"),
        h("button", { class: "btn small", onclick: () => prescribeDialog(e, reload) }, "Prescribe"),
        h("button", { class: "btn small", onclick: () => labDialog(e, reload) }, "Order lab test")) : null);
  }

  function num(v) { return v === "" ? undefined : Number(v); }

  function encounterDialog(patient, user, reload) {
    const isDoctor = user.role === "DOCTOR";
    const fields = [
      { name: "encounter_type", label: "Type of visit", type: "select", options: ENC_TYPES, required: true },
      { name: "complaint", label: "Reason for visit", type: "textarea", rows: 2 },
      { name: "temperature_c", label: "Temperature (°C)", type: "number", step: "0.1", half: true }, { name: "pulse", label: "Pulse (per minute)", type: "number", half: true },
      { name: "systolic", label: "Systolic pressure", type: "number", half: true }, { name: "diastolic", label: "Diastolic pressure", type: "number", half: true },
      { name: "spo2", label: "Oxygen saturation (%)", type: "number", half: true }, { name: "weight_kg", label: "Weight (kg)", type: "number", step: "0.1", half: true },
    ];
    if (isDoctor) fields.push({ name: "diagnosis_code", label: "Diagnosis code (ICD-10)", hint: "For example B50.9 for malaria or J18.9 for pneumonia." },
      { name: "diagnosis_text", label: "Diagnosis in words" }, { name: "plan", label: "Plan", type: "textarea", rows: 2 });
    D.ui.formDialog({
      title: "New visit for " + patient.full_name, wide: true, submitLabel: "Save visit",
      intro: isDoctor ? null : "Nurses record triage. A doctor adds the diagnosis and plan.", fields,
      async onSubmit(v, f) {
        const body = { patient_id: patient.id, encounter_type: v.encounter_type, complaint: v.complaint };
        ["temperature_c", "pulse", "systolic", "diastolic", "spo2", "weight_kg"].forEach((k) => { if (v[k] !== "") body[k] = k === "temperature_c" || k === "weight_kg" ? v[k] : num(v[k]); });
        if (isDoctor) Object.assign(body, { diagnosis_code: v.diagnosis_code, diagnosis_text: v.diagnosis_text, plan: v.plan });
        const r = await D.api.post("records/encounters/", body, { idempotent: true });
        if (!r.ok) { f.showErrors(r); return false; }
        D.ui.toast("Visit saved.", "ok"); reload(); return true;
      },
    });
  }

  function diagnosisDialog(e, reload) {
    D.ui.formDialog({
      title: "Diagnosis and plan", submitLabel: "Save", fields: [
        { name: "diagnosis_code", label: "Diagnosis code (ICD-10)", value: e.diagnosis_code, hint: "For example B50.9" },
        { name: "diagnosis_text", label: "Diagnosis in words", value: e.diagnosis_text }, { name: "plan", label: "Plan", type: "textarea", value: e.plan }],
      async onSubmit(v, f) {
        const r = await D.api.patch("records/encounters/" + e.id + "/", Object.assign({}, v, { version: e.version }));
        if (r.status === 409) { f.showErrors({ error: { message: "This visit was changed by someone else. Reload the page and try again." } }); return false; }
        if (!r.ok) { f.showErrors(r); return false; }
        D.ui.toast("Saved.", "ok"); reload(); return true;
      },
    });
  }
  function prescribeDialog(e, reload) {
    D.ui.formDialog({
      title: "Prescribe a medicine", submitLabel: "Prescribe", fields: [
        { name: "drug_name", label: "Medicine", required: true }, { name: "dose", label: "Dose", required: true, half: true, hint: "For example 500 mg" },
        { name: "frequency", label: "How often", required: true, half: true, hint: "For example twice daily" },
        { name: "duration_days", label: "Number of days", type: "number", required: true, min: 1, max: 365 }],
      async onSubmit(v, f) {
        const r = await D.api.post("records/prescriptions/", Object.assign({}, v, { encounter: e.id, duration_days: Number(v.duration_days) }), { idempotent: true });
        if (!r.ok) { f.showErrors(r); return false; }
        D.ui.toast("Prescription sent to the pharmacy.", "ok"); reload(); return true;
      },
    });
  }
  function labDialog(e, reload) {
    D.ui.formDialog({
      title: "Order a laboratory test", submitLabel: "Order test", fields: [{ name: "test_name", label: "Test", required: true, hint: "For example Malaria rapid test" }],
      async onSubmit(v, f) {
        const r = await D.api.post("records/lab-orders/", { encounter: e.id, test_name: v.test_name }, { idempotent: true });
        if (!r.ok) { f.showErrors(r); return false; }
        D.ui.toast("Test ordered.", "ok"); reload(); return true;
      },
    });
  }
  function allergyDialog(patient, reload) {
    D.ui.formDialog({
      title: "Add an allergy", submitLabel: "Add allergy", fields: [
        { name: "substance", label: "Allergic to", required: true }, { name: "reaction", label: "Reaction" },
        { name: "severity", label: "Severity", type: "select", options: [["MILD", "Mild"], ["MODERATE", "Moderate"], ["SEVERE", "Severe"]], value: "MODERATE" }],
      async onSubmit(v, f) {
        const r = await D.api.post("records/allergies/", Object.assign({ patient_id: patient.id }, v), { idempotent: true });
        if (!r.ok) { f.showErrors(r); return false; }
        D.ui.toast("Allergy recorded.", "ok"); reload(); return true;
      },
    });
  }

  // ---- pharmacy
  D.pages.pharmacy = async function (container, params, user) {
    const state = { status: "PRESCRIBED" };
    const holder = h("div");
    async function load() {
      D.ui.clear(holder).appendChild(D.ui.spinner());
      const r = await D.api.get("records/prescriptions/?page_size=50&status=" + state.status);
      D.ui.clear(holder);
      if (!r.ok) { holder.appendChild(D.ui.errorBox(r, load)); return; }
      if (!r.data.results.length) { holder.appendChild(D.ui.empty(state.status === "PRESCRIBED" ? "No prescriptions waiting" : "Nothing dispensed yet", "New prescriptions from doctors appear here.")); return; }
      holder.appendChild(D.ui.table([
        { label: "Patient", render: (p) => h("strong", null, p.patient_name || "–") },
        { label: "Medicine", render: (p) => p.drug_name + ", " + p.dose },
        { label: "Instructions", render: (p) => p.frequency + " for " + p.duration_days + " days" },
        { label: "Prescribed by", render: (p) => p.prescribed_by + ", " + D.ui.fmtDateTime(p.created_at) },
        { label: "", render: (p) => (p.status === "PRESCRIBED" && user.role === "PHARMACIST"
          ? h("button", { class: "btn primary small", onclick: () => dispense(p) }, "Dispense") : D.ui.badge(p.status)) },
      ], r.data.results));
    }
    async function dispense(p) {
      D.ui.confirmDialog("Dispense this medicine?", p.drug_name + " for " + p.patient_name + ". Check the patient's allergies first.", "Dispense", async () => {
        const r = await D.api.post("records/prescriptions/" + p.id + "/dispense/", {});
        D.ui.toast(r.ok ? "Marked as dispensed." : r.error.message, r.ok ? "ok" : "bad"); load();
      });
    }
    container.append(D.ui.pageHeader("Pharmacy", "Prescriptions from doctors at your hospital"),
      D.ui.tabs([{ id: "PRESCRIBED", label: "Waiting" }, { id: "DISPENSED", label: "Dispensed" }], state.status, (s) => { state.status = s; D.render(); }), D.ui.panel(null, holder));
    await load();
  };

  // ---- laboratory
  D.pages.lab = async function (container, params, user) {
    const state = { status: "ORDERED" };
    const holder = h("div");
    async function load() {
      D.ui.clear(holder).appendChild(D.ui.spinner());
      const r = await D.api.get("records/lab-orders/?page_size=50&status=" + state.status);
      D.ui.clear(holder);
      if (!r.ok) { holder.appendChild(D.ui.errorBox(r, load)); return; }
      if (!r.data.results.length) { holder.appendChild(D.ui.empty(state.status === "ORDERED" ? "No tests waiting" : "No results yet", "Tests ordered by doctors appear here.")); return; }
      holder.appendChild(D.ui.table([
        { label: "Patient", render: (o) => h("strong", null, o.patient_name || "–") }, { label: "Test", key: "test_name" },
        { label: "Ordered", render: (o) => o.ordered_by + ", " + D.ui.fmtDateTime(o.created_at) },
        { label: state.status === "ORDERED" ? "" : "Result", render: (o) => (o.status === "ORDERED"
          ? (user.role === "LAB_TECH" ? h("button", { class: "btn primary small", onclick: () => resultDialog(o) }, "Enter result") : D.ui.badge(o.status))
          : h("span", null, o.result_value + " " + o.result_unit + " ", h("span", { class: "badge " + (o.result_flag === "NORMAL" ? "ok" : "bad") }, o.result_flag.toLowerCase()))) },
      ], r.data.results));
    }
    function resultDialog(o) {
      D.ui.formDialog({
        title: o.test_name + " for " + o.patient_name, submitLabel: "Save result", fields: [
          { name: "result_value", label: "Result", required: true, half: true }, { name: "result_unit", label: "Unit", half: true },
          { name: "result_flag", label: "Interpretation", type: "select", required: true, options: [["NORMAL", "Normal"], ["HIGH", "High"], ["LOW", "Low"], ["CRITICAL", "Critical"]] }],
        async onSubmit(v, f) {
          const r = await D.api.post("records/lab-orders/" + o.id + "/result/", v);
          if (!r.ok) { f.showErrors(r); return false; }
          D.ui.toast("Result saved.", "ok"); load(); return true;
        },
      });
    }
    container.append(D.ui.pageHeader("Laboratory", "Test orders from doctors at your hospital"),
      D.ui.tabs([{ id: "ORDERED", label: "Waiting for result" }, { id: "COMPLETED", label: "Completed" }], state.status, (s) => { state.status = s; D.render(); }), D.ui.panel(null, holder));
    await load();
  };

  // ---- emergency access (break glass)
  D.pages.emergency = async function (container) {
    const out = h("div", { style: "margin-top:1.25rem" });
    const f = D.ui.form([
      { name: "national_id", label: "National ID of the patient", required: true, maxlength: 16, inputmode: "numeric" },
      { name: "reason", label: "Why do you need this now?", type: "textarea", required: true, hint: "At least 15 characters. The data protection officer reads this." },
    ], go);
    const btn = h("button", { class: "btn danger", type: "submit" }, icon("shield-exclamation"), "Open emergency summary");
    f.el.appendChild(btn);
    async function go() {
      if (!f.requireFields()) return;
      btn.disabled = true;
      const r = await D.api.post("records/break-glass/", f.values());
      btn.disabled = false;
      D.ui.clear(out);
      if (!r.ok) { f.showErrors(r); return; }
      if (!r.data.found) { out.appendChild(D.ui.empty("No summary found", r.data.message + (r.data.unreachable.length ? " Not reachable: " + r.data.unreachable.join(", ") + "." : ""))); return; }
      r.data.summaries.forEach((s) => out.appendChild(D.ui.panel("Summary from " + s.source_hospital, h("div", { class: "panel-body" }, summaryBlock(s)))));
    }
    container.append(D.ui.pageHeader("Emergency access", "Use only when a patient from another hospital needs care now and cannot wait for a transfer."),
      h("div", { class: "banner warn" }, icon("exclamation-triangle"), "Every use of this page is recorded with your name and reason, and is reviewed by the data protection officer."),
      D.ui.panel(null, h("div", { class: "panel-body" }, f.el)), out);
  };

  // Shared with the transfers page, which shows the same summary after arrival.
  D.summaryBlock = summaryBlock;
  function summaryBlock(s) {
    return h("div", { class: "stack" },
      h("div", null, h("h3", null, "Allergies"), s.allergies && s.allergies.length ? h("div", { class: "chips", style: "margin-top:.4rem" }, s.allergies.map((a) => h("span", { class: "chip " + a.severity }, a.substance))) : h("span", { class: "muted" }, "None recorded")),
      h("div", null, h("h3", null, "Diagnoses"), s.diagnoses && s.diagnoses.length ? h("ul", { style: "margin:.4rem 0 0;padding-left:1.1rem" }, s.diagnoses.map((d) => h("li", null, h("strong", null, d.code), " " + (d.text || "") + " (" + D.ui.fmtDate(d.date) + ")"))) : h("span", { class: "muted" }, "None recorded")),
      h("div", null, h("h3", null, "Current medicines"), s.active_medicines && s.active_medicines.length ? h("ul", { style: "margin:.4rem 0 0;padding-left:1.1rem" }, s.active_medicines.map((m) => h("li", null, m.drug + ", " + m.dose + ", " + m.frequency))) : h("span", { class: "muted" }, "None recorded")),
      s.latest_vitals ? h("div", null, h("h3", null, "Latest vital signs (" + D.ui.fmtDate(s.latest_vitals.date) + ")"), vitalsLine({ temperature_c: s.latest_vitals.temperature_c, pulse: s.latest_vitals.pulse, systolic: s.latest_vitals.systolic, diastolic: s.latest_vitals.diastolic, spo2: s.latest_vitals.spo2 })) : null,
      s.note ? h("p", { class: "muted" }, s.note) : null);
  }
})();
