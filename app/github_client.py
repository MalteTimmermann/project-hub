"""Schlanker Wrapper um die GitHub REST API (nur was das Dashboard braucht)."""
from __future__ import annotations

import asyncio
import os
import shlex
import tempfile
from datetime import datetime

import httpx

from .config import settings

API = "https://api.github.com"


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


class GitHubError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(f"GitHub {status}: {message}")


async def _request(method: str, path: str, **kwargs) -> httpx.Response:
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.request(method, f"{API}{path}", headers=_headers(), **kwargs)
    if resp.status_code >= 400:
        try:
            msg = resp.json().get("message", resp.text)
        except Exception:
            msg = resp.text
        raise GitHubError(resp.status_code, msg)
    return resp


async def get_languages(full_name: str) -> list[dict]:
    try:
        resp = await _request("GET", f"/repos/{full_name}/languages")
        data = resp.json()
        total = sum(data.values())
        if not total:
            return []
        return [
            {"name": lang, "pct": round(bytes_ / total * 100, 1)}
            for lang, bytes_ in sorted(data.items(), key=lambda x: -x[1])
        ]
    except GitHubError:
        return []


async def get_recent_commits(full_name: str) -> list[dict]:
    try:
        resp = await _request("GET", f"/repos/{full_name}/commits?per_page=2")
        commits = []
        for c in resp.json():
            commits.append({
                "sha": c["sha"][:7],
                "message": c["commit"]["message"].split("\n")[0],
                "author": c["commit"]["author"]["name"],
                "date": c["commit"]["author"]["date"],
                "url": c["html_url"],
            })
        return commits
    except GitHubError:
        return []


async def get_latest_run(full_name: str) -> dict | None:
    try:
        resp = await _request("GET", f"/repos/{full_name}/actions/runs?per_page=1")
        runs = resp.json().get("workflow_runs", [])
        if runs:
            r = runs[0]
            duration_s = None
            started = r.get("run_started_at")
            ended = r.get("updated_at")
            if started and ended:
                fmt = "%Y-%m-%dT%H:%M:%SZ"
                try:
                    delta = datetime.strptime(ended, fmt) - datetime.strptime(started, fmt)
                    duration_s = int(delta.total_seconds())
                except ValueError:
                    pass
            return {
                "status": r.get("status"),
                "conclusion": r.get("conclusion"),
                "url": r.get("html_url"),
                "duration_s": duration_s,
            }
    except GitHubError:
        pass
    return None


async def list_projects() -> list[dict]:
    """Repos des Owners listen, optional nach Topic gefiltert."""
    owner = settings.github_owner
    if settings.github_owner_is_org:
        path = f"/orgs/{owner}/repos?per_page=100&sort=pushed"
    else:
        path = "/user/repos?per_page=100&sort=pushed&affiliation=owner"

    resp = await _request("GET", path)
    repos = resp.json()

    topic = settings.project_topic.strip()
    projects = []
    for r in repos:
        if r.get("archived"):
            continue
        if topic and topic not in (r.get("topics") or []):
            continue
        projects.append(
            {
                "name": r["name"],
                "full_name": r["full_name"],
                "description": r.get("description") or "",
                "html_url": r["html_url"],
                "homepage": r.get("homepage") or "",
                "language": r.get("language") or "",
                "topics": r.get("topics") or [],
                "created_at": r.get("created_at") or "",
                "updated_at": r.get("pushed_at") or r.get("updated_at"),
                "private": r.get("private", False),
            }
        )

    n = len(projects)
    results = await asyncio.gather(
        *[get_latest_run(p["full_name"]) for p in projects],
        *[get_recent_commits(p["full_name"]) for p in projects],
        *[get_languages(p["full_name"]) for p in projects],
        return_exceptions=True,
    )
    ci_results = results[:n]
    commit_results = results[n : 2 * n]
    lang_results = results[2 * n :]

    for p, ci, commits, langs in zip(projects, ci_results, commit_results, lang_results):
        if isinstance(ci, dict):
            p["ci_status"] = ci.get("status")
            p["ci_conclusion"] = ci.get("conclusion")
            p["ci_url"] = ci.get("url")
            p["ci_duration_s"] = ci.get("duration_s")
        else:
            p["ci_status"] = None
            p["ci_conclusion"] = None
            p["ci_url"] = None
            p["ci_duration_s"] = None
        p["commits"] = commits if isinstance(commits, list) else []
        p["languages"] = langs if isinstance(langs, list) else []

    return projects


