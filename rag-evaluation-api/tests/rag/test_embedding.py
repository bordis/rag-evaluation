from types import SimpleNamespace

from app.rag.embedding import TAMANHO_DO_LOTE, embutir_textos


class ClienteFalso:
    """Reproduz a forma da resposta do SDK da OpenAI: .data[].embedding/.index e .usage."""

    def __init__(self, *, embaralhar: bool = False) -> None:
        self.chamadas: list[dict] = []
        self.embaralhar = embaralhar
        self.embeddings = SimpleNamespace(create=self._create)

    def _create(self, *, model: str, input: list[str], dimensions: int):
        self.chamadas.append({"model": model, "input": input, "dimensions": dimensions})
        itens = [
            SimpleNamespace(index=posicao, embedding=[float(len(texto)), 0.0])
            for posicao, texto in enumerate(input)
        ]
        if self.embaralhar:
            itens = list(reversed(itens))
        return SimpleNamespace(
            data=itens, usage=SimpleNamespace(prompt_tokens=len(input) * 10, total_tokens=0)
        )


def test_lista_vazia_nao_chama_a_api():
    cliente = ClienteFalso()
    resultado = embutir_textos([], cliente=cliente)
    assert resultado.vetores == []
    assert resultado.tokens == 0
    assert cliente.chamadas == []


def test_um_lote_preserva_a_ordem_dos_textos():
    cliente = ClienteFalso()
    resultado = embutir_textos(["ab", "abcd", "a"], cliente=cliente)
    assert [vetor[0] for vetor in resultado.vetores] == [2.0, 4.0, 1.0]
    assert len(cliente.chamadas) == 1


def test_tokens_sao_somados_e_devolvidos():
    resultado = embutir_textos(["ab", "abcd"], cliente=ClienteFalso())
    assert resultado.tokens == 20


def test_textos_acima_do_lote_viram_varias_chamadas():
    cliente = ClienteFalso()
    textos = ["x" * (numero + 1) for numero in range(TAMANHO_DO_LOTE + 5)]
    resultado = embutir_textos(textos, cliente=cliente)
    assert len(cliente.chamadas) == 2
    assert len(resultado.vetores) == TAMANHO_DO_LOTE + 5
    assert resultado.tokens == (TAMANHO_DO_LOTE + 5) * 10
    assert [vetor[0] for vetor in resultado.vetores] == [float(len(t)) for t in textos]


def test_resposta_fora_de_ordem_e_reordenada_pelo_index():
    cliente = ClienteFalso(embaralhar=True)
    resultado = embutir_textos(["ab", "abcd", "a"], cliente=cliente)
    assert [vetor[0] for vetor in resultado.vetores] == [2.0, 4.0, 1.0]


def test_a_dimensao_configurada_e_enviada():
    cliente = ClienteFalso()
    embutir_textos(["ab"], cliente=cliente)
    assert cliente.chamadas[0]["dimensions"] == 1536
    assert cliente.chamadas[0]["model"] == "text-embedding-3-small"
