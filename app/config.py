from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    #In k8s they come from a ConfigMap/Secret.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # No default on purpose: a missing Secret must stop startup, not fall back to a throwaway DB.
    database_url: str

    log_level: str = "INFO"

    # The image tag, set by the Helm chart. Shown in the UI so a rollout is visible.
    app_version: str = "dev"

    host: str = "0.0.0.0"
    port: int = 8000
    # Seconds uvicorn waits for in-flight requests on SIGTERM; must stay below the pod's
    # terminationGracePeriodSeconds (30) minus the preStop sleep (5).
    graceful_shutdown_seconds: int = 20
    # Local development only: restart on code changes. Off in the image.
    reload: bool = False


settings = Settings()
