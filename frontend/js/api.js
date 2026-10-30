/* API helper: every request to the gateway goes through here.
   Owner: Patrick (shared core). */
(function () {
  const D = (window.DHIS = window.DHIS || { pages: {} });
  const KEY = "dhis.session";

  D.session = {
    get() { try { return JSON.parse(sessionStorage.getItem(KEY)); } catch (e) { return null; } },
    set(value) { try { sessionStorage.setItem(KEY, JSON.stringify(value)); } catch (e) { /* private mode */ } },
    clear() { try { sessionStorage.removeItem(KEY); } catch (e) { /* ignore */ } },
  };

  async function request(method, path, opts) {
    opts = opts || {};
    const headers = { Accept: "application/json" };
    const session = D.session.get();
    if (session) headers.Authorization = "Bearer " + session.token;
    if (opts.body !== undefined) headers["Content-Type"] = "application/json";
    // A new key for each user action makes a retried write safe: the server returns the first answer.
    if (opts.idempotent) headers["Idempotency-Key"] = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random());
    let res;
    try {
      res = await fetch("/api/" + path, { method, headers, body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined });
    } catch (e) {
      return { ok: false, status: 0, data: null, error: { code: "network", message: "Cannot reach the server. Check your connection and try again." } };
    }
    let data = null;
    try { data = await res.json(); } catch (e) { /* empty body */ }
    if (res.status === 401 && path !== "auth/login/") {
      D.session.clear();
      location.hash = "#/login";
    }
    return { ok: res.ok, status: res.status, data, error: data && data.error ? data.error : (res.ok ? null : { code: "http_" + res.status, message: "Something went wrong (code " + res.status + ")." }) };
  }

  D.api = {
    get: (path) => request("GET", path),
    post: (path, body, opts) => request("POST", path, Object.assign({ body: body === undefined ? {} : body }, opts)),
    patch: (path, body) => request("PATCH", path, { body }),
    del: (path) => request("DELETE", path),
  };
})();
