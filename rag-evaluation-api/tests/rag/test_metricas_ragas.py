from types import SimpleNamespace

from app.rag.metricas_ragas import AvaliacaoRagas, MetricasRagas, avaliar_resposta


class MetricaFalsa:
    def __init__(self, valor: float) -> None:
        self.valor = valor
        self.argumentos: dict = {}

    async def ascore(self, **argumentos) -> SimpleNamespace:
        self.argumentos = argumentos
        return SimpleNamespace(value=self.valor)


async def test_cada_nota_vem_da_sua_metrica():
    metricas = MetricasRagas(
        fidelidade=MetricaFalsa(0.1),
        relevancia_resposta=MetricaFalsa(0.2),
        precisao_contexto=MetricaFalsa(0.3),
    )

    avaliacao = await avaliar_resposta("pergunta", "resposta", ["contexto"], metricas=metricas)

    assert avaliacao == AvaliacaoRagas(
        fidelidade=0.1, relevancia_resposta=0.2, precisao_contexto=0.3
    )


async def test_relevancia_nao_recebe_os_contextos():
    fidelidade = MetricaFalsa(1.0)
    relevancia = MetricaFalsa(1.0)
    metricas = MetricasRagas(
        fidelidade=fidelidade,
        relevancia_resposta=relevancia,
        precisao_contexto=MetricaFalsa(1.0),
    )

    await avaliar_resposta("pergunta", "resposta", ["contexto"], metricas=metricas)

    assert fidelidade.argumentos["retrieved_contexts"] == ["contexto"]
    assert relevancia.argumentos == {"user_input": "pergunta", "response": "resposta"}
