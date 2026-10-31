from types import SimpleNamespace

from app.models.telemetry import EtapaPipeline
from app.rag.generation import INSTRUCAO_SISTEMA, gerar_resposta
from app.rag.retrieval.base import Candidato

PERGUNTA = "O que e dado pessoal?"


class ClienteFalso:
    def __init__(self, texto: str = "Dado pessoal e toda informacao sobre pessoa natural.") -> None:
        self.chamadas: list[dict] = []
        self.texto = texto
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **argumentos):
        self.chamadas.append(argumentos)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.texto))],
            usage=SimpleNamespace(prompt_tokens=800, completion_tokens=90, total_tokens=890),
            model="gpt-4.1-mini-2025-04-14",
        )


def _candidatos() -> list[Candidato]:
    return [
        Candidato(milvus_id=1, chunk_index=3, texto="Artigo 5: dado pessoal e ..."),
        Candidato(milvus_id=2, chunk_index=4, texto="Paragrafo unico: ..."),
    ]


def test_devolve_o_texto_gerado():
    texto, _ = gerar_resposta(PERGUNTA, _candidatos(), cliente=ClienteFalso())
    assert texto == "Dado pessoal e toda informacao sobre pessoa natural."


def test_todos_os_trechos_entram_no_prompt():
    cliente = ClienteFalso()
    gerar_resposta(PERGUNTA, _candidatos(), cliente=cliente)
    conteudo = cliente.chamadas[0]["messages"][-1]["content"]
    assert "Artigo 5: dado pessoal e ..." in conteudo
    assert "Paragrafo unico: ..." in conteudo
    assert PERGUNTA in conteudo


def test_a_instrucao_proibe_conhecimento_externo():
    """Sem essa amarra, o modelo responderia de memoria e o estudo mediria o modelo, nao o RAG."""
    cliente = ClienteFalso()
    gerar_resposta(PERGUNTA, _candidatos(), cliente=cliente)
    sistema = cliente.chamadas[0]["messages"][0]
    assert sistema["role"] == "system"
    assert sistema["content"] == INSTRUCAO_SISTEMA
    assert "contexto" in INSTRUCAO_SISTEMA.lower()


def test_metrica_registra_etapa_tokens_e_modelo():
    _, metrica = gerar_resposta(PERGUNTA, _candidatos(), cliente=ClienteFalso())
    assert metrica.etapa is EtapaPipeline.GENERATION
    assert metrica.tokens_prompt == 800
    assert metrica.tokens_completion == 90
    assert metrica.modelo == "gpt-4.1-mini-2025-04-14"


def test_metrica_registra_quantos_trechos_sustentaram_a_resposta():
    _, metrica = gerar_resposta(PERGUNTA, _candidatos(), cliente=ClienteFalso())
    assert metrica.detalhes["trechos"] == 2
    assert metrica.detalhes["sem_contexto"] is False


def test_sem_candidatos_ainda_responde_mas_marca_a_ausencia_de_contexto():
    texto, metrica = gerar_resposta(PERGUNTA, [], cliente=ClienteFalso())
    assert texto
    assert metrica.detalhes["sem_contexto"] is True
    assert metrica.detalhes["trechos"] == 0
