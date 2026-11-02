from modules import agendamento


def test_remove_apenas_jobs_deste_projeto():
    deste_projeto = f"0 7 * * * python {agendamento.DIR / 'monitor.py'}"
    crontab = f"0 1 * * * python /outro/projeto/monitor.py\n{deste_projeto}\n0 2 * * * backup\n"
    assert agendamento._sem_jobs_do_monitor(crontab) == [
        "0 1 * * * python /outro/projeto/monitor.py",
        "0 2 * * * backup",
    ]
