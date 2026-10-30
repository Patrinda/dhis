/* Small UI toolkit shared by all pages. Owner: Patrick (shared core).
   Everything is built with DOM calls, never innerHTML, so user text cannot inject markup. */
(function () {
  const D = (window.DHIS = window.DHIS || { pages: {} });

  function h(tag, attrs) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === false || v === null || v === undefined) continue;
      if (k === "class") el.className = v;
      else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
      else if (v === true) el.setAttribute(k, "");
      else el.setAttribute(k, v);
    }
    const add = (kid) => {
      if (kid === null || kid === undefined || kid === false) return;
      if (Array.isArray(kid)) kid.forEach(add);
      else el.appendChild(kid instanceof Node ? kid : document.createTextNode(String(kid)));
    };
    for (let i = 2; i < arguments.length; i++) add(arguments[i]);
    return el;
  }
  const icon = (name) => h("i", { class: "bi bi-" + name, "aria-hidden": "true" });
  const clear = (el) => { while (el.firstChild) el.removeChild(el.firstChild); return el; };

  // ---------- formatting
  const dateFmt = new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", year: "numeric" });
  const timeFmt = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit" });
  const fmtDate = (iso) => (iso ? dateFmt.format(new Date(iso)) : "–");
  const fmtDateTime = (iso) => (iso ? dateFmt.format(new Date(iso)) + ", " + timeFmt.format(new Date(iso)) : "–");
  function age(dob) {
    const d = new Date(dob), n = new Date();
    let a = n.getFullYear() - d.getFullYear();
    if (n.getMonth() < d.getMonth() || (n.getMonth() === d.getMonth() && n.getDate() < d.getDate())) a--;
    return a;
  }
  function timeLeft(iso) {
    const ms = new Date(iso) - new Date();
    if (ms <= 0) return "overdue";
    const mins = Math.round(ms / 60000);
    return mins < 90 ? mins + " min left" : Math.round(mins / 60) + " h left";
  }

  // ---------- badges
  const STATUS = {
    PENDING_SYNC: ["Not yet sent", "warn"], PENDING: ["Waiting for decision", "blue"], ACCEPTED: ["Accepted", "ok"],
    REJECTED: ["Rejected", "bad"], CANCELLED: ["Cancelled", "neutral"], EXPIRED: ["Expired", "neutral"],
    IN_TRANSIT: ["In transit", "blue"], COMPLETED: ["Completed", "ok"],
    PRESCRIBED: ["Waiting", "blue"], DISPENSED: ["Dispensed", "ok"], ORDERED: ["Waiting for result", "blue"],
  };
  const badge = (status) => { const s = STATUS[status] || [status, "neutral"]; return h("span", { class: "badge " + s[1] }, s[0]); };
  const statusLabel = (status) => (STATUS[status] || [status])[0];
  const ROLE_LABEL = { SYSTEM_ADMIN: "System administrator", REGISTRATION: "Registration officer", NURSE: "Nurse", DOCTOR: "Doctor",
    PHARMACIST: "Pharmacist", LAB_TECH: "Laboratory technician", HOSPITAL_MANAGER: "Hospital manager", DPO: "Data protection officer" };
  const priorityLabel = (p) => p.charAt(0) + p.slice(1).toLowerCase();

  // ---------- feedback
  function toast(message, kind) {
    const box = document.getElementById("toasts");
    const el = h("div", { class: "toast " + (kind || "") }, h("span", null, message));
    box.appendChild(el);
    setTimeout(() => el.remove(), kind === "bad" ? 7000 : 4500);
  }
  const spinner = () => h("div", { class: "spinner", role: "progressbar", "aria-label": "Loading" });
  const empty = (title, text, action) => h("div", { class: "empty" }, h("strong", null, title), text ? h("div", null, text) : null, action ? h("div", { style: "margin-top:1rem" }, action) : null);
  const errorBox = (resp, retry) => h("div", { class: "banner bad" }, icon("exclamation-triangle"), h("div", null, resp.error ? resp.error.message : "Something went wrong."),
    retry ? h("button", { class: "btn small", onclick: retry }, "Try again") : null);

  // ---------- layout pieces
  const pageHeader = (title, sub, actions) => h("div", { class: "page-head" },
    h("div", null, h("h1", null, title), sub ? h("div", { class: "sub" }, sub) : null),
    actions ? h("div", { class: "actions" }, actions) : null);
  const initials = (name) => String(name || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("");
  const avatar = (name, cls) => h("span", { class: "avatar " + (cls || ""), "aria-hidden": "true" }, initials(name));
  const pill = (priority) => h("span", { class: "pill pill-" + priority }, priorityLabel(priority) + " priority");
  // Header card for one person or one transfer: avatar, name, a line of detail, and the actions on the right.
  const identityHeader = (name, subKids, actions) => h("div", { class: "identity" },
    avatar(name, "big"),
    h("div", { class: "identity-text" }, h("h1", null, name), h("div", { class: "identity-sub" }, subKids)),
    actions ? h("div", { class: "actions" }, actions) : null);
  const panel = (title, body, actions) => h("section", { class: "panel" },
    title ? h("div", { class: "panel-head" }, h("h2", null, title), actions ? h("div", { class: "actions" }, actions) : null) : null, body);

  function table(columns, rows, opts) {
    opts = opts || {};
    const thead = h("thead", null, h("tr", null, columns.map((c) => h("th", { scope: "col" }, c.label))));
    const tbody = h("tbody", null, rows.map((row) => {
      const tr = h("tr", { class: (opts.onRow ? "click " : "") + (opts.rowClass ? opts.rowClass(row) : ""), tabindex: opts.onRow ? "0" : false,
        onclick: opts.onRow ? () => opts.onRow(row) : null,
        onkeydown: opts.onRow ? (e) => { if (e.key === "Enter") opts.onRow(row); } : null },
        columns.map((c) => h("td", { class: c.class || "" }, c.render ? c.render(row) : row[c.key])));
      return tr;
    }));
    return h("div", { class: "tablewrap" }, h("table", null, thead, tbody));
  }
  function pager(state, onChange) {
    const { page, count, size } = state;
    const pages = Math.max(1, Math.ceil(count / size));
    return h("div", { class: "pager" }, h("span", null, count + (count === 1 ? " record" : " records")),
      h("span", { class: "actions" }, h("button", { class: "btn small", disabled: page <= 1, onclick: () => onChange(page - 1) }, "Previous"),
        h("span", null, "Page " + page + " of " + pages),
        h("button", { class: "btn small", disabled: page >= pages, onclick: () => onChange(page + 1) }, "Next")));
  }
  function tabs(items, selected, onSelect) {
    return h("div", { class: "tabs", role: "tablist" }, items.map((t) => h("button", { role: "tab", "aria-selected": String(t.id === selected), onclick: () => onSelect(t.id) },
      t.label, t.count !== undefined ? h("span", { class: "count" + (t.alert && t.count ? " alert" : "") }, t.count) : null)));
  }
  function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }

  // ---------- forms
  // fields: [{name,label,type,required,options:[[value,label]],hint,value,rows,readonly,half}]
  function form(fields, onSubmit) {
    const wrap = h("form", { novalidate: true });
    const errBox = h("div", { class: "form-error", hidden: true, role: "alert" });
    wrap.appendChild(errBox);
    const refs = {};
    fields.forEach((f) => {
      let input;
      const id = "f-" + f.name + "-" + Math.random().toString(36).slice(2, 7);
      if (f.type === "select") {
        input = h("select", { id, name: f.name }, (f.options || []).map(([v, l]) => h("option", { value: v }, l)));
        if (f.value !== undefined) input.value = f.value;
      } else if (f.type === "textarea") {
        input = h("textarea", { id, name: f.name, rows: f.rows || 3 }, f.value || "");
      } else {
        input = h("input", { id, name: f.name, type: f.type || "text", autocomplete: f.autocomplete || "off", inputmode: f.inputmode, maxlength: f.maxlength,
          min: f.min, max: f.max, step: f.step });
        if (f.value !== undefined && f.value !== null) input.value = f.value;
      }
      if (f.readonly) input.setAttribute("readonly", "");
      if (f.required) input.setAttribute("aria-required", "true");
      const hintId = id + "-hint";
      const err = h("div", { class: "err", hidden: true, id: id + "-err" });
      const field = h("div", { class: "field" + (f.half ? " half" : "") }, h("label", { for: id }, f.label + (f.required ? "" : " (optional)")), input,
        f.hint ? h("div", { class: "hint", id: hintId }, f.hint) : null, err);
      refs[f.name] = { field, input, err, def: f };
      f._el = field;
    });
    // lay out: consecutive fields flagged "half" share a row
    let i = 0;
    while (i < fields.length) {
      if (fields[i].half && fields[i + 1] && fields[i + 1].half) {
        wrap.appendChild(h("div", { class: "grid2" }, fields[i]._el, fields[i + 1]._el)); i += 2;
      } else { wrap.appendChild(fields[i]._el); i += 1; }
    }
    wrap.addEventListener("submit", (e) => { e.preventDefault(); if (onSubmit) onSubmit(); });
    return {
      el: wrap, refs,
      values() {
        const out = {};
        for (const [name, r] of Object.entries(refs)) out[name] = r.input.value.trim();
        return out;
      },
      clearErrors() { errBox.hidden = true; Object.values(refs).forEach((r) => { r.field.classList.remove("invalid"); r.err.hidden = true; }); },
      showErrors(resp) {
        this.clearErrors();
        const err = resp.error || {};
        const details = err.details && typeof err.details === "object" ? err.details : {};
        let matched = false;
        for (const [name, msgs] of Object.entries(details)) {
          if (refs[name]) {
            refs[name].field.classList.add("invalid");
            refs[name].err.textContent = Array.isArray(msgs) ? msgs.join(" ") : String(msgs);
            refs[name].err.hidden = false; matched = true;
          }
        }
        if (!matched || err.code !== "validation_error") { errBox.textContent = err.message || "Something went wrong."; errBox.hidden = false; }
        else { errBox.textContent = "Check the highlighted fields."; errBox.hidden = false; }
      },
      requireFields() {
        let ok = true;
        this.clearErrors();
        for (const r of Object.values(refs)) {
          if (r.def.required && !r.input.value.trim()) { r.field.classList.add("invalid"); r.err.textContent = "This field is required."; r.err.hidden = false; ok = false; }
        }
        if (!ok) { errBox.textContent = "Check the highlighted fields."; errBox.hidden = false; }
        return ok;
      },
    };
  }

  // ---------- dialog
  // actions: [{label, kind:'primary'|'danger'|'', onClick: async (close, button) => {}}]
  function dialog(opts) {
    const dlg = h("dialog", { class: opts.wide ? "wide-dialog" : "", "aria-labelledby": "dlg-title" });
    const close = () => { dlg.close(); dlg.remove(); };
    const head = h("div", { class: "dlg-head" }, h("h2", { id: "dlg-title" }, opts.title), h("button", { class: "icon-btn", "aria-label": "Close", onclick: close }, icon("x-lg")));
    const foot = h("div", { class: "dlg-foot" });
    (opts.actions || []).forEach((a) => {
      const btn = h("button", { class: "btn " + (a.kind || ""), type: "button" }, a.label);
      btn.addEventListener("click", async () => {
        btn.disabled = true;
        try { await a.onClick(close, btn); } finally { btn.disabled = false; }
      });
      foot.appendChild(btn);
    });
    if (!opts.actions || !opts.actions.length) foot.appendChild(h("button", { class: "btn", onclick: close }, "Close"));
    dlg.append(head, h("div", { class: "dlg-body" }, opts.content), foot);
    dlg.addEventListener("cancel", () => dlg.remove());
    document.body.appendChild(dlg);
    dlg.showModal();
    const first = dlg.querySelector("input:not([readonly]), select, textarea");
    if (first) first.focus();
    return { close, el: dlg };
  }
  // A dialog whose primary button submits a form.
  function formDialog(opts) {
    const f = form(opts.fields, () => submit());
    let handle;
    async function submit() {
      if (!f.requireFields()) return;
      const result = await opts.onSubmit(f.values(), f);
      if (result === true) handle.close();
    }
    handle = dialog({ title: opts.title, wide: opts.wide, content: [opts.intro ? h("p", { class: "muted" }, opts.intro) : null, f.el],
      actions: [{ label: "Cancel", onClick: (c) => c() }, { label: opts.submitLabel || "Save", kind: opts.danger ? "danger" : "primary", onClick: submit }] });
    return { form: f, dialog: handle };
  }
  function confirmDialog(title, text, label, onConfirm, danger) {
    return dialog({ title, content: h("p", null, text), actions: [{ label: "Cancel", onClick: (c) => c() },
      { label, kind: danger ? "danger" : "primary", onClick: async (c) => { if ((await onConfirm()) !== false) c(); } }] });
  }

  D.ui = { h, icon, clear, fmtDate, fmtDateTime, age, timeLeft, badge, statusLabel, priorityLabel, ROLE_LABEL, toast, spinner, empty, errorBox,
    pageHeader, identityHeader, avatar, initials, pill, panel, table, pager, tabs, debounce, form, dialog, formDialog, confirmDialog };
})();
