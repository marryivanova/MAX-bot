from functools import lru_cache
from os import path

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class MaxSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="MAX_",
        extra="ignore",
    )
    secret: str = Field(default="", env="MAX_SECRET")
    domain: str = Field(default="", env="MAX_DOMAIN")
    name: str = Field(default="", env="MAX_NAME")


class BitrixSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    client_id: str = Field(default="", env="")
    client_secret: str = Field(default="", env="")
    domain: str = Field(default="", env="")
    webhook_ol: str = Field("", env="")


class BitrixBots(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    bx_domain: str = Field("", env="")
    max_token: str = Field("", env="")
    max_id: str = Field("", env="")


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    debug: bool = Field(default=False)
    host: str = Field(default="")
    port: int = Field(default=8000)
    nginx_conf_filename: str = Field(default="")
    environment: str = Field(default="production")


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="MYSQL_",
        extra="ignore",
    )
    database: str = Field("", env="MYSQL_DB")
    host: str = Field("", env="MYSQL_HOST")
    user: str = Field("", env="MYSQL_LOGIN")
    password: str = Field("", env="MYSQL_PASSWORD")


class DatabaseBXSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="DB_",
        extra="ignore",
    )
    database: str = Field("", env="DB_NAME")
    host: str = Field("", env="DB_HOST")
    user: str = Field("", env="DB_USER")
    password: str = Field("", env="DB_PASSWORD")


class GDriveSettings(BaseSettings):
    credentials: str = path.join(path.dirname(__file__), "tokens", "credentials_gdrive.json")
    token: str = path.join(path.dirname(__file__), "tokens", "token_gdrive.json")


class MainSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    max: MaxSettings = Field(default_factory=MaxSettings)
    app: AppSettings = Field(default_factory=AppSettings)
    bitrix_bots: BitrixBots = Field(default_factory=BitrixBots)
    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    database: DatabaseBXSettings = Field(default_factory=DatabaseBXSettings)
    gdrive: GDriveSettings = Field(default_factory=GDriveSettings)

    bitrix: BitrixSettings = Field(default_factory=BitrixSettings)

    environment: str = Field(default="", env="ENVIRONMENT")
    test_user_id: int = Field(default=0, env="TEST_USER_ID")
    sentry_dsn: str = Field(default="", env="SENTRY_DSN")
    logger_level: str = Field(default="INFO", env="LOGGER_LEVEL")
    max_server: str = Field(default="", env="MAX_SERVER")
    swagger_login: str = Field(default="", env="SWAGGER_LOGIN")
    swagger_token: str = Field(default="", env="SWAGGER_TOKEN")
    admin_username: str = Field(default="", env="ADMIN_USERNAME")
    admin_password: str = Field(default="", env="ADMIN_PASSWORD")
    algorithm: str = Field(default="", env="ALGORITHM")
    access_token_expire_minutes: str = Field(default="", env="ACCESS_TOKEN_EXPIRE_MINUTES")


@lru_cache()
def get_settings() -> MainSettings:
    return MainSettings()


settings = get_settings()
