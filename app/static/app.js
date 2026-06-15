const grid = document.getElementById("grid");
const statusEl = document.getElementById("status");
const search = document.getElementById("search");
const modal = document.getElementById("modal");
const formStatus = document.getElementById("form-status");
const themeToggle = document.getElementById("theme-toggle");

function applyTheme(isDark) {
  if (isDark) {
    document.documentElement.removeAttribute("data-theme");
    if (themeToggle) themeToggle.textContent = "☀";
  } else {
    document.documentElement.dataset.theme = "light";
    if (themeToggle) themeToggle.textContent = "🌙";
  }
  localStorage.setItem("theme", isDark ? "dark" : "light");
}

if (themeToggle) {
  themeToggle.onclick = () => applyTheme(document.documentElement.dataset.theme === "light");
}

const savedTheme = localStorage.getItem("theme");
applyTheme(savedTheme !== "light");

let projects = [];

function headers() {
  const h = { "Content-Type": "application/json" };
  if (window.__DASHBOARD_TOKEN__) h["X-Dashboard-Token"] = window.__DASHBOARD_TOKEN__;
  return h;
}

function ciIcon(status, conclusion, url) {
  let icon, cls, title;
  if (!status) return "";
  if (status === "in_progress") {
    icon = "●"; cls = "ci-running"; title = "Läuft…";
  } else if (status !== "completed") {
    icon = "○"; cls = "ci-queued"; title = "Wartend";
  } else {
    switch (conclusion) {
      case "success":   icon = "✓"; cls = "ci-success";   title = "Erfolgreich"; break;
      case "failure":   icon = "✗"; cls = "ci-failure";   title = "Fehlgeschlagen"; break;
      case "cancelled": icon = "○"; cls = "ci-cancelled"; title = "Abgebrochen"; break;
      default:          icon = "?"; cls = "ci-unknown";   title = conclusion || status;
    }
  }
  const badge = `<span class="ci ${cls}" title="${title}">${icon}</span>`;
  return url
    ? `<a href="${url}" target="_blank" rel="noopener" class="ci-link">${badge}</a>`
    : badge;
}

function escapeHtml(str) {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function fmtDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString("de-DE", { day: "2-digit", month: "short", year: "numeric" });
}

function render(list) {
  grid.innerHTML = "";
  if (!list.length) {
    grid.innerHTML = '<div class="empty">Noch keine Projekte. Lege oben rechts dein erstes an.</div>';
    return;
  }
  for (const p of list) {
    const row = document.createElement("div");
    row.className = "project-row";
    row.innerHTML = `
      <div class="project-info">
        <div class="card-head">
          <span class="card-name">${p.name}</span>
          <span class="badge">${p.private ? "privat" : "public"}</span>
        </div>
        <div class="card-desc">${p.description || ""}</div>
        <div class="card-meta">
          <span>${p.language ? `<span class="dot"></span>${p.language}` : ""}</span>
          <span>${fmtDate(p.updated_at)}</span>
          ${ciIcon(p.ci_status, p.ci_conclusion, p.ci_url)}
        </div>
        <div class="card-links">
          <a class="btn btn-small" href="${p.html_url}" target="_blank" rel="noopener">GitHub ↗</a>
          <a class="btn btn-small" href="/apps/${p.name}/" target="_blank" rel="noopener">App ↗</a>
        </div>
        <div class="commits">${(p.commits || []).map(c => `
          <a class="commit" href="${c.url}" target="_blank" rel="noopener">
            <code class="commit-sha">${c.sha}</code>
            <span class="commit-msg">${escapeHtml(c.message)}</span>
          </a>`).join("")}
        </div>
      </div>
      <div class="project-preview">
        <iframe src="/apps/${p.name}/" loading="lazy" title="${p.name}"></iframe>
      </div>`;
    grid.appendChild(row);
  }
}

function applyFilter() {
  const q = search.value.toLowerCase().trim();
  render(q ? projects.filter((p) =>
    (p.name + " " + p.description).toLowerCase().includes(q)) : projects);
}

async function load() {
  statusEl.textContent = "Lade Projekte…";
  statusEl.className = "status";
  try {
    const res = await fetch("/api/projects", { headers: headers() });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Fehler beim Laden");
    projects = data;
    statusEl.textContent = `${projects.length} Projekt(e)`;
    applyFilter();
  } catch (e) {
    statusEl.textContent = "Fehler: " + e.message;
    statusEl.className = "status error";
  }
}

// --- Modal: Neues Projekt ---
document.getElementById("new-btn").onclick = () => {
  formStatus.textContent = "";
  modal.classList.remove("hidden");
  document.getElementById("p-name").focus();
};
document.getElementById("cancel").onclick = () => modal.classList.add("hidden");
modal.onclick = (e) => { if (e.target === modal) modal.classList.add("hidden"); };

document.getElementById("new-form").onsubmit = async (e) => {
  e.preventDefault();
  const btn = e.submitter;
  btn.disabled = true;
  formStatus.className = "form-status";
  formStatus.textContent = "Lege Repo an…";
  try {
    const body = {
      name: document.getElementById("p-name").value,
      description: document.getElementById("p-desc").value,
      private: document.getElementById("p-private").checked,
    };
    const res = await fetch("/api/projects", {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Fehler beim Anlegen");
    formStatus.className = "form-status ok";
    let msg = `✓ Angelegt: <a href="${data.html_url}" target="_blank" rel="noopener">${data.full_name}</a>`;
    if (data.warnings && data.warnings.length) {
      msg += `<br><span style="color:#d29922">⚠ Secrets: ${data.warnings.join("; ")}</span>`;
    }
    formStatus.innerHTML = msg;
    document.getElementById("new-form").reset();
    document.getElementById("p-private").checked = true;
    await load();
  } catch (err) {
    formStatus.className = "form-status error";
    formStatus.textContent = "Fehler: " + err.message;
  } finally {
    btn.disabled = false;
  }
};

search.oninput = applyFilter;
document.getElementById("reload").onclick = load;

load();
