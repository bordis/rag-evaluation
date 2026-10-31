from types import SimpleNamespace

from app.rag.llm import conversar


class ClienteFalso:
    """Reproduz a forma da resposta do Chat Completions da OpenAI."""

    def __init__(self, *, texto: str = " resposta ", sem_uso: bool = False) -> None:
        self.chamadas: list[dict] = []
        self.texto = texto
        self.sem_uso = sem_uso
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **argumentos):
        self.chamadas.append(argumentos)
        uso = None
        if not self.sem_uso:
            uso = SimpleNamespace(prompt_tokens=120, completion_tokens=35, total_tokens=155)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.texto))],
            usage=uso,
            model="gpt-4.1-mini-2025-04-14",
        )


MENSAGENS = [{"role": "user", "content": "O que e dado pessoal?"}]


def test_extrai_o_texto_sem_espacos_nas_pontas():
    assert conversar(MENSAGENS, cliente=ClienteFalso()).texto == "resposta"


def test_extrai_a_contagem_de_tokens():
    resposta = conversar(MENSAGENS, cliente=ClienteFalso())
    assert (resposta.tokens_prompt, resposta.tokens_completion, resposta.tokens_total) == (
        120,
        35,
        155,
    )


def test_modelo_registrado_e_o_snapshot_devolvido_pela_api():
    """O .env diz `gpt-4.1-mini`, mas a API responde com o snapshot exato — e o que interessa."""
    assert conversar(MENSAGENS, cliente=ClienteFalso()).modelo == "gpt-4.1-mini-2025-04-14"


def test_usa_max_completion_tokens_e_nao_o_parametro_depreciado():
    cliente = ClienteFalso()
    conversar(MENSAGENS, cliente=cliente)
    assert cliente.chamadas[0]["max_completion_tokens"] == 1024
    assert "max_tokens" not in cliente.chamadas[0]


def test_envia_modelo_e_temperatura_da_configuracao():
    cliente = ClienteFalso()
    conversar(MENSAGENS, cliente=cliente)
    assert cliente.chamadas[0]["model"] == "gpt-4.1-mini"
    assert cliente.chamadas[0]["temperature"] == 0.3


def test_formato_json_so_e_pedido_quando_solicitado():
    cliente = ClienteFalso()
    conversar(MENSAGENS, cliente=cliente)
    assert "response_format" not in cliente.chamadas[0]

    conversar(MENSAGENS, cliente=cliente, resposta_json=True)
    assert cliente.chamadas[1]["response_format"] == {"type": "json_object"}


def test_resposta_sem_uso_nao_derruba_a_rodada():
    resposta = conversar(MENSAGENS, cliente=ClienteFalso(sem_uso=True))
    assert resposta.tokens_total == 0


def test_conteudo_nulo_vira_string_vazia():
    assert conversar(MENSAGENS, cliente=ClienteFalso(texto=None)).texto == ""
