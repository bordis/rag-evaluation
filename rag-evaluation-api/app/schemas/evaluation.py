"""Schemas da avaliacao — o contrato que o frontend consome.

**Nenhum destes schemas tem campo `pipeline`.** Nao e "escondido na UI": a identidade do pipeline
nao existe no JSON que chega ao navegador. Essa e a garantia do cego, e o teste de contrato
`test_nenhuma_resposta_de_avaliacao_revela_o_pipeline` e a trava que impede uma refatoracao futura
de reintroduzi-la.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.evaluation import Familiaridade, TempoExperiencia


class PerfilAvaliador(BaseModel):
    """Corpo do `POST /sessions`. Todo o perfil e opcional — a sessao e anonima."""

    area_atuacao: str | None = Field(default=None, max_length=120)
    familiaridade: Familiaridade | None = None
    tempo_experiencia: TempoExperiencia | None = None


class SessaoCriada(BaseModel):
    id: uuid.UUID
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
    escolha_rotulo: str | None
    criado_em: datetime | None
    escolhido_em: datetime | None


class EscolhaEntrada(BaseModel):
    rotulo: str = Field(min_length=1, max_length=1, pattern="^[A-D]$")


class ProgressoDocumento(BaseModel):
    document_id: uuid.UUID
    slug: str
    respondidas: int
    concluido: bool


class ProgressoSessao(BaseModel):
    session_id: uuid.UUID
    max_perguntas: int
    total_concluidos: int
    documentos: list[ProgressoDocumento]
