import pytest
from fastapi.testclient import TestClient

import app as app_module
from modules import banco


@pytest.fixture(autouse=True)
def ambiente_isolado(tmp_path, monkeypatch):
    """Usa banco e pasta de dados temporários e nenhuma credencial real."""
    monkeypatch.setattr(banco, "DB_PATH", tmp_path / "historico.db")
    monkeypatch.setattr(app_module, "DADOS_DIR", tmp_path)
    monkeypatch.setattr(app_module, "ENV_FILE", tmp_path / ".env")
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    monkeypatch.setenv("PORTAL_TOKEN", "token-secreto")
    monkeypatch.setattr(app_module, "instalar_cron", lambda *_: (None, "simulado"))
    monkeypatch.setattr(app_module, "remover_cron", lambda: "simulado")
    banco.inicializar()


@pytest.fixture
def remoto():
    return TestClient(app_module.app, base_url="http://192.168.0.10:5000",
                      client=("192.168.0.20", 5555))


@pytest.fixture
def local():
    return TestClient(app_module.app, base_url="http://localhost:5000",
                      client=("127.0.0.1", 5555))
