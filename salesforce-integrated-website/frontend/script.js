const API_BASE = "http://127.0.0.1:8000/api";

async function apiRequest(path, options = {}) {
  const response = await fetch(API_BASE + path, {
    ...options,
    credentials: "include",
    headers: { ...(options.body ? {"Content-Type":"application/json"} : {}), ...(options.headers || {}) }
  });
  let data = {};
  try { data = await response.json(); } catch (_) {}
  if (!response.ok) throw new Error(data.detail || data.message || "Request failed");
  return data;
}
function showMessage(id, text, type = "") {
  const el = document.getElementById(id);
  if (el) { el.textContent = text; el.className = "message " + type; }
}

document.addEventListener("DOMContentLoaded", () => {
  // All main sections, including FAQ, live inside index.html.
  function showView(name) {
    document.querySelectorAll(".view").forEach(view => {
      view.classList.toggle("active-view", view.id === `view-${name}`);
    });
    document.querySelectorAll(".nav-link[data-view]").forEach(button => {
      button.classList.toggle("active", button.dataset.view === name);
    });
    if (name === "faq" && !window.faqsLoaded) loadFAQs();
    if (name === "admin") loadAdminQueries();
    window.scrollTo({top: 0, behavior: "smooth"});
  }
  const initialHash = window.location.hash.replace("#", "");
  if (["home", "faq", "accounts", "tasks", "reports", "dashboards", "admin", "login"].includes(initialHash)) {
    showView(initialHash);
  }
  window.addEventListener("hashchange", () => {
    const requested = window.location.hash.replace("#", "");
    if (["home", "faq", "accounts", "tasks", "reports", "dashboards", "admin", "login"].includes(requested)) showView(requested);
  });

  document.querySelectorAll("[data-view]").forEach(button => {
    button.addEventListener("click", event => {
      event.preventDefault();
      showView(button.dataset.view);
    });
  });
  document.querySelectorAll('a[href="#home"]').forEach(link => {
    link.addEventListener("click", event => { event.preventDefault(); showView("home"); });
  });

  const globalSearch = document.getElementById("global-search");
  globalSearch?.addEventListener("keydown", event => {
    if (event.key === "Enter") {
      const faqSearch = document.getElementById("faq-search");
      if (faqSearch) faqSearch.value = globalSearch.value;
      showView("faq");
      if (window.faqsLoaded) faqSearch?.dispatchEvent(new Event("input"));
    }
  });

  const supportForm = document.getElementById("support-form");
  supportForm?.addEventListener("submit", async event => {
    event.preventDefault();
    const submitButton = document.getElementById("support-submit");
    const status = document.getElementById("support-message-status");
    if (status) { status.textContent = "Submitting your query…"; status.className = "message"; }
    if (submitButton) submitButton.disabled = true;
    try {
      const result = await apiRequest("/queries", { method: "POST", body: JSON.stringify({
        name: document.getElementById("support-name").value.trim(),
        email: document.getElementById("support-email").value.trim(),
        phone: document.getElementById("support-phone").value.trim(),
        message: document.getElementById("support-message").value.trim()
      })});
      if (status) { status.textContent = `Success: your query was saved (Query ID ${result.query.id}).`; status.className = "message success"; }
      supportForm.reset();
    } catch (err) {
      if (status) { status.textContent = `Could not submit query: ${err.message}`; status.className = "message error"; }
    } finally {
      if (submitButton) submitButton.disabled = false;
    }
  });

  const loginForm = document.getElementById("login-form");
  const registerForm = document.getElementById("register-form");
  document.getElementById("show-register")?.addEventListener("click", () => {
    loginForm?.classList.add("hidden"); registerForm?.classList.remove("hidden");
  });
  document.getElementById("show-login")?.addEventListener("click", () => {
    registerForm?.classList.add("hidden"); loginForm?.classList.remove("hidden");
  });
  loginForm?.addEventListener("submit", async event => {
    event.preventDefault(); showMessage("login-message", "Signing in…");
    try {
      await apiRequest("/auth/login", {method:"POST", body:JSON.stringify({
        email:document.getElementById("login-email").value.trim(),
        password:document.getElementById("login-password").value
      })});
      showMessage("login-message", "Login successful!", "success");
      setTimeout(() => showView("home"), 500);
    } catch (err) { showMessage("login-message", err.message, "error"); }
  });
  registerForm?.addEventListener("submit", async event => {
    event.preventDefault(); showMessage("register-message", "Creating account…");
    try {
      await apiRequest("/auth/register", {method:"POST", body:JSON.stringify({
        name:document.getElementById("register-name").value.trim(),
        email:document.getElementById("register-email").value.trim(),
        password:document.getElementById("register-password").value
      })});
      showMessage("register-message", "Registration successful!", "success");
      setTimeout(() => showView("home"), 500);
    } catch (err) { showMessage("register-message", err.message, "error"); }
  });
});

