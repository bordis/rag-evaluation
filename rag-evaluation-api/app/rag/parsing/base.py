"""Contrato comum aos parsers.

Os dois parsers sao intencionalmente desiguais: o raw extrai texto de forma ingenua e o Docling
devolve Markdown estruturado. Essa desigualdade e uma das duas variaveis independentes do estudo.
"""

from dataclasses import dataclass, field
from typing import Protocol

MIMES_SUPORTADOS: dict[str, str] = {
    "application/pdf": ".pdf",
    "text/plain": ".txt",
    "text/markdown": ".md",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}

EXTENSOES_SUPORTADAS: dict[str, str] = {
    extensao: mime for mime, extensao in MIMES_SUPORTADOS.items()
}


# O acervo do estudo e so de PDF digital (decisao 9): o texto bruto de outros formatos nao e
# comparavel ao de um PDF. Os parsers continuam aceitando os demais; a porta de entrada e que fecha.
MIME_DO_ACERVO = "application/pdf"


class ErroDeParsing(RuntimeError):
    """Falha ao extrair texto. Derruba a ingestao apenas do pipeline afetado."""


@dataclass(frozen=True)
class ResultadoParsing:
    texto: str
    metadados: dict = field(default_factory=dict)


class Parser(Protocol):
    def __call__(self, conteudo: bytes, mime_type: str, nome_arquivo: str) -> ResultadoParsing: ...
