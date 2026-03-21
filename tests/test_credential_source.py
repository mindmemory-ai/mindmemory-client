from mindmemory_client.credential_source import credential_source


def test_credential_source_default(monkeypatch):
    monkeypatch.delenv("MMEM_CREDENTIAL_SOURCE", raising=False)
    assert credential_source() == "account"


def test_credential_source_env(monkeypatch):
    monkeypatch.setenv("MMEM_CREDENTIAL_SOURCE", "env")
    assert credential_source() == "env"


def test_credential_source_invalid_falls_back(monkeypatch):
    monkeypatch.setenv("MMEM_CREDENTIAL_SOURCE", "bogus")
    assert credential_source() == "account"