async function loadFAQs() {
  const list = document.getElementById("faq-list");
  const status = document.getElementById("faq-status");
  const errorBox = document.getElementById("faq-error");
  const empty = document.getElementById("faq-empty");
  const search = document.getElementById("faq-search");
  const category = document.getElementById("faq-category");
  if (!list || !status || !search || !category) return;
  let faqs = [];
  function render() {
    const term = search.value.trim().toLowerCase(), cat = category.value;
    const found = faqs.filter(f => (!cat || String(f.category || "") === cat) &&
      (!term || String(f.question || "").toLowerCase().includes(term) || String(f.answer || "").toLowerCase().includes(term)));
    list.replaceChildren();
    found.forEach(f => {
      const item = document.createElement("article"); item.className = "faq-item";
      const q = document.createElement("h3"); q.textContent = f.question || "Untitled question";
      const a = document.createElement("p"); a.textContent = f.answer || "No answer provided.";
      item.append(q, a);
      if (f.category) { const badge = document.createElement("span"); badge.className = "badge"; badge.textContent = f.category; item.append(badge); }
      list.append(item);
    });
    if (empty) empty.classList.toggle("hidden", found.length !== 0);
    status.textContent = `${found.length} FAQ(s) found`;
  }
  try {
    const response = await fetch(API_BASE + "/faqs");
    if (!response.ok) throw new Error("API returned " + response.status);
    faqs = await response.json();
    window.faqsLoaded = true;
    const count = document.getElementById("faq-count");
    if (count) count.textContent = String(faqs.length);
    [...new Set(faqs.map(f => String(f.category || "")).filter(Boolean))].sort().forEach(c => {
      const option = document.createElement("option"); option.value = c; option.textContent = c; category.append(option);
    });
    if (errorBox) errorBox.classList.add("hidden");
    render();
  } catch (err) {
    status.textContent = "FAQ service is unavailable.";
    errorBox?.classList.remove("hidden");
    console.error("FAQ API error:", err);
  }
  search.addEventListener("input", render);
  category.addEventListener("change", render);
  document.getElementById("clear-search")?.addEventListener("click", () => {
    search.value = ""; category.value = ""; render();
  });
}


