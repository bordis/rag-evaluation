# RAG Evaluation

Estudo de mestrado em que avaliadores humanos escolhem, **às cegas**, a melhor resposta entre
quatro configurações de pipeline RAG sobre o mesmo documento.

O repositório tem dois projetos:

| Pasta | O que é |
| --- | --- |
| [`rag-evaluation-api/`](rag-evaluation-api/) | Backend FastAPI: ingestão, consulta nos 4 pipelines, sessões, rodadas e telemetria. |
| [`rag-evaluation-web/`](rag-evaluation-web/) | Front-end Angular 21 (standalone + Signals), em Português (BR). |

## O desenho experimental

Quatro pipelines num fatorial 2×2 — só **parser** e **retrieval** variam; chunking e geração são
idênticos, de propósito, para não confundir as variáveis:

| Código | Parser | Retrieval |
| --- | --- | --- |
| `pipeline-1` | raw (pypdf / decode direto) | fixo: denso, top-k |
| `pipeline-2` | Docling | fixo: denso, top-k |
| `pipeline-3` | raw | configurável: query rewriting, re-rank, híbrido, janela deslizante |
| `pipeline-4` | Docling | configurável |

Comparar 1↔2 e 3↔4 isola o parser; comparar 1↔3 e 2↔4 isola o retrieval avançado.

**A avaliação às cegas é garantida pelo servidor:** nenhum schema de resposta da avaliação tem
campo `pipeline` — a identidade não existe no JSON que chega ao navegador. Cada rodada sorteia os
rótulos A/B/C/D de novo, então a posição também não é pista.

## Fluxo do avaliador

1. **Boas-vindas** (`/`) — explicação do estudo.
2. **Perfil** (`/perfil`) — três perguntas **opcionais**; é aqui que a sessão anônima é criada.
3. **Seleção de documento** (`/documentos`) — só documentos com ingestão concluída nos 4 pipelines.
4. **Avaliação** (`/avaliacao/:slug`) — pergunta → 4 respostas anônimas → escolha da melhor.

Até **10 perguntas respondidas por documento** (`MAX_PERGUNTAS`); o limite é imposto pelo servidor.
Só rodada **decidida** conta — perguntar e abandonar não consome a cota. O `sessionId` fica no
`sessionStorage` do navegador (e só ele: o histórico vem sempre da API), então recarregar a página
não perde o progresso.

---

# Configuração

## Pré-requisitos

