"""Medicao de duracao por etapa.

Tempo por etapa e um dos dois numeros que a dissertacao compara entre os pipelines; medi-lo
por fora, com logs, perderia a precisao e a associacao com a linha do banco.
"""

import time


class Cronometro:
    """Mede em milissegundos o tempo do bloco `with`, inclusive quando ele levanta excecao."""

    def __init__(self) -> None:
        self.ms = 0
        self._inicio = 0.0

    def __enter__(self) -> "Cronometro":
        self._inicio = time.perf_counter()
        return self

    def __exit__(self, *_excecao: object) -> None:
        # Sem `return True`: a excecao continua subindo e o chamador decide o que fazer.
        self.ms = int((time.perf_counter() - self._inicio) * 1000)
