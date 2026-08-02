from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlmodel import Session, create_engine

from app.core.config import get_settings

engine = create_engine(get_settings().sqlalchemy_url, pool_pre_ping=True)


def get_session() -> Iterator[Session]:
    with Session(engine) as sessao:
        yield sessao


SessionDep = Annotated[Session, Depends(get_session)]


def rodar_migracoes() -> None:
    """Aplica as migracoes pendentes. Chamada no lifespan para o schema se atualizar sozinho."""
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    raiz = Path(__file__).resolve().parents[2]
    config = Config(str(raiz / "alembic.ini"))
    config.set_main_option("script_location", str(raiz / "alembic"))
    config.set_main_option("sqlalchemy.url", get_settings().sqlalchemy_url)
    command.upgrade(config, "head")
