import pytest

from bayline.sample.generate import generate
from bayline.sample.load import seed_database


@pytest.fixture(autouse=True)
def clear_model_settings(monkeypatch):
    for suffix in ("MODE", "REPLAY_DIR", "BASE_URL", "API_KEY", "MODEL", "TIMEOUT_SECONDS"):
        monkeypatch.delenv("BAYLINE_LLM_" + suffix, raising=False)


@pytest.fixture(scope="session")
def sample():
    return generate()


@pytest.fixture(scope="session")
def seeded_db(tmp_path_factory):
    path = tmp_path_factory.mktemp("snapshot") / "bayline.db"
    seed_database(path)
    return path
