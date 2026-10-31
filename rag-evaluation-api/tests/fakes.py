"""Dublês compartilhados entre os testes de servico e os de contrato da avaliacao."""

import uuid

from app.models.telemetry import EtapaPipeline
from app.rag.pipeline import RespostaDePipeline
from app.rag.retrieval.base import Candidato, MetricaEtapa
from app.services.evaluation import ROTULOS, DependenciasDeAvaliacao


class PipelineFalso:
    """Substitui `executar_pipeline`: uma resposta previsivel por braco, sem OpenAI nem Milvus.

    O texto gerado **nao** cita o codigo do pipeline — se citasse, o teste que varre o JSON em
    busca de vazamento da identidade passaria a acusar o proprio duble.
    """

    def __init__(self, *, falhar_em: str | None = None) -> None:
        self.falhar_em = falhar_em
        self.chamadas: list[tuple[str, uuid.UUID, str]] = []

    def __call__(self, pipeline, document_id, pergunta, *, cliente_milvus=None):
        self.chamadas.append((pipeline.codigo, document_id, pergunta))
        if pipeline.codigo == self.falhar_em:
            raise RuntimeError("openai fora do ar")
        return RespostaDePipeline(
            texto=f"resposta numero {pipeline.codigo[-1]}",
            metricas=[
                MetricaEtapa(
                    etapa=EtapaPipeline.EMBEDDING_QUERY,
                    duracao_ms=5,
                    tokens_total=7,
                    modelo="text-embedding-3-small",
                    detalhes={"query": pergunta},
                ),
                MetricaEtapa(
                    etapa=EtapaPipeline.GENERATION,
                    duracao_ms=11,
                    tokens_prompt=30,
                    tokens_completion=20,
                    tokens_total=50,
                    modelo="gpt-4.1-mini",
                ),
            ],
            chunks=[
                # ID real do Milvus: o auto_id nao cabe em 32 bits.
                Candidato(
                    milvus_id=470122313216735446, chunk_index=0, texto="trecho um", score_final=0.9
                ),
                Candidato(milvus_id=2, chunk_index=1, texto="trecho dois", score_final=0.5),
            ],
        )


def dependencias_falsas(executor: PipelineFalso) -> DependenciasDeAvaliacao:
    """Rotulos em ordem fixa: o embaralhamento tem teste proprio e aqui so atrapalharia."""
    return DependenciasDeAvaliacao(
        executar_pipeline=executor,
        construir_cliente_milvus=lambda: object(),
        sortear_rotulos=lambda quantidade: list(ROTULOS[:quantidade]),
    )
