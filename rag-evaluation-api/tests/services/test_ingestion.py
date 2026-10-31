import uuid

import pytest
from sqlmodel import Session, select

from app.models.document import Document, DocumentIngestion, StatusDocumento, StatusIngestao
from app.models.pipeline import ParserType, Pipeline
from app.rag.chunking import Chunk
from app.rag.embedding import ResultadoEmbedding
from app.rag.parsing.base import ErroDeParsing, ResultadoParsing
from app.seed import semear_pipelines
from app.services.ingestion import DependenciasDeIngestao, ingerir_documento

TEXTO_RAW = " ".join(f"raw{numero}" for numero in range(300))
TEXTO_DOCLING = " ".join(f"docling{numero}" for numero in range(300))


class Espiao:
    """Substitui parsing, embedding e indexacao para o orquestrador rodar sem infraestrutura."""

    def __init__(self, *, falhar_no_parser: ParserType | None = None) -> None:
        self.falhar_no_parser = falhar_no_parser
        self.parsers_pedidos: list[ParserType] = []
        self.embeddings: list[list[str]] = []
        self.indexacoes: list[tuple[str, uuid.UUID, int, dict]] = []
        self.cliente = object()

    def obter_parser(self, parser: ParserType):
        self.parsers_pedidos.append(parser)

        def parsear(conteudo: bytes, mime_type: str, nome_arquivo: str) -> ResultadoParsing:
            if parser == self.falhar_no_parser:
                raise ErroDeParsing("docling-serve fora do ar")
            texto = TEXTO_RAW if parser is ParserType.RAW else TEXTO_DOCLING
            return ResultadoParsing(texto=texto, metadados={"parser": parser.value})

        return parsear

    def embutir(self, textos: list[str]) -> ResultadoEmbedding:
        self.embeddings.append(textos)
        return ResultadoEmbedding(vetores=[[0.1, 0.2] for _ in textos], tokens=7 * len(textos))

    def indexar(
        self,
        cliente,
        collection_name: str,
        document_id: uuid.UUID,
        chunks: list[Chunk],
        vetores: list[list[float]],
        metadados: dict,
    ) -> int:
        self.indexacoes.append((collection_name, document_id, len(chunks), metadados))
        return len(chunks)

    def dependencias(self) -> DependenciasDeIngestao:
        return DependenciasDeIngestao(
            obter_parser=self.obter_parser,
            embutir=self.embutir,
            indexar=self.indexar,
            construir_cliente_milvus=lambda: self.cliente,
        )


@pytest.fixture(name="documento")
def documento_fixture(sessao: Session) -> Document:
    semear_pipelines(sessao)
    documento = Document(
        slug="lgpd",
        titulo="LGPD",
        area="Direito",
        descricao="Lei 13.709/2018",
        icone="D",
        nome_arquivo_original="lgpd.pdf",
        mime_type="application/pdf",
        tamanho_bytes=2048,
        sha256="b" * 64,
    )
    sessao.add(documento)
    sessao.commit()
    sessao.refresh(documento)

    for pipeline in sessao.exec(select(Pipeline)).all():
        sessao.add(DocumentIngestion(document_id=documento.id, pipeline_id=pipeline.id))
    sessao.commit()
    return documento


def _ingestoes(sessao: Session, documento: Document) -> list[DocumentIngestion]:
    return list(
        sessao.exec(
            select(DocumentIngestion)
            .join(Pipeline, Pipeline.id == DocumentIngestion.pipeline_id)  # type: ignore[arg-type]
            .where(DocumentIngestion.document_id == documento.id)
            .order_by(Pipeline.codigo)  # type: ignore[arg-type]
        ).all()
    )


def test_sucesso_nos_quatro_pipelines_deixa_o_documento_pronto(sessao, documento):
    espiao = Espiao()
    ingerir_documento(
        sessao,
        documento.id,
        b"%PDF",
        "application/pdf",
        "lgpd.pdf",
        dependencias=espiao.dependencias(),
    )
    sessao.refresh(documento)
    assert documento.status == StatusDocumento.PRONTO

    ingestoes = _ingestoes(sessao, documento)
    assert len(ingestoes) == 4
    assert all(item.status == StatusIngestao.CONCLUIDA for item in ingestoes)
    assert all(item.erro is None for item in ingestoes)


