from types import SimpleNamespace

from app.models.telemetry import EtapaPipeline
from app.rag.retrieval.hyde import gerar_documento_hipotetico


class ClienteFalso:
    def __init__(self, texto: str) -> None:
        self.chamadas: list[dict] = []
        self.texto = texto
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **argumentos):
        self.chamadas.append(argumentos)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.texto))],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            model="gpt-4.1-mini",
        )


def test_devolve_o_paragrafo_e_registra_a_etapa():
    cliente = ClienteFalso("  O contribuinte pode contestar o lançamento.  ")

    hipotetico, metrica = gerar_documento_hipotetico("Como contesto o IPTU?", cliente=cliente)

    assert hipotetico == "O contribuinte pode contestar o lançamento."
    assert metrica.etapa is EtapaPipeline.HYDE
    assert metrica.tokens_total == 15
    assert metrica.detalhes["hipotetico"] == hipotetico
    assert metrica.detalhes["fallback"] is False


def test_paragrafo_vazio_nao_derruba_a_rodada():
    hipotetico, metrica = gerar_documento_hipotetico("Pergunta?", cliente=ClienteFalso("   "))

    assert hipotetico is None
    assert metrica.detalhes["fallback"] is True
