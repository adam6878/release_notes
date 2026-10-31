from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    #In k8s they come from a ConfigMap/Secret.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str

    log_level: str = "INFO"

    app_version: str = "dev"

    host: str = "0.0.0.0"
    port: int = 8000

    graceful_shutdown_seconds: int = 20
    
    reload: bool = False


settings = Settings()
