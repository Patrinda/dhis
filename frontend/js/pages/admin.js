/* Users and hospitals, and the system status page. Owner: Uwikuzo Theopiste. */
(function () {
  const D = window.DHIS;
  const { h, icon } = D.ui;
  const ROLES = Object.entries(D.ui.ROLE_LABEL);

  D.pages.admin = async function (container) {
    let tab = "users";
    const body = h("div");
    const hospitals = await D.api.get("auth/hospitals/");
    if (!hospitals.ok) { container.appendChild(D.ui.errorBox(hospitals)); return; }

    async function users() {
      D.ui.clear(body).appendChild(D.ui.spinner());
      const r = await D.api.get("auth/users/?page_size=100");
      D.ui.clear(body);
      if (!r.ok) { body.appendChild(D.ui.errorBox(r, users)); return; }
      body.appendChild(D.ui.panel(null, D.ui.table([
        { label: "Name", render: (u) => h("div", null, h("strong", null, (u.first_name + " " + u.last_name).trim() || u.username), h("div", { class: "muted small" }, u.username)) },
        { label: "Role", render: (u) => D.ui.ROLE_LABEL[u.role] || u.role },
        { label: "Hospital", render: (u) => u.hospital_code || "National" },
        { label: "Status", render: (u) => h("span", { class: "badge " + (u.is_active ? "ok" : "neutral") }, u.is_active ? "Active" : "Deactivated") },
        { label: "Last sign-in", render: (u) => D.ui.fmtDateTime(u.last_login) },
        { label: "", render: (u) => h("button", { class: "btn small", onclick: () => userDialog(u) }, "Edit") },
      ], r.data.results)));
    }

    function userDialog(u) {
      const editing = !!u;
      const fields = [
        { name: "username", label: "Username", required: true, value: u && u.username, readonly: editing },
        { name: "first_name", label: "First name", required: true, value: u && u.first_name, half: true },
        { name: "last_name", label: "Last name", required: true, value: u && u.last_name, half: true },
        { name: "email", label: "Email", type: "email", value: u && u.email },
        { name: "role", label: "Role", type: "select", required: true, options: ROLES, value: u ? u.role : "NURSE", half: true },
        { name: "hospital", label: "Hospital", type: "select", options: [["", "National (no hospital)"]].concat(hospitals.data.map((x) => [x.code, x.code + " – " + x.name])), value: u ? (u.hospital || "") : "", half: true },
        { name: "password", label: editing ? "New password" : "Password", type: "password", required: !editing, hint: "At least 10 characters. Leave empty to keep the current one.", autocomplete: "new-password" },
      ];
      if (editing) fields.push({ name: "is_active", label: "Account status", type: "select", options: [["true", "Active"], ["false", "Deactivated"]], value: String(u.is_active) });
      D.ui.formDialog({
        title: editing ? "Edit user" : "Add user", fields, submitLabel: editing ? "Save changes" : "Add user",
        async onSubmit(v, f) {
          const body = Object.assign({}, v, { hospital: v.hospital || null });
          if (!v.password) delete body.password;
          if (editing) body.is_active = v.is_active === "true"; else delete body.is_active;
          if (editing) delete body.username;
          const r = editing ? await D.api.patch("auth/users/" + u.id + "/", body) : await D.api.post("auth/users/", body, { idempotent: true });
          if (!r.ok) { f.showErrors(r); return false; }
          D.ui.toast(editing ? "User saved." : "User added.", "ok"); users(); return true;
        },
      });
    }

    async function hospitalTab() {
      D.ui.clear(body);
      body.appendChild(D.ui.panel(null, D.ui.table([
        { label: "Code", render: (x) => h("strong", null, x.code) }, { label: "Name", key: "name" }, { label: "District", key: "district" },
        { label: "Patient service", render: (x) => h("code", null, x.patient_url || "–") }, { label: "Records service", render: (x) => h("code", null, x.records_url || "–") },
        { label: "", render: (x) => h("button", { class: "btn small", onclick: () => hospitalDialog(x) }, "Edit") },
      ], hospitals.data)));
    }
    function hospitalDialog(x) {
      const editing = !!x;
      D.ui.formDialog({
        title: editing ? "Edit hospital" : "Add hospital", submitLabel: editing ? "Save changes" : "Add hospital",
        intro: "The service addresses tell the gateway where this hospital's patient and records services run.",
        fields: [
          { name: "code", label: "Code", required: true, value: x && x.code, readonly: editing, maxlength: 10, hint: "Short and unique, for example KRH." },
          { name: "name", label: "Name", required: true, value: x && x.name },
          { name: "district", label: "District", required: true, value: x && x.district },
          { name: "patient_url", label: "Patient service address", value: x && x.patient_url, hint: "For example http://127.0.0.1:8000" },
          { name: "records_url", label: "Records service address", value: x && x.records_url },
        ],
        async onSubmit(v, f) {
          const r = editing ? await D.api.patch("auth/hospitals/" + x.id + "/", v) : await D.api.post("auth/hospitals/", v);
          if (!r.ok) { f.showErrors(r); return false; }
          D.ui.toast("Hospital saved. Reloading the list.", "ok"); D.render(); return true;
        },
      });
    }

    function draw() {
      const actions = h("button", { class: "btn primary", onclick: () => (tab === "users" ? userDialog() : hospitalDialog()) }, icon("plus-lg"), tab === "users" ? "Add user" : "Add hospital");
      D.ui.clear(container);
      container.append(D.ui.pageHeader("Users and hospitals", "Create staff accounts and set which hospital each person belongs to.", actions),
        D.ui.tabs([{ id: "users", label: "Users" }, { id: "hospitals", label: "Hospitals" }], tab, (t) => { tab = t; draw(); }), body);
      tab === "users" ? users() : hospitalTab();
    }
    draw();
  };

  D.pages.status = async function (container) {
    const holder = h("div", { class: "stack" });
    async function load() {
      const [health, queue] = await Promise.all([fetch("/api/health/").then((r) => r.json()).catch(() => null), D.api.get("queue/")]);
      D.ui.clear(holder);
      if (!health) { holder.appendChild(D.ui.errorBox({ error: { message: "The gateway did not answer." } }, load)); return; }
      holder.appendChild(D.ui.panel("Services", D.ui.table([
        { label: "Service", render: (r) => h("strong", null, r[0]) },
        { label: "State", render: (r) => h("span", { class: "badge " + (r[1].up ? "ok" : "bad") }, r[1].up ? "Running" : "Not responding") },
        { label: "Response time", render: (r) => (r[1].ms === null ? "–" : r[1].ms + " ms") },
      ], Object.entries(health.services)), h("button", { class: "btn small", onclick: load }, icon("arrow-clockwise"), "Refresh")));
      const circuits = Object.entries(health.circuits || {});
      holder.appendChild(D.ui.panel("Connection protection (circuit breakers)", circuits.length ? D.ui.table([
        { label: "Service address", render: (r) => h("code", null, r[0]) },
        { label: "State", render: (r) => h("span", { class: "badge " + (r[1] === "CLOSED" ? "ok" : r[1] === "OPEN" ? "bad" : "warn") }, r[1] === "CLOSED" ? "Closed (normal)" : r[1] === "OPEN" ? "Open (calls blocked)" : "Half open (testing)") },
      ], circuits) : D.ui.empty("No calls made yet", "A circuit opens after five failed calls to the same service and is tested again after 30 seconds.")));
      const rows = queue.ok ? queue.data.results : [];
      holder.appendChild(D.ui.panel("Transfer requests waiting to be sent", rows.length ? D.ui.table([
        { label: "Request", key: "summary" }, { label: "State", render: (r) => D.ui.badge(r.status) },
        { label: "Tries", key: "attempts" }, { label: "Saved", render: (r) => D.ui.fmtDateTime(r.created_at) },
        { label: "Last problem", render: (r) => r.last_error || "–" },
      ], rows) : D.ui.empty("Nothing is waiting", "When the transfer service is down, new requests are saved here and sent automatically."),
        h("button", { class: "btn small", onclick: async () => { const r = await D.api.post("queue/flush/", {}); D.ui.toast(r.ok ? r.data.completed + " request(s) sent." : r.error.message, r.ok ? "ok" : "bad"); load(); } }, "Send now")));
    }
    container.append(D.ui.pageHeader("System status", "Which services are running, and how the system protects itself when one stops."), holder);
    await load();
  };
})();
