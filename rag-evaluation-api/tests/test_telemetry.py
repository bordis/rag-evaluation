import time

from app.telemetry.recorder import Cronometro


def test_nasce_zerado():
    assert Cronometro().ms == 0


def test_mede_a_duracao_do_bloco():
    with Cronometro() as relogio:
        time.sleep(0.03)
    assert relogio.ms >= 25


def test_mede_mesmo_quando_o_bloco_falha():
    relogio = Cronometro()
    try:
        with relogio:
            time.sleep(0.03)
            raise RuntimeError("falhou")
    except RuntimeError:
        pass
    assert relogio.ms >= 25
