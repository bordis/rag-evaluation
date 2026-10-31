"""Schemas da avaliacao — o contrato que o frontend consome.

**Nenhum destes schemas tem campo `pipeline`.** Nao e "escondido na UI": a identidade do pipeline
nao existe no JSON que chega ao navegador. Essa e a garantia do cego, e o teste de contrato
`test_nenhuma_resposta_de_avaliacao_revela_o_pipeline` e a trava que impede uma refatoracao futura
de reintroduzi-la.
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class AceiteDoTermo(BaseModel):
    """Corpo do `POST /sessions`: sem aceite do termo de participacao, nao ha sessao."""

    aceite: Literal[True]
    termo_versao: str = Field(min_length=1, max_length=32)


class SessaoCriada(BaseModel):
    id: uuid.UUID
    study_id: uuid.UUID
    criado_em: datetime | None


class RespostaCega(BaseModel):
    """Uma resposta como o avaliador a ve: um rotulo e um texto, nada mais."""

    id: uuid.UUID
    rotulo: str
    texto: str


class RodadaDetalhe(BaseModel):
    id: uuid.UUID
    pergunta: str
    respostas: list[RespostaCega]
    ordem: int
    escolha_rotulo: str | None
    nenhuma_correta: bool
    criado_em: datetime | None
    escolhido_em: datetime | None


class EscolhaEntrada(BaseModel):
    """`rotulo` nulo significa "nenhuma esta correta". Os tempos sao medidos no navegador."""

    rotulo: str | None = Field(default=None, min_length=1, max_length=1, pattern="^[A-D]$")
    tempo_total_ms: int | None = Field(default=None, ge=0)
    tempo_geracao_ms: int | None = Field(default=None, ge=0)
    tempo_oculto_ms: int | None = Field(default=None, ge=0)


class ProgressoDocumento(BaseModel):
    document_id: uuid.UUID
    slug: str
    respondidas: int
    concluido: bool


class ProgressoSessao(BaseModel):
    session_id: uuid.UUID
    max_perguntas: int
    # Falso quando o estudo da sessao encerrou: o front descarta a sessao e volta ao inicio.
    estudo_aberto: bool
    total_concluidos: int
    documentos: list[ProgressoDocumento]
