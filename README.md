# RAG Evaluation

Aplicação em que avaliadores humanos escolhem, **às cegas**, a melhor resposta entre quatro
configurações de pipeline RAG sobre o mesmo documento.

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
| `pipeline-3` | raw | avançado: HyDE, híbrido (RRF), reordenação por cross-encoder, vizinhos |
| `pipeline-4` | Docling | avançado |

Comparar 1↔2 e 3↔4 isola o parser; comparar 1↔3 e 2↔4 isola o retrieval avançado.

**A avaliação às cegas é garantida pelo servidor:** nenhum schema de resposta da avaliação tem
campo `pipeline` — a identidade não existe no JSON que chega ao navegador. Cada rodada sorteia os
rótulos A/B/C/D de novo, então a posição também não é pista.

## Parâmetros do estudo

| Parâmetro | Valor |
| --- | --- |
| Contexto entregue ao LLM | **15 chunks nos 4 pipelines** |
| Pipelines 1 e 2 | busca densa, `top_k` 15 |
| Pipelines 3 e 4 | 20 candidatos → reordenação → 5 âncoras + vizinhos (±1); se faltar, os próximos do ranking completam 15 |
| HyDE | média dos vetores do parágrafo hipotético e da pergunta; o BM25 usa só a pergunta |
| Fusão híbrida | `RRFRanker` (k = 60), padrão do Milvus; BM25 com k1 = 1,2 e b = 0,75 |
| Reordenador | `BAAI/bge-reranker-v2-m3`, local, revisão fixa no compose, recebendo a pergunta original |
| Segmentação | 256 tokens (`cl100k_base`) em frases inteiras, sem sobreposição, igual nos dois parsers |
| Índice denso | `FLAT` com cosseno: busca exata, sem parâmetros |
| Docling | `pypdfium2`, tabelas `accurate`, sem OCR, descrição de imagens com `gpt-4.1-mini` (área mínima 5%) |
| Geração | `gpt-4.1-mini`, temperatura 0,3, até 1024 tokens |
| Embedding | `text-embedding-3-small` (1536) |
| Juiz RAGAS | `RAGAS_LLM_MODEL`, sempre diferente do modelo de geração |

## Fluxo do avaliador

1. **Boas-vindas** (`/`) — explicação e **aceite do termo**, que cria a sessão. Sem estudo aberto, ninguém começa.
2. **Seleção de documento** (`/documentos`) — só documentos com ingestão concluída nos 4 pipelines.
3. **Avaliação** (`/avaliacao/:slug`) — pergunta → 4 respostas anônimas → escolha da melhor ou
   "nenhuma está correta".

Até **10 perguntas respondidas por documento** (`MAX_PERGUNTAS`), por estudo; o limite é imposto pelo
servidor. Só rodada **decidida** conta — perguntar e abandonar não consome a cota. O `sessionId` fica
no `sessionStorage` do navegador, então recarregar a página não perde o progresso.

**Tempo da rodada:** medido no navegador, da abertura do documento ou da escolha anterior até a
escolha seguinte. A espera pela geração e o tempo com a aba oculta ficam em colunas próprias.

> **TODO:** identificar o avaliador por login. Hoje, fechar a aba cria outra sessão, e as rotas
> `/admin` estão abertas: qualquer pessoa que digite a URL vê os pipelines.

---

# Subindo tudo de uma vez

Com o `.env` da API preenchido (seção 2 abaixo), rode na raiz do repositório:

```powershell
powershell -ExecutionPolicy Bypass -File .\subir.ps1
```

O script abre o Docker Desktop se precisar, sobe os containers, espera cada serviço responder, inicia a API e o front em janelas próprias
e abre `http://localhost:4200/admin`. Use `-SemNavegador` para não abrir o navegador.

- **Primeira vez:** instala o que faltar e baixa o reordenador (2,2 GB), o que pode levar vários minutos.
  Para instalar as dependências da API, ele precisa do `uv`.
- **Rodar de novo:** o que já está no ar é mantido, então é seguro repetir.
- **Para parar:** feche as janelas `RAG - API` e `RAG - Web` e rode `docker compose stop` em
  `rag-evaluation-api/`. Os dados continuam salvos.

# Configuração

## Pré-requisitos

