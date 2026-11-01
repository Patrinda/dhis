/* Sign-in page. Owner: Uwikuzo Theopiste (identity folder + login/admin pages). */
(function () {
  const D = window.DHIS;
  const { h, icon } = D.ui;

  const DEMO = [["doctor_krh", "Doctor, Kigali"], ["nurse_krh", "Nurse, Kigali"], ["reg_krh", "Registration, Kigali"], ["pharm_krh", "Pharmacist, Kigali"],
    ["lab_krh", "Lab technician, Kigali"], ["manager_krh", "Manager, Kigali"], ["doctor_bdh", "Doctor, Butare"], ["nurse_bdh", "Nurse, Butare"],
    ["reg_bdh", "Registration, Butare"], ["manager_bdh", "Manager, Butare"], ["dpo", "Data protection officer"], ["admin", "System administrator"]];

  function story() {
    const point = (title, text) => h("li", null, icon("check-circle-fill"), h("div", null, h("strong", null, title), h("span", null, text)));
    return h("div", { class: "signin-story" },
      h("div", { class: "brand" }, h("span", { class: "brand-mark" }, icon("plus-lg")), "DHIS"),
      h("h1", null, "Move patients between hospitals without losing their story."),
      h("p", null, "Each hospital keeps its own records. Only what a transfer needs is shared, and only when the receiving hospital accepts."),
      h("ul", { class: "points" },
        point("Registered once", "A national ID can exist at only one hospital at a time."),
        point("Consent first", "A transfer cannot be requested without the patient's consent."),
        point("Every step recorded", "Each action is written to a log that cannot be changed.")));
  }

  D.pages.login = async function (container) {
    const f = D.ui.form([
      { name: "username", label: "Username", required: true, autocomplete: "username" },
      { name: "password", label: "Password", type: "password", required: true, autocomplete: "current-password" },
    ], submit);
    const btn = h("button", { class: "btn primary", type: "submit", style: "width:100%;justify-content:center" }, "Sign in");
    f.el.appendChild(btn);

    async function submit() {
      if (!f.requireFields()) return;
      btn.disabled = true;
      const v = f.values();
      const r = await D.api.post("auth/login/", { username: v.username, password: document.querySelector('input[name="password"]').value });
      if (!r.ok) {
        btn.disabled = false;
        f.showErrors({ error: { message: r.status === 401 ? "Wrong username or password." : r.error.message } });
        return;
      }
      const session = { token: r.data.token, user: r.data.user };
      D.session.set(session);
      const hs = await D.api.get("auth/hospitals/");
      if (hs.ok && session.user.hospital) {
        const mine = hs.data.find((x) => x.code === session.user.hospital);
        if (mine) { session.user.hospital_name = mine.name; D.session.set(session); }
      }
      location.hash = "#/";
      D.render();
    }

    const demo = h("details", { class: "demo-users" }, h("summary", null, "Demo accounts for this training system"),
      h("p", { class: "muted small", style: "margin-top:.6rem" }, "Every demo account uses the password Dhis@Demo2025. Remove these accounts before any real use."),
      D.ui.table([{ label: "Username", render: (r) => h("code", null, r[0]) }, { label: "Role", render: (r) => r[1] }], DEMO));
    container.appendChild(h("div", { class: "signin" }, story(), h("div", { class: "signin-form" }, h("h2", null, "Sign in"), f.el, demo)));
  };
})();
