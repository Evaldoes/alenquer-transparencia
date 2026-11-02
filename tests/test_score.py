from datetime import datetime, timedelta

import pytest

import monitor

EMPRESA_REGULAR = {
    "data_inicio_atividade": "2000-01-01",
    "capital_social": 500_000,
    "porte": "05",
    "situacao_cadastral": "ATIVA",
    "estabelecimento": {"logradouro": "AVENIDA BRASIL"},
}


def empresa(**campos):
    return {**EMPRESA_REGULAR, **campos}


def data_ha(dias):
    return (datetime.now() - timedelta(days=dias)).strftime("%Y-%m-%d")


def test_empresa_regular_nao_pontua():
    assert monitor.score_cnpj({}, EMPRESA_REGULAR, []) == (0, [])


def test_sem_dados_de_cnpj_nao_pontua():
    assert monitor.score_cnpj({}, None, []) == (0, [])


@pytest.mark.parametrize(("dias", "pontos"), [(30, 30), (200, 15), (800, 0)])
def test_idade_da_empresa(dias, pontos):
    score, _ = monitor.score_cnpj({}, empresa(data_inicio_atividade=data_ha(dias)), [])
    assert score == pontos


def test_data_invalida_nao_conta_como_empresa_nova():
    assert monitor.score_cnpj({}, empresa(data_inicio_atividade="?"), [])[0] == 0


def test_capital_baixo():
    assert monitor.score_cnpj({}, empresa(capital_social=9_999), [])[0] == 20


def test_empresa_mei():
    assert monitor.score_cnpj({}, empresa(porte="MEI"), [])[0] == 25


def test_empresa_inativa():
    assert monitor.score_cnpj({}, empresa(situacao_cadastral="BAIXADA"), [])[0] == 50


def test_endereco_residencial():
    dados = empresa(estabelecimento={"logradouro": "TRAVESSA DAS FLORES"})
    assert monitor.score_cnpj({}, dados, [])[0] == 15


@pytest.mark.parametrize(("valor", "pontos"), [(65_492.11, 20), (65_492.12, 40)])
def test_dispensa_de_licitacao(valor, pontos):
    contrato = {"modalidadeCompra": "Dispensa", "valorInicialCompra": valor}
    assert monitor.score_cnpj(contrato, None, [])[0] == pontos


def test_contrato_de_emergencia():
    assert monitor.score_cnpj({"modalidadeCompra": "Emergencial"}, None, [])[0] == 25


def test_empresa_repetida_ignora_formatacao_do_cnpj():
    contrato = {"cnpjContratado": "11.222.333/0001-81"}
    outros = [contrato, {"cnpjContratado": "11222333000181"}, {"cnpjContratado": "11222333000181"}]
    assert monitor.score_cnpj(contrato, None, outros)[0] == 15


def test_score_cnpj_tem_teto_de_100():
    dados = empresa(data_inicio_atividade=data_ha(10), capital_social=0, porte="MEI",
                    situacao_cadastral="BAIXADA")
    assert monitor.score_cnpj({"modalidadeCompra": "Dispensa"}, dados, [])[0] == 100


OBJETO = "Construção de escola municipal"


@pytest.mark.parametrize(("situacao", "pontos"), [
    ("INADIMPLENTE", 50),
    ("INADIMPLÊNCIA SUSPENSA", 25),
    ("PRESTAÇÃO DE CONTAS REJEITADA", 40),
    ("APROVADA COM RESSALVAS", 15),
    ("CANCELADO", 20),
    ("CONCLUÍDO", 0),
])
def test_situacao_do_convenio(situacao, pontos):
    contrato = {"situacao": situacao, "objetoCompra": OBJETO}
    assert monitor.score_convenio(contrato)[0] == pontos


def test_objeto_vago():
    assert monitor.score_convenio({"situacao": "CONCLUÍDO", "objetoCompra": "obra"})[0] == 20


def test_baixa_liberacao_de_recursos():
    contrato = {"objetoCompra": OBJETO, "valorTotal": 100_000, "valorLiberado": 10_000}
    assert monitor.score_convenio(contrato)[0] == 15


def test_vigencia_expirada_em_execucao():
    contrato = {"situacao": "EM EXECUÇÃO", "objetoCompra": OBJETO, "dataFim": data_ha(5)}
    assert monitor.score_convenio(contrato)[0] == 20


def test_score_convenio_tem_teto_de_60():
    contrato = {"situacao": "INADIMPLENTE", "objetoCompra": "x",
                "valorTotal": 100_000, "valorLiberado": 1}
    assert monitor.score_convenio(contrato)[0] == 60


@pytest.mark.parametrize(("score", "nivel"), [
    (0, "BAIXO"), (39, "BAIXO"), (40, "MÉDIO"), (69, "MÉDIO"), (70, "ALTO"), (100, "ALTO"),
])
def test_nivel_de_risco(score, nivel):
    assert monitor._nivel(score)[0] == nivel


def test_grupos_de_preco_nao_dependem_da_ordem_das_palavras():
    contratos = [
        {"objetoCompra": "alfa bravo charlie delta echo foxtrot", "valor": 100, "cnpjContratado": "1"},
        {"objetoCompra": "foxtrot echo delta charlie bravo alfa", "valor": 300, "cnpjContratado": "2"},
    ]
    assert monitor.comparar_precos(contratos)["2"][0]["desvio_pct"] == 50
