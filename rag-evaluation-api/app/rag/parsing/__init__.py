"""Escolha do parser a partir do tipo gravado no pipeline.

O orquestrador de ingestao nunca cita `pipeline-1` ou `pipeline-2` por nome: ele le
`Pipeline.parser` do banco e pede o parser correspondente aqui. Um quinto pipeline seria uma
linha no banco, nao codigo novo.
"""

from app.models.pipeline import ParserType
from app.rag.parsing.base import (
    EXTENSOES_SUPORTADAS,
    MIMES_SUPORTADOS,
    ErroDeParsing,
    Parser,
    ResultadoParsing,
)
from app.rag.parsing.docling import extrair_texto_docling
from app.rag.parsing.raw import extrair_texto_raw

_PARSERS: dict[ParserType, Parser] = {
    ParserType.RAW: extrair_texto_raw,
    ParserType.DOCLING: extrair_texto_docling,
}

__all__ = [
    "EXTENSOES_SUPORTADAS",
    "MIMES_SUPORTADOS",
    "ErroDeParsing",
    "Parser",
    "ResultadoParsing",
    "obter_parser",
]


def obter_parser(parser: ParserType) -> Parser:
    try:
        return _PARSERS[parser]
    except KeyError as erro:
        raise ValueError(f"Nao ha parser cadastrado para {parser}.") from erro
