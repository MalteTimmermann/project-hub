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

    vps_user: str = ""
    vps_port: str = "22"
    vps_ssh_key: str = ""
    # Interner SSH-Host: Container → VPS-Host (über Docker bridge)
    vps_internal_host: str = "host.docker.internal"


settings = Settings()