| Requisito | Observação |
| --- | --- |
| **Python 3.12+** e [`uv`](https://docs.astral.sh/uv/) | `pip install uv` resolve, se não tiver. |
| **Node.js 20+** e npm | Para o front-end Angular. |
| **Docker + Compose** | Sobe Milvus, etcd, MinIO e docling-serve. |
| **PostgreSQL 17 rodando nativamente** na porta 5432 | **Não** está no compose (serviço `postgresql-x64-17` no Windows). |
| **Chave da API da OpenAI** | Embeddings, re-ranking e geração. As chamadas são cobradas. |

### 1. Banco de dados

Com o PostgreSQL no ar, crie os dois bancos (o segundo é só para a suíte de testes):

```sql
CREATE DATABASE "rag-evaluation";
CREATE DATABASE "rag-evaluation-test";
```

Não é preciso rodar migração à mão: o `alembic upgrade head` roda no startup da API, junto com a
semeadura dos 4 pipelines e a criação das collections do Milvus.

### 2. Variáveis de ambiente da API

```bash
cd rag-evaluation-api
cp .env.example .env
```

Edite o `.env` e preencha **`CHAT_API_KEY`** com a sua chave da OpenAI. Ajuste `DB_USERNAME` /
`DB_PASSWORD` se o seu PostgreSQL não usa `postgres` / `admin`. O `.env` é gitignored.

As variáveis que mais importam:

| Variável | Padrão | Para que serve |
| --- | --- | --- |
| `CHAT_API_KEY` | *(vazio)* | **Obrigatória.** Sem ela a API nem sobe. |
| `CHAT_MODEL` | `gpt-4.1-mini` | Modelo de chat. **Não troque por um modelo de raciocínio**: eles rejeitam `temperature` e gastam reasoning tokens, contaminando a telemetria. |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Dimensão 1536, casada com o schema do Milvus. |
| `DB_URL` / `DB_NAME` / `DB_USERNAME` / `DB_PASSWORD` | `localhost:5432` / `rag-evaluation` / `postgres` / `admin` | Conexão do PostgreSQL. |
| `MAX_PERGUNTAS` | `10` | Perguntas respondidas por documento. |
| `MAX_UPLOAD_MB` | `25` | Tamanho máximo do arquivo enviado. |
| `PIPELINE_TIMEOUT_SECONDS` | `60` | Timeout de cada pipeline numa rodada. |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `800` / `150` | Chunking (idêntico nos 4 pipelines). |
| `RAG_SEARCH_LIMIT` | `5` | `top_k` inicial dos pipelines na semeadura. |
| `CORS_ORIGINS` | `http://localhost:4200,http://127.0.0.1:4200` | Origens liberadas para o front. |

### 3. Infraestrutura (Milvus + Docling)

```bash
cd rag-evaluation-api
docker compose up -d
```

O **Milvus leva ~90 segundos** para reportar `healthy`. Acompanhe com `docker compose ps`.

### 4. Subir a API

```bash
cd rag-evaluation-api
uv sync
uv run fastapi dev
```

- API em `http://127.0.0.1:8000`, Swagger em **`http://127.0.0.1:8000/docs`**.
- No Windows, se o banner colorido quebrar o console, prefixe com `PYTHONIOENCODING=utf-8`.

Confirme que tudo está no ar:

```bash
curl http://127.0.0.1:8000/api/health
```

A resposta traz um componente por dependência (`postgres`, `milvus`, `docling`) e devolve **503**
se algum estiver fora.

### 5. Subir o front-end

```bash
cd rag-evaluation-web
npm install
npm start
```

Aplicação em `http://localhost:4200`.

A URL da API fica em [`src/environments/environment.ts`](rag-evaluation-web/src/environments/environment.ts)
(`apiBaseUrl`, **com o sufixo `/api`**). Se você mudar a porta da API, mude ali — e lembre-se de
manter a origem do front em `CORS_ORIGINS` no `.env` do backend.

---

# Adicionando documentos ao acervo

O upload é **exclusivo do pesquisador** e feito pelo **Swagger** — não existe tela de administração,
de propósito: todos os avaliadores precisam enfrentar o mesmo corpus.

**Formatos aceitos:** `.pdf`, `.docx`, `.txt`, `.md`. **Tamanho máximo:** `MAX_UPLOAD_MB` (25 MB).
O arquivo **não é guardado** — só o `sha256`, para detectar envio duplicado.

## Pelo Swagger (recomendado)

1. Abra `http://127.0.0.1:8000/docs`.
2. Expanda **`POST /api/documents`** → **Try it out**.
3. Preencha os campos:

| Campo | Obrigatório | Regra | Exemplo |
| --- | --- | --- | --- |
| `arquivo` | sim | pdf, docx, txt ou md | `lgpd.pdf` |
| `slug` | sim | 2–64 caracteres, minúsculas, números e hífen (`^[a-z0-9][a-z0-9-]*$`); único. **É o que aparece na URL** `/avaliacao/:slug` | `lgpd` |
| `titulo` | sim | 2–200 caracteres, exibido no card | `Lei Geral de Proteção de Dados` |
| `area` | sim | 2–120 caracteres, mostrado acima do título | `Direito & Privacidade` |
| `descricao` | não | até 1000 caracteres | `Texto consolidado da Lei nº 13.709/2018.` |
| `icone` | não | um emoji para o card | `⚖️` |

4. **Execute.** A resposta é **202 Accepted**: a ingestão roda em segundo plano, nos 4 pipelines,
   cada um refazendo todo o trabalho (parsing → chunking → embedding → indexação).

## Pela linha de comando

```bash
curl -X POST http://127.0.0.1:8000/api/documents \
  -F "arquivo=@./lgpd.pdf;type=application/pdf" \
  -F "slug=lgpd" \
  -F "titulo=Lei Geral de Proteção de Dados" \
  -F "area=Direito & Privacidade" \
  -F "descricao=Texto consolidado da Lei nº 13.709/2018." \
  -F "icone=⚖️"
```

## Acompanhando a ingestão

```bash
# status geral (processando | pronto | erro_parcial)
curl http://127.0.0.1:8000/api/documents

# telemetria por pipeline: tempo de cada etapa, chunks, tokens e erro
curl http://127.0.0.1:8000/api/documents/{id}/ingestions
```

- O documento vira **`pronto`** — e **só então aparece para os avaliadores** — quando os **4**
  pipelines concluem.
- Se algum falhar, fica **`erro_parcial`** e continua invisível na tela de seleção. O motivo por
  pipeline aparece em `/ingestions` (causa mais comum: `docling-serve` fora do ar, o que derruba
  apenas os pipelines 2 e 4).
- Um PDF grande leva minutos: o Docling converte o documento inteiro antes de devolver.

## Removendo um documento

```bash
curl -X DELETE http://127.0.0.1:8000/api/documents/{id}
```

Remove os vetores das 4 collections do Milvus e apaga o documento no PostgreSQL em cascata —
inclusive as rodadas e escolhas já feitas sobre ele.

---

# Endpoints

| Método | Rota | Uso |
| --- | --- | --- |
| `GET` | `/api/health` | Postgres, Milvus e Docling de uma vez. |
| `POST` | `/api/documents` | Upload (pesquisador). **202**. |
| `GET` | `/api/documents?status=pronto` | Lista o acervo; o front sempre filtra por `pronto`. |
| `GET` | `/api/documents/{id}` | Detalhe do documento. |
| `GET` | `/api/documents/{id}/ingestions` | Telemetria de ingestão por pipeline (pesquisador). |
| `DELETE` | `/api/documents/{id}` | Remove do Postgres e do Milvus. |
| `POST` | `/api/sessions` | Cria a sessão anônima; corpo (perfil) é opcional. |
| `GET` | `/api/sessions/{id}/progress` | Respondidas por documento e total de concluídos. |
| `POST` | `/api/sessions/{sid}/documents/{slug}/questions` | Pergunta → rodada com as respostas cegas. |
| `GET` | `/api/sessions/{sid}/documents/{slug}/rounds` | Histórico, para reidratar o chat. |
| `POST` | `/api/rounds/{id}/choice` | Registra a escolha (`{"rotulo": "A"}`). |

Rotas administrativas usam o **UUID** do documento; as de avaliação usam o **slug**.

---

# Comandos

## Backend (`rag-evaluation-api/`)

```bash
uv sync                          # instala/atualiza dependências
docker compose up -d             # Milvus, etcd, MinIO e docling-serve
uv run fastapi dev               # dev server (migrações + seed no startup)
uv run pytest                    # suíte unitária e de contrato
uv run pytest -m integration     # exige o compose no ar e gasta OpenAI de verdade
uv run ruff check . --fix        # lint
uv run ruff format .             # formatação
uv run alembic revision --autogenerate -m "..."   # nova migração
```

Os testes de contrato usam o banco `rag-evaluation-test` (a fixture recria as tabelas a cada
execução). Os marcados como `integration` ficam **fora** da suíte padrão porque custam dinheiro.

## Front-end (`rag-evaluation-web/`)

```bash
npm start                        # dev server em http://localhost:4200
npm run build                    # build de produção em dist/
npm test                         # testes (Vitest via @angular/build:unit-test)
npx prettier --write .           # formatação
```

---

# Problemas comuns

| Sintoma | Causa provável e solução |
| --- | --- |
| API não sobe: erro de validação em `chat_api_key` | `CHAT_API_KEY` vazia no `.env`. |
| `/api/health` com `milvus: false` | O Milvus ainda está subindo (~90s) ou o compose não está no ar. |
| Documento parado em `erro_parcial` | Veja `/documents/{id}/ingestions`. Se o erro cita o Docling, confira `docker compose ps` — sem ele, pipelines 2 e 4 falham. |
| Front mostra "Não foi possível falar com o servidor" | API fora do ar, `apiBaseUrl` errado no `environment.ts`, ou a origem do front fora de `CORS_ORIGINS`. |
| Nenhum documento na tela de seleção | Nenhum documento está `pronto`; o front só lista `?status=pronto`. |
| Pergunta responde **502** | Algum pipeline falhou ou estourou `PIPELINE_TIMEOUT_SECONDS`. A rodada inteira é invalidada de propósito — escolher entre 3 respostas produziria um dado que não agrega com os demais. |
| Pergunta responde **409** | Há rodada pendente de escolha, o documento não está `pronto`, ou o limite de `MAX_PERGUNTAS` foi atingido. |

> **Custo:** cada pergunta dispara os 4 pipelines, e cada um faz embedding da query mais uma
> geração — os pipelines 3 e 4 ainda somam reescrita de query e re-ranking. A coleta consome
> créditos reais da OpenAI.

---

# Sistema visual

O front segue [`rag-evaluation-web/DESIGN.md`](rag-evaluation-web/DESIGN.md) (canvas creme + coral
+ navy, tipografia editorial serifada). Os tokens são espelhados como CSS custom properties em
`src/styles.css` — **nunca use hex inline nos componentes**. Fontes: Cormorant Garamond, Inter e
JetBrains Mono, carregadas do Google Fonts em `src/index.html`.
