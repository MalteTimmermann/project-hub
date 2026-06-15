"""Schlanker Wrapper um die GitHub REST API (nur was das Dashboard braucht)."""
from __future__ import annotations

import asyncio
from base64 import b64encode

import httpx
from nacl import encoding, public

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
            return {
                "status": r.get("status"),
                "conclusion": r.get("conclusion"),
                "url": r.get("html_url"),
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
                "language": r.get("language") or "",  # kept for search/filter compat
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
        else:
            p["ci_status"] = None
            p["ci_conclusion"] = None
            p["ci_url"] = None
        p["commits"] = commits if isinstance(commits, list) else []
        p["languages"] = langs if isinstance(langs, list) else []

    return projects


def _encrypt_secret(public_key: str, value: str) -> str:
    """Wert mit dem Repo-Public-Key (libsodium sealed box) verschluesseln."""
    pk = public.PublicKey(public_key.encode(), encoding.Base64Encoder())
    sealed = public.SealedBox(pk)
    return b64encode(sealed.encrypt(value.encode())).decode()


async def set_deploy_secrets(full_name: str) -> list[str]:
    """VPS_*-Secrets in das neue Repo schreiben. Gibt Warnungen zurueck."""
    secrets = {
        "VPS_HOST": settings.vps_host,
        "VPS_USER": settings.vps_user,
        "VPS_PORT": settings.vps_port,
        "VPS_SSH_KEY": settings.vps_ssh_key,
    }
    missing = [k for k, v in secrets.items() if not v]
    if missing:
        return [f"Secrets nicht gesetzt (in .env leer): {', '.join(missing)}"]

    # Public Key des Repos holen (zum Verschluesseln)
    pk_resp = await _request("GET", f"/repos/{full_name}/actions/secrets/public-key")
    pk = pk_resp.json()

    warnings: list[str] = []
    for name, value in secrets.items():
        try:
            await _request(
                "PUT",
                f"/repos/{full_name}/actions/secrets/{name}",
                json={
                    "encrypted_value": _encrypt_secret(pk["key"], value),
                    "key_id": pk["key_id"],
                },
            )
        except GitHubError as e:
            warnings.append(f"{name}: {e.message}")
    return warnings


async def create_project(name: str, description: str = "", private: bool = True) -> dict:
    """Neues Repo aus dem Template generieren, Topic + VPS-Deploy-Secrets setzen."""
    if not settings.template_repo:
        raise GitHubError(400, "TEMPLATE_REPO ist nicht konfiguriert.")

    template_owner, template_name = settings.template_repo.split("/", 1)

    payload = {
        "owner": settings.github_owner,
        "name": name,
        "description": description,
        "private": private,
        "include_all_branches": False,
    }
    resp = await _request(
        "POST",
        f"/repos/{template_owner}/{template_name}/generate",
        json=payload,
    )
    repo = resp.json()

    # Topic setzen, damit das Projekt im Dashboard auftaucht
    topic = settings.project_topic.strip()
    if topic:
        try:
            await _request(
                "PUT",
                f"/repos/{repo['full_name']}/topics",
                json={"names": [topic]},
            )
        except GitHubError:
            pass  # nicht kritisch fuers Anlegen

    # VPS-Deploy-Secrets injizieren (Option 2)
    secret_warnings = await set_deploy_secrets(repo["full_name"])

    return {
        "name": repo["name"],
        "full_name": repo["full_name"],
        "html_url": repo["html_url"],
        "private": repo.get("private", True),
        "secrets_set": not secret_warnings,
        "warnings": secret_warnings,
    }
