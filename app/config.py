from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Real environment variables win over .env. In k8s they come from a ConfigMap/Secret.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # No default on purpose: a missing Secret must stop startup, not fall back to a throwaway DB.
    database_url: str

    log_level: str = "INFO"


settings = Settings()
