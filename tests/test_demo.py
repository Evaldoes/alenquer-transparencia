import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

import gerar_demo  # noqa: E402


def test_demo_publicada_esta_atualizada():
    assert gerar_demo.DESTINO.read_text(encoding="utf-8") == gerar_demo.gerar()


def test_demo_nao_contem_cnpj_nem_cpf():
    dados = (RAIZ / "demo" / "demo.js").read_text(encoding="utf-8")
    assert not re.search(r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}|\d{3}\.\d{3}\.\d{3}-\d{2}", dados)


def test_demo_avisa_que_os_dados_sao_ficticios():
    assert "dados fictícios" in gerar_demo.gerar()
