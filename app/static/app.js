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

const LANG_COLORS = {
  "Python": "#3572A5", "JavaScript": "#f1e05a", "TypeScript": "#3178c6",
  "HTML": "#e34c26", "CSS": "#563d7c", "SCSS": "#c6538c",
  "Shell": "#89e051", "Bash": "#89e051", "Go": "#00ADD8",
  "Rust": "#dea584", "Java": "#b07219", "C": "#555555",
  "C++": "#f34b7d", "C#": "#178600", "Ruby": "#701516",
  "PHP": "#4F5D95", "Swift": "#F05138", "Kotlin": "#A97BFF",
  "Dockerfile": "#384d54", "Vue": "#41b883", "Svelte": "#ff3e00",
};

function langColor(name) {
  return LANG_COLORS[name] || "#8b949e";
}

function langBlock(languages) {
  if (!languages || !languages.length) return "";
  const segs = languages
    .map(l => `<div class="lang-seg" style="width:${l.pct}%;background:${langColor(l.name)}" title="${l.name} ${l.pct}%"></div>`)
    .join("");
  const items = languages
    .map(l => `<span class="lang-item"><span class="lang-dot" style="background:${langColor(l.name)}"></span>${l.name}<span class="lang-pct">${l.pct}%</span></span>`)
    .join("");
  return `<div class="card-langs"><div class="lang-bar">${segs}</div><div class="lang-list">${items}</div></div>`;
}

let projects = [];

function headers() {
  const h = { "Content-Type": "application/json" };
  if (window.__DASHBOARD_TOKEN__) h["X-Dashboard-Token"] = window.__DASHBOARD_TOKEN__;
  return h;
}

function fmtDuration(s) {
  if (s == null || s < 0) return "";
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

function ciIcon(status, conclusion, url, durationS) {
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
  const dur = fmtDuration(durationS);
  const badge = `<span class="ci ${cls}" title="${title}">${icon}${dur ? ` <span class="ci-dur">${dur}</span>` : ""}</span>`;
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
        ${langBlock(p.languages)}
        <div class="card-meta">
          ${ciIcon(p.ci_status, p.ci_conclusion, p.ci_url, p.ci_duration_s)}
          <div class="card-dates">
            <span title="Erstellt">⊕ ${fmtDate(p.created_at)}</span>
            <span title="Letzter Commit">${p.commits && p.commits[0] ? `↑ ${fmtDate(p.commits[0].date)}` : ""}</span>
          </div>
        </div>
        <div class="card-links">
          <a class="btn btn-small" href="${p.html_url}" target="_blank" rel="noopener">GitHub ↗</a>
          <a class="btn btn-small" href="/apps/${p.name}/" target="_blank" rel="noopener">App ↗</a>
          <button class="btn btn-small btn-danger" data-name="${escapeHtml(p.name)}" data-full="${escapeHtml(p.full_name)}">✕</button>
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

grid.addEventListener("click", async (e) => {
  const btn = e.target.closest(".btn-danger");
  if (!btn) return;
  const name = btn.dataset.name;
  const full = btn.dataset.full;
  if (!confirm(`Projekt „${name}" wirklich löschen?\n\nDas GitHub-Repo (${full}) und die Server-Dateien werden dauerhaft entfernt. Diese Aktion kann nicht rückgängig gemacht werden.`)) return;
  btn.disabled = true;
  btn.textContent = "…";
  try {
    const res = await fetch(`/api/projects/${encodeURIComponent(name)}`, {
      method: "DELETE",
      headers: headers(),
    });
    const data = await res.json();
    if (!res.ok) {
      alert("Fehler beim Löschen: " + (data.detail || res.statusText));
      btn.disabled = false;
      btn.textContent = "✕";
      return;
    }
    if (data.warnings && data.warnings.length) {
      alert("Gelöscht ✓\n\n⚠ Server-Cleanup:\n" + data.warnings.join("\n"));
    }
    await load();
  } catch (err) {
    alert("Fehler: " + err.message);
    btn.disabled = false;
    btn.textContent = "✕";
  }
});

search.oninput = applyFilter;
document.getElementById("reload").onclick = load;

load();
