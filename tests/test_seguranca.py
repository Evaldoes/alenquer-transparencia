import pytest

ROTAS_PROTEGIDAS = [
    ("get", "/api/token"),
    ("get", "/api/denuncias"),
    ("get", "/api/agendamento/status"),
    ("get", "/api/pdf/download/x.pdf"),
    ("post", "/api/agendamento/instalar"),
    ("post", "/api/agendamento/remover"),
    ("post", "/api/denuncia"),
    ("post", "/api/ocr"),
]


@pytest.mark.parametrize(("metodo", "rota"), ROTAS_PROTEGIDAS)
def test_acesso_remoto_e_negado(remoto, metodo, rota):
    assert getattr(remoto, metodo)(rota).status_code == 403


def test_token_nao_vaza_para_acesso_remoto(remoto):
    assert "token-secreto" not in remoto.get("/api/token").text


def test_acesso_local_continua_funcionando(local):
    assert local.get("/api/token").json()["token"] == "token-secreto"


def test_site_externo_nao_aciona_rota_local(local):
    resposta = local.post("/api/agendamento/remover",
                          headers={"Origin": "https://site-malicioso.example"})
    assert resposta.status_code == 403


def test_dns_rebinding_e_bloqueado(local):
    resposta = local.get("/api/token", headers={"Host": "site-malicioso.example"})
    assert resposta.status_code == 403


def test_token_de_admin_libera_acesso_remoto(remoto, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "admin-123")
    resposta = remoto.get("/api/denuncias", headers={"X-Admin-Token": "admin-123"})
    assert resposta.status_code == 200


def test_token_de_admin_errado_e_negado(remoto, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "admin-123")
    resposta = remoto.get("/api/denuncias", headers={"X-Admin-Token": "errado"})
    assert resposta.status_code == 403


def test_token_de_admin_vazio_nao_libera(remoto, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "")
    resposta = remoto.get("/api/denuncias", headers={"X-Admin-Token": ""})
    assert resposta.status_code == 403


def test_api_publica_continua_aberta(remoto):
    assert remoto.get("/v1/status").status_code == 200


def test_download_entrega_pdf(local, tmp_path):
    (tmp_path / "boletim.pdf").write_bytes(b"%PDF-1.4")
    assert local.get("/api/pdf/download/boletim.pdf").status_code == 200


def test_download_nao_entrega_banco(local, tmp_path):
    assert (tmp_path / "historico.db").exists()
    assert local.get("/api/pdf/download/historico.db").status_code == 404


def test_servidor_usa_localhost_por_padrao():
    import app as app_module
    assert app_module.host_padrao({}) == "127.0.0.1"


def test_gateway_do_docker_e_aceito_somente_se_configurado(monkeypatch):
    from fastapi.testclient import TestClient

    import app as app_module
    cliente = TestClient(app_module.app, base_url="http://localhost:5000",
                         client=("172.30.0.1", 5555))
    assert cliente.get("/api/token").status_code == 403
    monkeypatch.setenv("CLIENTES_LOCAIS", "172.30.0.1")
    assert cliente.get("/api/token").status_code == 200
