from pydantic import BaseModel


class ComponenteSaude(BaseModel):
    nome: str
    disponivel: bool
    erro: str | None = None


class RespostaSaude(BaseModel):
    saudavel: bool
    componentes: list[ComponenteSaude]
