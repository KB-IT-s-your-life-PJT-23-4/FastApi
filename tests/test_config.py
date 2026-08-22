from app.core.config import Settings


REQUIRED_API_ENV = {
    "OPENAI_API_KEY": "test-chat-key",
    "OPENAI_EMBEDDING_API_KEY": "test-embedding-key",
}


def test_settings_accept_mirizoom_database_environment(monkeypatch) -> None:
    database_env = {
        "MIRIZOOM_DB_HOST": "db.example.ap-northeast-2.rds.amazonaws.com",
        "MIRIZOOM_DB_PORT": "3306",
        "MIRIZOOM_DB_NAME": "mirizoom",
        "MIRIZOOM_DB_USER": "app_user",
        "MIRIZOOM_DB_PASSWORD": "test-password",
        "MIRIZOOM_DB_CONNECT_TIMEOUT": "5",
    }

    for name, value in {**REQUIRED_API_ENV, **database_env}.items():
        monkeypatch.setenv(name, value)

    settings = Settings(_env_file=None)

    assert settings.mirizoom_db_host == database_env["MIRIZOOM_DB_HOST"]
    assert settings.mirizoom_db_port == 3306
    assert settings.mirizoom_db_name == "mirizoom"
    assert settings.mirizoom_db_user == "app_user"
    assert settings.mirizoom_db_password == "test-password"
    assert settings.mirizoom_db_connect_timeout == 5


def test_mirizoom_names_take_priority_over_legacy_database_names(
    monkeypatch,
) -> None:
    environment = {
        **REQUIRED_API_ENV,
        "MIRIZOOM_DB_HOST": "rds.example.com",
        "MIRIZOOM_DB_USER": "fastapi_user",
        "DB_HOST": "legacy.example.com",
        "DB_USERNAME": "legacy_user",
    }

    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    settings = Settings(_env_file=None)

    assert settings.mirizoom_db_host == "rds.example.com"
    assert settings.mirizoom_db_user == "fastapi_user"