| Requisito | Observação |
| --- | --- |
| **Python 3.12 ou 3.13** e [`uv`](https://docs.astral.sh/uv/) | `pip install uv` resolve, se não tiver. O `uv` baixa o Python 3.12 fixado no projeto. |
| **Node.js 20+** e npm | Para o front-end Angular. |
| **Docker + Compose** | Sobe PostgreSQL 17 (porta 5432), Milvus, etcd, MinIO e docling-serve. |
| **Chave da API da OpenAI** | Embeddings, HyDE, geração, descrição de imagens e RAGAS. As chamadas são cobradas. |
| **Memória e disco** | O reordenador baixa 2,2 GB na primeira subida e usa cerca de 2,7 GB de RAM. O Docker precisa de pelo menos 8 GB. |

### 1. Banco de dados

O container `rag-postgres` cria o banco `rag-evaluation` na primeira subida, com os dados no volume
Docker `postgres-data`. A suíte de integração usa outro banco, que precisa ser criado à mão:

```bash
docker exec rag-postgres psql -U postgres -c 'CREATE DATABASE "rag-evaluation-test"'
```

Não é preciso rodar migração à mão: o `alembic upgrade head` roda no startup da API, junto com a
semeadura dos 4 pipelines e a criação das collections do Milvus.

### 2. Variáveis de ambiente da API

Toda a configuração fica em um único arquivo, `rag-evaluation-api/.env`, lido pela API e pelo
`docker compose`. Ele não é versionado porque guarda a sua chave da OpenAI. Em um clone novo, crie o
arquivo com o conteúdo abaixo e preencha `CHAT_API_KEY`:

```dotenv
# OpenAI: chat (a mesma chave também é usada nos embeddings e no RAGAS)
CHAT_API_KEY=
CHAT_MODEL=gpt-4.1-mini
CHAT_BASE_URL=https://api.openai.com/v1
CHAT_TEMPERATURE=0.3
CHAT_MAX_TOKENS=1024

# OpenAI: embeddings
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_MODEL_QUERY=text-embedding-3-small
EMBEDDING_URL=https://api.openai.com/v1
EMBEDDING_DIMENSIONS=1536

# PostgreSQL (container rag-postgres)
DB_NAME=rag-evaluation
DB_URL=postgresql://localhost:5432
DB_USERNAME=postgres
DB_PASSWORD=admin

# Milvus
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_USERNAME=root
MILVUS_PASSWORD=Milvus
MILVUS_DATABASE_NAME=default
MILVUS_COLLECTION_NAME_1=evaluation1
MILVUS_COLLECTION_NAME_2=evaluation2
MILVUS_COLLECTION_NAME_3=evaluation3
MILVUS_COLLECTION_NAME_4=evaluation4

# Docling
DOCLING_URL=http://localhost:5001
DOCLING_TIMEOUT_SECONDS=1800
DOCLING_DO_OCR=false
# Só com antivírus que inspeciona HTTPS (veja Problemas comuns)
DOCLING_CA_BUNDLE=

# Reordenador local
RERANKER_URL=http://localhost:8081
RERANKER_MODEL=BAAI/bge-reranker-v2-m3

# RAGAS
RAGAS_LLM_MODEL=gpt-4.1

# RAG e limites do estudo
RAG_SEARCH_LIMIT=15
RAG_ANCORAS=5
CHUNK_SIZE=256
CHUNK_OVERLAP=0
RERANK_CANDIDATES=20
SLIDING_WINDOW_SIZE=1
PIPELINE_TIMEOUT_SECONDS=300
MAX_PERGUNTAS=10
MAX_UPLOAD_MB=25

# Front-end
CORS_ORIGINS=http://localhost:4200,http://127.0.0.1:4200
```

`CHAT_API_KEY` é obrigatória: sem ela, a API não sobe. O estudo só abre com o reordenador no ar. As demais têm valor padrão no código, mas
mantenha-as no arquivo para deixar a configuração do estudo explícita.

| Variável | Para que serve |
| --- | --- |
| `CHAT_API_KEY` | Chave da OpenAI. As chamadas são cobradas. |
| `CHAT_MODEL` | Modelo de geração. **Não troque por um modelo de raciocínio**: eles rejeitam `temperature` e gastam reasoning tokens, contaminando a telemetria. |
| `CHAT_BASE_URL` / `CHAT_TEMPERATURE` / `CHAT_MAX_TOKENS` | Endpoint e parâmetros da geração. |
| `EMBEDDING_MODEL` / `EMBEDDING_MODEL_QUERY` | Modelos de embedding de documentos e de consultas. |
| `EMBEDDING_URL` / `EMBEDDING_DIMENSIONS` | Endpoint e dimensão dos embeddings. A dimensão precisa casar com o schema do Milvus. |
| `DB_URL` / `DB_NAME` / `DB_USERNAME` / `DB_PASSWORD` | Conexão do PostgreSQL. O compose usa as três últimas para criar o banco, apenas na primeira subida; trocá-las depois não altera um banco que já existe. |
| `MILVUS_HOST` / `MILVUS_PORT` / `MILVUS_USERNAME` / `MILVUS_PASSWORD` / `MILVUS_DATABASE_NAME` | Conexão do Milvus. |
| `MILVUS_COLLECTION_NAME_1` a `MILVUS_COLLECTION_NAME_4` | Collection de cada um dos 4 pipelines. |
| `DOCLING_URL` / `DOCLING_TIMEOUT_SECONDS` | Endereço e timeout do docling-serve. |
| `DOCLING_DO_OCR` | Mantenha `false`: os documentos são PDFs digitais, e o OCR tornaria o tempo de ingestão incomparável ao do parser raw. |
| `RAGAS_LLM_MODEL` | Modelo juiz do RAGAS, diferente do modelo de geração para evitar autopromoção. |
| `RAG_SEARCH_LIMIT` / `RAG_ANCORAS` | Chunks entregues ao LLM e âncoras dos pipelines 3 e 4, na semeadura. |
| `RERANKER_URL` / `RERANKER_MODEL` | Endereço do container `rag-reranker` e nome gravado na telemetria. O modelo em si é definido no compose. |
| `DOCLING_CA_BUNDLE` | Caminho, dentro do container, do bundle de certificados. |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | Chunking em tokens, idêntico nos 4 pipelines. Mudar exige reingerir o acervo. |
| `RERANK_CANDIDATES` / `SLIDING_WINDOW_SIZE` | Candidatos antes da reordenação e vizinhos de cada lado da âncora. |
| `PIPELINE_TIMEOUT_SECONDS` | Timeout de cada pipeline em uma rodada. |
| `MAX_PERGUNTAS` | Perguntas respondidas por documento. |
| `MAX_UPLOAD_MB` | Tamanho máximo do arquivo enviado. |
| `CORS_ORIGINS` | Origens liberadas para o front, separadas por vírgula. |

### 3. Infraestrutura (PostgreSQL, Milvus e Docling)

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

# Gerenciamento (`/admin`)

O menu superior leva a esta área em todas as telas, e ela **não tem senha nesta fase**. Antes da coleta, é preciso esconder esses links do avaliador, porque a área revela os pipelines.

- **Estudos:** só com um estudo aberto o avaliador responde. Encerrado, os dados ficam congelados nele,
  e o próximo começa zerado. O acervo é compartilhado entre estudos.
- **Documentos:** envio de **PDF digital** (até `MAX_UPLOAD_MB`), status da ingestão, contagem de
  páginas, tabelas e imagens. O arquivo **não é guardado**, só o `sha256`. Documento com rodadas não
  pode ser excluído.
- **Pipelines:** CRUD com a configuração em JSON. Com estudo aberto, nada muda. O braço de controle
  não liga técnicas avançadas. Cada resposta guarda um snapshot da configuração usada.
- **Avaliações:** navega nas perguntas de um ciclo e mostra respostas, pipeline, escolha, tempos,
  tokens, custo e os chunks de cada etapa (denso, BM25, fusão, reordenação, contexto final), com
  ordem, scores e conteúdo.
- **Resultados:** taxa de vitória, H1 a H3, viés de posição, fadiga, custo, RAGAS e exportação em CSV.

O documento vira `pronto` quando os 4 pipelines concluem. Com falha em algum, fica `erro_parcial`,
fora da tela de seleção, e o motivo aparece em **Exibir detalhes**. Imagem acima do limiar sem descrição
conta como falha: o Docling responde `success` mesmo quando o VLM falha.

## Análise

Cada efeito é um teste binário por rodada contra 50%: a vencedora usou Docling (H1)? Usou recuperação
avançada (H2)? Está na diagonal 1 e 4 (H3)? Rodadas "nenhuma" ficam fora e são reportadas à parte. A
API dá IC de Wilson, IC por bootstrap de avaliadores e binomial exato. O modelo misto, com avaliador e
documento como efeitos aleatórios, é `analise/modelo_misto.R`, sobre o CSV:

```bash
Rscript rag-evaluation-api/analise/modelo_misto.R estudo.csv
```

## RAGAS

Um LLM juiz dá três notas, de 0 a 1, sem resposta de referência: **fidelidade** (a resposta se apoia
nos trechos?), **relevância** (ela responde à pergunta?) e **precisão do contexto** (os trechos
servem?). A concordância mede em quantas rodadas o pipeline de maior nota foi o escolhido, contra 25%
ao acaso. O cálculo é disparado pelo admin, fora do fluxo do avaliador, porque custa dezenas de
chamadas por rodada.

---

# Endpoints

| Método | Rota | Uso |
| --- | --- | --- |
| `GET` | `/api/health` | Postgres, Milvus e Docling de uma vez. |
| `GET` `POST` | `/api/studies` | Lista e abre estudos. |
| `GET` | `/api/studies/atual` | Estudo aberto, ou `null`. |
| `POST` | `/api/studies/{id}/encerrar` | Encerra o estudo. |
| `POST` `GET` | `/api/documents` | Upload de PDF (**202**) e listagem; o avaliador filtra por `status=pronto`. |
| `GET` `DELETE` | `/api/documents/{id}` | Detalhe e remoção. |
| `GET` | `/api/documents/{id}/ingestions` | Telemetria de ingestão por pipeline. |
| `GET` `POST` | `/api/pipelines` | CRUD dos pipelines. |
| `GET` `PUT` `DELETE` | `/api/pipelines/{id}` | CRUD dos pipelines. |
| `POST` | `/api/sessions` | Cria a sessão: `{"aceite": true, "termo_versao": "..."}`. |
| `GET` | `/api/sessions/{id}/progress` | Respondidas por documento. |
| `POST` | `/api/sessions/{sid}/documents/{slug}/questions` | Pergunta → rodada com as respostas cegas. |
| `GET` | `/api/sessions/{sid}/documents/{slug}/rounds` | Histórico, para reidratar o chat. |
| `POST` | `/api/rounds/{id}/choice` | Escolha e tempos; `rotulo: null` = nenhuma está correta. |
| `GET` | `/api/admin/studies/{id}/avaliacoes` | Ciclos do estudo. |
| `GET` | `/api/admin/avaliacoes/{sid}/{documentId}` | Detalhe completo de um ciclo. |
| `GET` | `/api/admin/studies/{id}/stats` | Análise do estudo. |
| `GET` | `/api/admin/studies/{id}/export.csv` | Uma linha por rodada × pipeline. |
| `POST` | `/api/admin/studies/{id}/ragas` | RAGAS do estudo, em segundo plano. |
| `GET` | `/api/admin/studies/{id}/ragas` | Andamento do RAGAS do estudo. |
| `POST` | `/api/admin/rounds/{id}/ragas` | RAGAS de uma rodada. |

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
| O reordenador demora a responder ao subir | Ele leva cerca de 2 minutos para carregar. O estudo só abre com ele no ar (`docker logs rag-reranker`). |
| Front mostra "Não foi possível falar com o servidor" | API fora do ar, `apiBaseUrl` errado no `environment.ts`, ou a origem do front fora de `CORS_ORIGINS`. |
| Nenhum documento na tela de seleção | Nenhum documento está `pronto`; o front só lista `?status=pronto`. |
| Pergunta responde **502** | Algum pipeline falhou ou estourou `PIPELINE_TIMEOUT_SECONDS`. A rodada inteira é invalidada de propósito — escolher entre 3 respostas produziria um dado que não agrega com os demais. |
| Pergunta responde **409** | Há rodada pendente de escolha, o documento não está `pronto`, o limite de `MAX_PERGUNTAS` foi atingido ou o estudo foi encerrado. |
| Documento em `erro_parcial`: "O VLM não descreveu N imagens" | Veja `docker logs rag-docling`. Com `CERTIFICATE_VERIFY_FAILED`, o antivírus inspeciona HTTPS: junte a raiz dele ao bundle do `certifi` em `rag-evaluation-api/volumes/certs/ca-bundle.pem`, defina `DOCLING_CA_BUNDLE=/certs/ca-bundle.pem` e rode `docker compose up -d docling`. |
| Índice ou tamanho de chunk mudou | As collections só são criadas se não existirem: é preciso removê-las e reingerir o acervo. |

> **Custo:** cada pergunta dispara os 4 pipelines, e cada um faz embedding da query mais uma
> geração — os pipelines 3 e 4 ainda somam HyDE e a reordenação local. A coleta consome créditos
> reais da OpenAI, e cada PDF com imagens gasta chamadas de visão em dois pipelines.
>
> **Tempo:** em CPU, a reordenação é o gargalo: quase 1 s por candidato de 256 tokens, em fila. Avaliadores
> simultâneos somam a espera. O tempo da etapa inclui a fila; para medir o custo da reordenação, meça-a isolada.

---

# Sistema visual

O front segue [`rag-evaluation-web/DESIGN.md`](rag-evaluation-web/DESIGN.md) (tipografia editorial
serifada, com a paleta da Procempa). Os tokens são espelhados como CSS custom properties em
`src/styles.css` — **nunca use hex inline nos componentes**. Fontes: Cormorant Garamond, Inter e
JetBrains Mono, carregadas do Google Fonts em `src/index.html`.
