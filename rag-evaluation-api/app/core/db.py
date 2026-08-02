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
