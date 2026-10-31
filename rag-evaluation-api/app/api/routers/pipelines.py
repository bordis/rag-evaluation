"""CRUD dos pipelines. Com estudo aberto a configuracao fica travada, para nao misturar tratamentos.

Cada resposta tambem guarda um snapshot da config, entao o que ja foi coletado nunca muda.
"""

from fastapi import APIRouter, HTTPException, status
from sqlmodel import Session, select

from app.core.db import SessionDep
from app.core.milvus import construir_cliente, garantir_collection
from app.models.evaluation import PipelineAnswer
from app.models.pipeline import Pipeline
from app.schemas.admin import PipelineAtualizar, PipelineCriar, PipelineDetalhe
from app.seed import CODIGOS_DE_CONTROLE, FLAGS_RETRIEVAL
from app.services.studies import PIPELINES_DO_DESENHO, estudo_aberto

router = APIRouter(prefix="/api/pipelines", tags=["pipelines"])


def _detalhar(pipeline: Pipeline) -> PipelineDetalhe:
    return PipelineDetalhe(
        id=pipeline.id,  # type: ignore[arg-type]
        codigo=pipeline.codigo,
        nome=pipeline.nome,
        descricao=pipeline.descricao,
        parser=pipeline.parser,
        collection_name=pipeline.collection_name,
        ativo=pipeline.ativo,
        config=pipeline.config,
        controle=pipeline.codigo in CODIGOS_DE_CONTROLE,
        atualizado_em=pipeline.atualizado_em,
    )


def _obter(sessao: Session, pipeline_id: int) -> Pipeline:
    pipeline = sessao.get(Pipeline, pipeline_id)
    if pipeline is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Pipeline não encontrado.")
    return pipeline


def _exigir_sem_estudo_aberto(sessao: Session) -> None:
    if estudo_aberto(sessao) is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Encerre o estudo aberto antes de alterar os pipelines.",
        )


def _flag_ligada(config: dict, flag: str) -> bool:
    valor = config.get(flag)
    return bool(valor.get("ativo")) if isinstance(valor, dict) else bool(valor)


def _validar_controle(codigo: str, config: dict) -> None:
    """Os pipelines 1 e 2 sao o braco de controle: nele o fator B fica sempre desligado."""
    if codigo in CODIGOS_DE_CONTROLE and any(_flag_ligada(config, f) for f in FLAGS_RETRIEVAL):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Os pipelines de controle não podem ligar técnicas de recuperação avançada.",
        )


@router.get("")
def listar_pipelines(sessao: SessionDep) -> list[PipelineDetalhe]:
    return [_detalhar(item) for item in sessao.exec(select(Pipeline).order_by(Pipeline.codigo))]


@router.get("/{pipeline_id}")
def obter_pipeline(sessao: SessionDep, pipeline_id: int) -> PipelineDetalhe:
    return _detalhar(_obter(sessao, pipeline_id))


@router.post("", status_code=status.HTTP_201_CREATED)
def criar_pipeline(sessao: SessionDep, dados: PipelineCriar) -> PipelineDetalhe:
    """Nasce inativo: nao tem documentos ingeridos e o desenho ja tem seus quatro bracos."""
    _exigir_sem_estudo_aberto(sessao)
    _validar_controle(dados.codigo, dados.config)
    if sessao.exec(select(Pipeline).where(Pipeline.codigo == dados.codigo)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Já existe pipeline com este código.")
    garantir_collection(construir_cliente(), dados.collection_name)
    pipeline = Pipeline(**dados.model_dump(), ativo=False)
    sessao.add(pipeline)
    sessao.commit()
    sessao.refresh(pipeline)
    return _detalhar(pipeline)


@router.put("/{pipeline_id}")
def atualizar_pipeline(
    sessao: SessionDep, pipeline_id: int, dados: PipelineAtualizar
) -> PipelineDetalhe:
    _exigir_sem_estudo_aberto(sessao)
    pipeline = _obter(sessao, pipeline_id)
    alteracoes = dados.model_dump(exclude_unset=True)
    if alteracoes.get("config") is not None:
        _validar_controle(pipeline.codigo, alteracoes["config"])
    if alteracoes.get("ativo") and not pipeline.ativo:
        ativos = sessao.exec(select(Pipeline).where(Pipeline.ativo)).all()
        if len(ativos) >= PIPELINES_DO_DESENHO:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=f"Já há {PIPELINES_DO_DESENHO} pipelines ativos, o limite do desenho.",
            )
    for campo, valor in alteracoes.items():
        if valor is not None:
            setattr(pipeline, campo, valor)
    sessao.add(pipeline)
    sessao.commit()
    sessao.refresh(pipeline)
    return _detalhar(pipeline)


@router.delete("/{pipeline_id}", status_code=status.HTTP_204_NO_CONTENT)
def excluir_pipeline(sessao: SessionDep, pipeline_id: int) -> None:
    _exigir_sem_estudo_aberto(sessao)
    pipeline = _obter(sessao, pipeline_id)
    if sessao.exec(select(PipelineAnswer).where(PipelineAnswer.pipeline_id == pipeline_id)).first():
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Este pipeline já tem respostas registradas; desative-o em vez de excluir.",
        )
    sessao.delete(pipeline)
    sessao.commit()
