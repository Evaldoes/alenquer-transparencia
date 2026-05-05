"""
Agendamento automático — configura cron jobs para o monitor rodar sem intervenção.
"""
import os
import subprocess
from pathlib import Path

DIR = Path(__file__).parent.parent
ENV = DIR / ".env"


def cron_linha(frequencia, comando):
    tabela = {
        "diario":   "0 7 * * *",
        "semanal":  "0 7 * * 1",
        "quinzenal":"0 7 1,15 * *",
        "mensal":   "0 7 1 * *",
    }
    cron = tabela.get(frequencia, "0 7 * * 1")
    return f"{cron} {comando}"


def instalar_cron(frequencia="semanal", email=None, token=None):
    """
    Instala cron job para rodar o monitor automaticamente.
    Retorna a linha adicionada ao crontab.
    """
    python = DIR / "venv" / "bin" / "python"
    monitor = DIR / "monitor.py"
    log     = DIR / "dados" / "cron.log"
    log.parent.mkdir(exist_ok=True)

    # Ler token do .env se não fornecido
    if not token and ENV.exists():
        for linha in ENV.read_text().splitlines():
            if linha.startswith("PORTAL_TOKEN="):
                token = linha.split("=", 1)[1].strip().strip('"')
                break

    if not token:
        return None, "Token não configurado. Configure via ./alenquer.sh opção 'a'."

    args = f"--token {token}"
    if email:
        args += f" --email {email}"

    cmd = (f'cd {DIR} && {python} {monitor} {args} '
           f'>> {log} 2>&1')
    linha = cron_linha(frequencia, cmd)

    # Ler crontab atual
    try:
        atual = subprocess.run(["crontab", "-l"],
                               capture_output=True, text=True).stdout
    except Exception:
        atual = ""

    # Remover linhas antigas do monitor
    linhas = [l for l in atual.splitlines()
              if "monitor.py" not in l and l.strip()]

    # Adicionar nova linha
    linhas.append(linha)
    novo_crontab = "\n".join(linhas) + "\n"

    proc = subprocess.run(["crontab", "-"],
                          input=novo_crontab, text=True,
                          capture_output=True)
    if proc.returncode != 0:
        return None, f"Erro ao instalar cron: {proc.stderr}"

    return linha, "Cron instalado com sucesso."


def remover_cron():
    """Remove todos os cron jobs do monitor."""
    try:
        atual = subprocess.run(["crontab", "-l"],
                               capture_output=True, text=True).stdout
        linhas = [l for l in atual.splitlines()
                  if "monitor.py" not in l]
        subprocess.run(["crontab", "-"],
                       input="\n".join(linhas) + "\n", text=True)
        return "Cron removido."
    except Exception as e:
        return f"Erro: {e}"


def listar_crons():
    """Lista os cron jobs ativos do monitor."""
    try:
        saida = subprocess.run(["crontab", "-l"],
                               capture_output=True, text=True).stdout
        return [l for l in saida.splitlines() if "monitor.py" in l]
    except Exception:
        return []


def status():
    """Retorna status do agendamento."""
    crons    = listar_crons()
    log_path = DIR / "dados" / "cron.log"
    ultima   = None
    if log_path.exists():
        linhas = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        # Pegar última linha com data
        for l in reversed(linhas):
            if "Resumo" in l or "analisados" in l.lower():
                ultima = l.strip()
                break
    return {
        "ativo":        len(crons) > 0,
        "crons":        crons,
        "ultima_execucao": ultima,
        "log_path":     str(log_path),
    }
