from functools import lru_cache

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str

    # Auth
    jwt_secret: SecretStr
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # LLM and embeddings (filled in later)
    llm_provider: str = ""
    llm_api_key: SecretStr = SecretStr("")
    embedding_model: str = ""

    # Password for the synthetic demo accounts created by scripts/seed_users.py
    seed_user_password: SecretStr = SecretStr("")

    @field_validator("jwt_secret")
    @classmethod
    def jwt_secret_must_be_strong(cls, v: SecretStr) -> SecretStr:
        secret = v.get_secret_value()
        if secret == "change-me" or len(secret) < 32:
            raise ValueError("JWT_SECRET must be a random value of at least 32 characters")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
