from types import SimpleNamespace

from app.models.telemetry import EtapaPipeline
from app.rag.retrieval.rewrite import reescrever_query

PERGUNTA = "e sobre o que fala aquela parte de consentimento?"


class ClienteFalso:
    def __init__(self, texto: str = "consentimento do titular para tratamento de dados") -> None:
        self.chamadas: list[dict] = []
        self.texto = texto
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **argumentos):
        self.chamadas.append(argumentos)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.texto))],
            usage=SimpleNamespace(prompt_tokens=60, completion_tokens=12, total_tokens=72),
            model="gpt-4.1-mini-2025-04-14",
        )


def test_devolve_a_query_reescrita():
    query, _ = reescrever_query(PERGUNTA, cliente=ClienteFalso())
    assert query == "consentimento do titular para tratamento de dados"


def test_metrica_registra_etapa_tokens_e_modelo():
    _, metrica = reescrever_query(PERGUNTA, cliente=ClienteFalso())
    assert metrica.etapa is EtapaPipeline.QUERY_REWRITING
    assert metrica.tokens_total == 72
    assert metrica.modelo == "gpt-4.1-mini-2025-04-14"
    assert metrica.duracao_ms >= 0


def test_detalhes_guardam_a_pergunta_original_e_a_reescrita():
    """Sem as duas versoes gravadas, nao da para avaliar se a reescrita ajudou ou atrapalhou."""
    _, metrica = reescrever_query(PERGUNTA, cliente=ClienteFalso())
    assert metrica.detalhes["original"] == PERGUNTA
    assert metrica.detalhes["reescrita"] == "consentimento do titular para tratamento de dados"
    assert metrica.detalhes["fallback"] is False


def test_resposta_vazia_mantem_a_pergunta_original():
    query, metrica = reescrever_query(PERGUNTA, cliente=ClienteFalso(texto="   "))
    assert query == PERGUNTA
    assert metrica.detalhes["fallback"] is True


def test_a_pergunta_do_usuario_vai_no_prompt():
    cliente = ClienteFalso()
    reescrever_query(PERGUNTA, cliente=cliente)
    mensagens = cliente.chamadas[0]["messages"]
    assert mensagens[0]["role"] == "system"
    assert PERGUNTA in mensagens[-1]["content"]
