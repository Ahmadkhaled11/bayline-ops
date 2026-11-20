import json

import pytest

from bayline.cli import main
from bayline.llm import LiveClient, ModelConfigError, RecordingClient, ReplayClient, client_from_env

LIVE = {"BAYLINE_LLM_MODE": "live", "BAYLINE_LLM_BASE_URL": "https://provider.example/v1",
        "BAYLINE_LLM_API_KEY": "test-only-key", "BAYLINE_LLM_MODEL": "model"}


def test_default_and_modes(tmp_path):
    assert isinstance(client_from_env({}), ReplayClient)
    assert isinstance(client_from_env(LIVE), LiveClient)
    client = client_from_env({**LIVE, "BAYLINE_LLM_MODE": "record", "BAYLINE_LLM_REPLAY_DIR": str(tmp_path)})
    assert isinstance(client, RecordingClient) and client.replay_dir == tmp_path
    with pytest.raises(ModelConfigError, match="BAYLINE_LLM_MODE"):
        client_from_env({"BAYLINE_LLM_MODE": "invalid"})


@pytest.mark.parametrize("key", ["BAYLINE_LLM_BASE_URL", "BAYLINE_LLM_API_KEY", "BAYLINE_LLM_MODEL"])
def test_missing_settings(key):
    env = {k: v for k, v in LIVE.items() if k != key}
    with pytest.raises(ModelConfigError, match=key):
        client_from_env(env)


@pytest.mark.parametrize("timeout", ["zero", "0", "-1", "nan", "inf"])
def test_bad_timeout(timeout):
    with pytest.raises(ModelConfigError, match="BAYLINE_LLM_TIMEOUT_SECONDS"):
        client_from_env({**LIVE, "BAYLINE_LLM_TIMEOUT_SECONDS": timeout})


def test_check_defaults_and_json(capsys):
    assert main(["llm-check"]) == 0
    output = capsys.readouterr().out
    assert "mode: replay" in output and "key set: no" in output
    assert main(["llm-check", "--json", "--ping"]) == 0
    assert json.loads(capsys.readouterr().out)["key set"] == "no"


def test_check_live_never_prints_key(monkeypatch, capsys):
    for k, v in LIVE.items():
        monkeypatch.setenv(k, v)
    assert main(["llm-check"]) == 0
    output = capsys.readouterr().out
    assert "key set: yes" in output and "test-only-key" not in output
    monkeypatch.delenv("BAYLINE_LLM_MODEL")
    assert main(["llm-check"]) == 2
    assert "test-only-key" not in capsys.readouterr().out


def test_ping_with_fake_client(monkeypatch, capsys):
    import bayline.llm
    from bayline.llm import ChatResponse

    calls = []

    class Fake:
        def complete(self, request):
            calls.append(request)
            return ChatResponse("Hello.", "model", "stop")

    monkeypatch.setenv("BAYLINE_LLM_MODE", "live")
    monkeypatch.setattr(bayline.llm, "client_from_env", lambda: Fake())
    assert main(["llm-check", "--ping"]) == 0
    assert len(calls) == 1
    assert "response: Hello." in capsys.readouterr().out
