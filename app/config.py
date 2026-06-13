from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    github_token: str = ""
    github_owner: str = ""
    github_owner_is_org: bool = False
    project_topic: str = "webapp"
    template_repo: str = ""

    dashboard_token: str = ""
    host: str = "127.0.0.1"
    port: int = 8080

    # VPS-Deploy-Secrets, die in jedes neu erstellte Repo injiziert werden
    # (Option 2: Dashboard setzt sie per GitHub Actions Secrets API).
    vps_host: str = ""
    vps_user: str = ""
    vps_port: str = "22"
    vps_ssh_key: str = ""


settings = Settings()