async def _vps_ssh(cmds: str, timeout: int = 120) -> list[str]:
    """Führt Shell-Befehle via SSH auf dem VPS aus (über host.docker.internal)."""
    if not all([settings.vps_user, settings.vps_ssh_key]):
        return ["VPS-Zugangsdaten nicht konfiguriert — Schritt übersprungen."]

    key_content = settings.vps_ssh_key.replace("\\n", "\n")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".key", delete=False) as f:
        f.write(key_content)
        key_file = f.name

    try:
        os.chmod(key_file, 0o600)
        proc = await asyncio.create_subprocess_exec(
            "ssh",
            "-i", key_file,
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=10",
            "-p", settings.vps_port or "22",
            f"{settings.vps_user}@{settings.vps_internal_host}",
            f"bash -c {shlex.quote(cmds)}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        if proc.returncode != 0:
            return [f"VPS-Fehler: {stderr.decode().strip()[:300]}"]
        return []
    except asyncio.TimeoutError:
        return [f"VPS-Timeout (>{timeout}s)."]
    except Exception as e:
        return [f"VPS-SSH fehlgeschlagen: {e}"]
    finally:
        os.unlink(key_file)


async def _get_runner_token(full_name: str) -> str | None:
    try:
        resp = await _request("POST", f"/repos/{full_name}/actions/runners/registration-token")
        return resp.json()["token"]
    except GitHubError:
        return None


async def _setup_vps(name: str, full_name: str) -> list[str]:
    """Klont Repo, vergibt Port, öffnet UFW und registriert GitHub Actions Runner."""
    runner_token = await _get_runner_token(full_name)
    if not runner_token:
        return ["Runner-Token konnte nicht von GitHub abgerufen werden."]

    github_url = f"https://github.com/{full_name}"
    n = shlex.quote(name)

    cmds = f"""
set -e

# Repo klonen
git clone {shlex.quote(github_url)} /opt/{n}
chown -R github-runner:github-runner /opt/{n}

# Nächsten freien Port ermitteln (startet bei 8081)
PORT=$(cat /opt/.next-port 2>/dev/null || echo 8081)
echo $((PORT + 1)) > /opt/.next-port

# .env anlegen
echo "APP_PORT=$PORT" > /opt/{n}/.env

# Port in UFW freigeben
ufw allow "$PORT/tcp"

# Runner-Binary herunterladen
mkdir -p /opt/actions-runner-{n}
cd /opt/actions-runner-{n}
RUNNER_URL=$(curl -fsSL https://api.github.com/repos/actions/runner/releases/latest \
  | grep -oP '"browser_download_url": "\\K[^"]*linux-x64[^"]*\\.tar\\.gz')
curl -fsSL -o runner.tar.gz "$RUNNER_URL"
tar xzf runner.tar.gz
rm runner.tar.gz
chown -R github-runner:github-runner /opt/actions-runner-{n}

# Runner konfigurieren
su - github-runner -c "cd /opt/actions-runner-{n} && ./config.sh \\
  --url {shlex.quote(github_url)} \\
  --token {shlex.quote(runner_token)} \\
  --name {n} \\
  --unattended --replace"

# Als Systemdienst starten
/opt/actions-runner-{n}/svc.sh install github-runner
/opt/actions-runner-{n}/svc.sh start
"""

    return await _vps_ssh(cmds, timeout=180)


async def delete_project(full_name: str) -> None:
    """Löscht das GitHub-Repo dauerhaft."""
    await _request("DELETE", f"/repos/{full_name}")


async def cleanup_vps(name: str) -> list[str]:
    """Stoppt Container und Runner, entfernt nginx-Config und Verzeichnisse."""
    n = shlex.quote(name)
    cmds = f"""
# Docker Container stoppen
[ -d /opt/{n} ] && cd /opt/{n} && docker compose down 2>/dev/null || true

# Runner-Service stoppen und deinstallieren
if [ -d /opt/actions-runner-{n} ]; then
    /opt/actions-runner-{n}/svc.sh stop 2>/dev/null || true
    /opt/actions-runner-{n}/svc.sh uninstall 2>/dev/null || true
fi

# nginx-Config entfernen
rm -f /etc/nginx/sites-available/{n} /etc/nginx/sites-enabled/{n}
nginx -s reload 2>/dev/null || true

# UFW-Port schließen (Port aus .env lesen)
PORT=$(grep APP_PORT /opt/{n}/.env 2>/dev/null | cut -d= -f2)
[ -n "$PORT" ] && ufw delete allow "$PORT/tcp" 2>/dev/null || true

# Verzeichnisse löschen
rm -rf /opt/{n} /opt/actions-runner-{n}
"""
    return await _vps_ssh(cmds)


async def create_project(name: str, description: str = "", private: bool = True) -> dict:
    """Neues Repo aus Template anlegen und VPS vollständig automatisch einrichten."""
    if not settings.template_repo:
        raise GitHubError(400, "TEMPLATE_REPO ist nicht konfiguriert.")

    template_owner, template_name = settings.template_repo.split("/", 1)

    resp = await _request(
        "POST",
        f"/repos/{template_owner}/{template_name}/generate",
        json={
            "owner": settings.github_owner,
            "name": name,
            "description": description,
            "private": private,
            "include_all_branches": False,
        },
    )
    repo = resp.json()

    # Topic setzen, damit Projekt im Dashboard erscheint
    topic = settings.project_topic.strip()
    if topic:
        try:
            await _request(
                "PUT",
                f"/repos/{repo['full_name']}/topics",
                json={"names": [topic]},
            )
        except GitHubError:
            pass

    # VPS automatisch einrichten
    warnings = await _setup_vps(name, repo["full_name"])

    return {
        "name": repo["name"],
        "full_name": repo["full_name"],
        "html_url": repo["html_url"],
        "private": repo.get("private", True),
        "warnings": warnings,
    }
