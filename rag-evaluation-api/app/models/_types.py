from enum import StrEnum

from sqlalchemy import Enum as SAEnum


def coluna_enum(enum_cls: type[StrEnum], length: int) -> SAEnum:
    """Coluna de enum que grava o VALOR, nao o nome do membro.

    Por padrao o SQLAlchemy persiste o nome ("ATE_2_ANOS"), enquanto a API serializa o valor
    ("ate-2-anos") — divergencia entre o que esta no banco e o que trafega no JSON. Pior: um
    server_default escrito com o valor (ex. "processando") conviveria na mesma coluna com nomes
    gravados pelo ORM (ex. "PROCESSANDO").

    native_enum=False grava VARCHAR em vez de um tipo ENUM nativo do PostgreSQL, que e doloroso
    de migrar. create_constraint=True e explicito porque o padrao do SQLAlchemy e False desde a
    versao 1.4: sem ele nao haveria validacao nenhuma no banco, e um UPDATE manual poderia
    inserir um valor invalido no meio da coleta.
    """
    return SAEnum(
        enum_cls,
        native_enum=False,
        create_constraint=True,
        length=length,
        values_callable=lambda enum: [membro.value for membro in enum],
    )