def test_telemetria_de_cada_pipeline_e_gravada(sessao, documento):
    espiao = Espiao()
    ingerir_documento(
        sessao,
        documento.id,
        b"%PDF",
        "application/pdf",
        "lgpd.pdf",
        dependencias=espiao.dependencias(),
    )
    for ingestao in _ingestoes(sessao, documento):
        assert ingestao.total_caracteres > 0
        assert ingestao.total_chunks > 0
        assert ingestao.tokens_embedding == 7 * ingestao.total_chunks
        assert ingestao.iniciado_em is not None
        assert ingestao.concluido_em is not None
        assert ingestao.duracao_total_ms >= 0


def test_cada_pipeline_usa_o_seu_parser_e_a_sua_collection(sessao, documento):
    espiao = Espiao()
    ingerir_documento(
        sessao,
        documento.id,
        b"%PDF",
        "application/pdf",
        "lgpd.pdf",
        dependencias=espiao.dependencias(),
    )
    assert espiao.parsers_pedidos == [
        ParserType.RAW,
        ParserType.DOCLING,
        ParserType.RAW,
        ParserType.DOCLING,
    ]
    assert [indexacao[0] for indexacao in espiao.indexacoes] == [
        "evaluation1",
        "evaluation2",
        "evaluation3",
        "evaluation4",
    ]


def test_nao_ha_reaproveitamento_de_trabalho_entre_pipelines(sessao, documento):
    """Os pipelines 1 e 3 produzem chunks identicos, mas cada um embute os seus.

    Reaproveitar economizaria embeddings e registraria tempo zero de parsing no pipeline 3,
    corrompendo justamente a telemetria comparativa que o estudo mede.
    """
    espiao = Espiao()
    ingerir_documento(
        sessao,
        documento.id,
        b"%PDF",
        "application/pdf",
        "lgpd.pdf",
        dependencias=espiao.dependencias(),
    )
    assert len(espiao.embeddings) == 4
    assert espiao.embeddings[0] == espiao.embeddings[2]


def test_falha_em_um_pipeline_deixa_o_documento_em_erro_parcial(sessao, documento):
    espiao = Espiao(falhar_no_parser=ParserType.DOCLING)
    ingerir_documento(
        sessao,
        documento.id,
        b"%PDF",
        "application/pdf",
        "lgpd.pdf",
        dependencias=espiao.dependencias(),
    )
    sessao.refresh(documento)
    assert documento.status == StatusDocumento.ERRO_PARCIAL

    ingestoes = _ingestoes(sessao, documento)
    assert [item.status for item in ingestoes] == [
        StatusIngestao.CONCLUIDA,
        StatusIngestao.ERRO,
        StatusIngestao.CONCLUIDA,
        StatusIngestao.ERRO,
    ]
    assert "docling-serve fora do ar" in ingestoes[1].erro


def test_falha_de_um_pipeline_nao_impede_os_outros(sessao, documento):
    espiao = Espiao(falhar_no_parser=ParserType.DOCLING)
    ingerir_documento(
        sessao,
        documento.id,
        b"%PDF",
        "application/pdf",
        "lgpd.pdf",
        dependencias=espiao.dependencias(),
    )
    assert [indexacao[0] for indexacao in espiao.indexacoes] == ["evaluation1", "evaluation3"]


def test_metadados_indexados_carregam_parser_e_slug(sessao, documento):
    espiao = Espiao()
    ingerir_documento(
        sessao,
        documento.id,
        b"%PDF",
        "application/pdf",
        "lgpd.pdf",
        dependencias=espiao.dependencias(),
    )
    metadados = espiao.indexacoes[0][3]
    assert metadados == {"parser": "raw", "slug": "lgpd"}


def test_documento_inexistente_nao_explode(sessao):
    espiao = Espiao()
    ingerir_documento(
        sessao,
        uuid.uuid4(),
        b"%PDF",
        "application/pdf",
        "x.pdf",
        dependencias=espiao.dependencias(),
    )
    assert espiao.indexacoes == []