async function loadAdminQueries() {
  const tbody = document.getElementById("admin-query-rows");
  const statusLine = document.getElementById("admin-query-status");
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="6">Loading support queries…</td></tr>';
  if (statusLine) statusLine.textContent = "Loading…";
  try {
    const response = await fetch(API_BASE + "/queries");
    let queries = await response.json();
    if (!response.ok) throw new Error(queries.detail || "Could not load queries.");
    queries = Array.isArray(queries) ? queries : [];
    const count = status => queries.filter(q => String(q.status || "Open").toLowerCase() === status.toLowerCase()).length;
    document.getElementById("admin-open-count").textContent = count("Open");
    document.getElementById("admin-progress-count").textContent = count("In Progress");
    document.getElementById("admin-resolved-count").textContent = count("Resolved");
    document.getElementById("admin-total-count").textContent = queries.length;

    const search = document.getElementById("admin-search");
    const filter = document.getElementById("admin-status-filter");
    const render = () => {
      const term = (search?.value || "").trim().toLowerCase();
      const selectedStatus = filter?.value || "";
      const filtered = queries.filter(q => {
        const status = String(q.status || "Open");
        const text = [q.id, q.name, q.email, q.message, q.phone, q.created_at].join(" ").toLowerCase();
        return (!term || text.includes(term)) && (!selectedStatus || status === selectedStatus);
      });
      tbody.replaceChildren();
      if (!filtered.length) {
        const tr = document.createElement("tr"), td = document.createElement("td");
        td.colSpan = 6; td.className = "table-empty"; td.textContent = "No matching support queries.";
        tr.append(td); tbody.append(tr);
      }
      filtered.forEach(q => {
        const tr = document.createElement("tr");
        const addText = value => { const td = document.createElement("td"); td.textContent = value == null ? "" : String(value); tr.append(td); };
        addText("#" + q.id);
        addText(q.name || "—");
        const contact = document.createElement("td");
        const email = document.createElement("a");
        email.href = "mailto:" + String(q.email || "");
        email.textContent = String(q.email || "No email");
        contact.append(email);
        if (q.phone) { const phone = document.createElement("div"); phone.className = "query-phone"; phone.textContent = q.phone; contact.append(phone); }
        tr.append(contact);
        const message = document.createElement("td"); message.className = "query-message"; message.textContent = q.message || ""; tr.append(message);
        addText(q.created_at || "—");
        const statusCell = document.createElement("td");
        const select = document.createElement("select");
        select.className = "query-status-select";
        select.setAttribute("aria-label", "Update status for query " + q.id);
        ["Open", "In Progress", "Resolved"].forEach(s => {
          const option = document.createElement("option"); option.value = s; option.textContent = s;
          if (String(q.status || "Open") === s) option.selected = true;
          select.append(option);
        });
        select.addEventListener("change", async () => {
          select.disabled = true;
          const messageBox = document.getElementById("admin-message");
          messageBox.textContent = "Saving status for query #" + q.id + "…";
          messageBox.className = "message";
          try {
            const result = await apiRequest("/queries/" + encodeURIComponent(q.id) + "/status", {
              method: "PATCH", body: JSON.stringify({status: select.value})
            });
            q.status = result.query.status;
            messageBox.textContent = "Query #" + q.id + " updated to " + q.status + ".";
            messageBox.className = "message success";
            document.getElementById("admin-open-count").textContent = count("Open");
            document.getElementById("admin-progress-count").textContent = count("In Progress");
            document.getElementById("admin-resolved-count").textContent = count("Resolved");
            render();
          } catch (err) {
            messageBox.textContent = "Could not update status: " + err.message;
            messageBox.className = "message error";
            select.value = q.status || "Open";
          } finally { select.disabled = false; }
        });
        statusCell.append(select); tr.append(statusCell);
        tbody.append(tr);
      });
      if (statusLine) statusLine.textContent = `${filtered.length} of ${queries.length} queries`;
    };
    search?.removeEventListener("input", window.__adminQueryRender);
    filter?.removeEventListener("change", window.__adminQueryRender);
    window.__adminQueryRender = render;
    search?.addEventListener("input", render);
    filter?.addEventListener("change", render);
    render();
    document.getElementById("admin-message").textContent = "";
  } catch (err) {
    tbody.innerHTML = '<tr><td colspan="6">Could not load support queries. Check that the backend is running.</td></tr>';
    if (statusLine) statusLine.textContent = "API unavailable";
    const messageBox = document.getElementById("admin-message");
    if (messageBox) { messageBox.textContent = err.message; messageBox.className = "message error"; }
  }
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("admin-refresh")?.addEventListener("click", loadAdminQueries);
});
