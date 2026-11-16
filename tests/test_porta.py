"""`python app.py` precisa subir mesmo quando a porta 5000 está bloqueada
(caso comum no Windows: WinError 10013)."""
import socket

import pytest

from app import HOST, PORTAS_PADRAO, escolher_porta, portas_candidatas


@pytest.fixture
def porta_ocupada():
    ocupante = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    ocupante.bind((HOST, 0))
    ocupante.listen(1)
    yield ocupante.getsockname()[1]
    ocupante.close()


def _porta_livre():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


def _consegue_abrir(porta):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, porta))
    return True


def test_usa_a_primeira_porta_quando_livre():
    livre = _porta_livre()
    assert escolher_porta(HOST, [livre, _porta_livre()]) == livre


def test_pula_porta_bloqueada(porta_ocupada):
    livre = _porta_livre()
    assert escolher_porta(HOST, [porta_ocupada, livre]) == livre


def test_todas_bloqueadas_pede_uma_ao_sistema(porta_ocupada):
    escolhida = escolher_porta(HOST, [porta_ocupada])
    assert escolhida != porta_ocupada
    assert 0 < escolhida < 65536
    assert _consegue_abrir(escolhida)


def test_candidatas_padrao_comecam_pela_5000():
    assert portas_candidatas({}) == list(PORTAS_PADRAO)
    assert PORTAS_PADRAO[0] == 5000
    assert 8000 in PORTAS_PADRAO


def test_variavel_port_tem_prioridade():
    assert portas_candidatas({"PORT": "8123"}) == [8123, *PORTAS_PADRAO]
    assert portas_candidatas({"PORT": "8000"})[0] == 8000
    assert portas_candidatas({"PORT": "8000"}).count(8000) == 1


@pytest.mark.parametrize("valor", ["", "abc", "0", "-1", "70000", "80.5"])
def test_variavel_port_invalida_e_ignorada(valor):
    assert portas_candidatas({"PORT": valor}) == list(PORTAS_PADRAO)
