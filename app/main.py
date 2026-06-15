import re
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

from .config import settings
from .github_client import GitHubError, cleanup_vps, create_project, delete_project, list_projects

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Project Hub", version="1.0.0")


def _check_auth(token: str | None) -> None:
    """Optionaler simpler Schutz via X-Dashboard-Token Header."""
    if settings.dashboard_token and token != settings.dashboard_token:
        raise HTTPException(status_code=401, detail="Nicht autorisiert.")


_NAME_RE = re.compile(r"^[a-zA-Z0-9._-]+$")


class NewProject(BaseModel):
    name: str
    description: str = ""
    private: bool = True

    @field_validator("name")
    @classmethod
    def valid_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name darf nicht leer sein.")
        if not all(c.isalnum() or c in "-_." for c in v):
            raise ValueError("Nur Buchstaben, Zahlen, - _ . erlaubt.")
        return v


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "owner": settings.github_owner,
        "token_configured": bool(settings.github_token),
        "template_configured": bool(settings.template_repo),
    }


@app.get("/api/projects")
async def get_projects(x_dashboard_token: str | None = Header(default=None)):
    _check_auth(x_dashboard_token)
    try:
        return await list_projects()
    except GitHubError as e:
        return JSONResponse(status_code=e.status, content={"detail": e.message})


@app.post("/api/projects")
async def post_project(
    body: NewProject, x_dashboard_token: str | None = Header(default=None)
):
    _check_auth(x_dashboard_token)
    try:
        repo = await create_project(body.name, body.description, body.private)
        return JSONResponse(status_code=201, content=repo)
    except GitHubError as e:
        return JSONResponse(status_code=e.status, content={"detail": e.message})


@app.delete("/api/projects/{name}")
async def del_project(
    name: str, x_dashboard_token: str | None = Header(default=None)
):
    _check_auth(x_dashboard_token)
    if not _NAME_RE.fullmatch(name):
        raise HTTPException(status_code=400, detail="Ungültiger Projektname.")
    full_name = f"{settings.github_owner}/{name}"
    try:
        await delete_project(full_name)
    except GitHubError as e:
        return JSONResponse(status_code=e.status, content={"detail": e.message})
    warnings = await cleanup_vps(name)
    return JSONResponse(content={"deleted": name, "warnings": warnings})


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
