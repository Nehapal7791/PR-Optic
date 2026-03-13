import pytest
from pydantic import ValidationError


def test_settings_requires_all_env_vars(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    
    with pytest.raises(ValidationError) as exc_info:
        from src.config import Settings
        Settings()
    
    errors = exc_info.value.errors()
    assert len(errors) == 3
    assert any(e["loc"] == ("github_token",) for e in errors)
    assert any(e["loc"] == ("github_webhook_secret",) for e in errors)
    assert any(e["loc"] == ("anthropic_api_key",) for e in errors)


def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "test_token_123")
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "test_secret_456")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test_key_789")
    
    from src.config import Settings
    settings = Settings()
    
    assert settings.github_token == "test_token_123"
    assert settings.github_webhook_secret == "test_secret_456"
    assert settings.anthropic_api_key == "test_key_789"
