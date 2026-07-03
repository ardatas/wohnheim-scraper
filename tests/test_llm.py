from wohnheim_finder.llm import resolve_llm_config


def test_resolve_llm_prefers_deepseek(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")

    config = resolve_llm_config()

    assert config is not None
    assert config.provider == "deepseek"
    assert config.api_key == "deepseek-key"
    assert config.base_url == "https://api.deepseek.com"
    assert config.model == "deepseek-v4-flash"


def test_resolve_llm_supports_generic_openai_compatible(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "generic-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.deepseek.com/")
    monkeypatch.setenv("LLM_MODEL", "deepseek-v4-pro")

    config = resolve_llm_config()

    assert config is not None
    assert config.provider == "generic"
    assert config.api_key == "generic-key"
    assert config.base_url == "https://api.deepseek.com"
    assert config.model == "deepseek-v4-pro"
