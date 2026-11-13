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
| Contexto entregue ao LLM | **6 chunks nos 4 pipelines** (≈ 1.500 tokens) |
| Pipelines 1 e 2 | busca densa, `top_k` 6 |
| Pipelines 3 e 4 | 20 candidatos → reordenação → 2 âncoras + vizinhos (±1); se faltar, os próximos do ranking completam 6 |
| HyDE | média dos vetores do parágrafo hipotético e da pergunta; o BM25 usa só a pergunta |
| Fusão híbrida | `RRFRanker` (k = 60), padrão do Milvus; BM25 com k1 = 1,2 e b = 0,75 |
| Reordenador | `bge-reranker-v2-m3`, em serviço próprio no formato `/v1/rerank`, recebendo a pergunta original |
| Segmentação | 256 tokens (`cl100k_base`) em frases inteiras, sem sobreposição, igual nos dois parsers |
| Índice denso | `FLAT` com cosseno: busca exata, sem parâmetros |
| Parser raw | `pypdf`, sem estrutura; páginas com bytes nulos fora das strings (export do dompdf, usado pelo BookStack) são reparadas e lidas de novo, e ficam em `paginas_reparadas` nos metadados da ingestão |
| Docling | `pypdfium2`, tabelas `accurate`, sem OCR, descrição de imagens com `DOCLING_IMAGEM_MODELO` (área mínima 5%) |
| Geração | `CHAT_MODEL`, temperatura 0,3, até 1024 tokens |
| Embedding | `EMBEDDING_MODEL` para os trechos e `EMBEDDING_MODEL_QUERY` para a pergunta, com `EMBEDDING_DIMENSIONS` dimensões |
| Juiz RAGAS | `RAGAS_LLM_MODEL`, sempre diferente do modelo de geração |

**Por que 6 chunks.** A busca é filtrada por documento, então o acervo de cada pergunta é um único
documento. Um documento de 20 a 30 páginas rende, por estimativa (600 a 900 tokens por página em
português), de 50 a 100 chunks de 256 tokens; o valor medido de cada documento aparece na listagem
de documentos da área de administração. Com 15 chunks, o LLM recebia de 15% a 30% do documento: a
busca densa simples (pipelines 1 e 2) quase sempre já trazia o trecho certo, e restava pouco para o
retrieval avançado ganhar (efeito teto). Com 20 candidatos para 15 entregues, a reordenação quase
não filtrava, e o contexto dos pipelines 3 e 4 era praticamente o mesmo dos pipelines 1 e 2. Com 6
chunks, o LLM recebe cerca de 1.500 tokens (de 6% a 12% do documento, estimados) e o reordenador
escolhe 2 âncoras entre 20, uma seleção de fato. A relação âncoras × (2 · janela + 1) = total se
mantém: 2 âncoras ± 1 vizinho = 6 (antes, 5 × 3 = 15). O custo assumido é que perguntas de síntese,
que dependem de vários trechos espalhados, ficam mais difíceis nos quatro pipelines; a alternativa
intermediária seria 9 chunks e 3 âncoras. A mudança não exige reingestão (só `CHUNK_SIZE` e
`CHUNK_OVERLAP` exigem).

## Fluxo do avaliador

1. **Boas-vindas** (`/`) — explicação e **aceite do termo**, que cria a sessão. Sem estudo aberto, ninguém começa.
2. **Seleção de documento** (`/documentos`) — só documentos com ingestão concluída nos 4 pipelines.
3. **Avaliação** (`/avaliacao/:slug`) — pergunta → 4 respostas anônimas → escolha da melhor ou
   "nenhuma está correta" → se escolheu uma, na mesma tela, quais das outras três **também estão
   corretas** (caixas de marcação, ou "Nenhuma das outras está correta") → próxima pergunta.

Até **10 perguntas respondidas por documento** (`MAX_PERGUNTAS`), por estudo; o limite é imposto pelo
servidor. Só rodada **decidida** (com escolha) conta — perguntar e abandonar não consome a cota. Mas só
rodada **completa** (decidida e, se houve vencedora, com a marcação das outras) libera a próxima
pergunta. A marcação complementa a escolha, não a troca: a escolhida fica travada. O `sessionId` fica no
`sessionStorage` do navegador, então recarregar a página não perde o progresso; um F5 entre a escolha e
a marcação retoma na marcação.

**Tempo da rodada:** medido no navegador, da abertura do documento ou do fim da rodada anterior até a
escolha. A espera pela geração e o tempo com a aba oculta ficam em colunas próprias. A marcação das
outras respostas tem tempo próprio (total e aba oculta), fora do tempo da rodada.

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

- **Primeira vez:** instala o que faltar e baixa as imagens do Docker, o que pode levar vários minutos.
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
| **Serviços de modelo** | Chat, embeddings, reordenador e juiz do RAGAS, todos por HTTP. O chat, os embeddings e o juiz falam o formato da OpenAI; o reordenador, o `/v1/rerank`. Podem ser serviços internos. |

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
`docker compose`. Ele não é versionado porque guarda as chaves dos serviços. Em um clone novo, crie o
arquivo com o conteúdo abaixo e preencha os endereços, os modelos e as chaves do seu ambiente:

```dotenv
# Chat, no formato da OpenAI (a mesma chave também é enviada aos embeddings)
CHAT_API_KEY=
CHAT_MODEL=
CHAT_BASE_URL=https://seu-servico-de-chat/v1
CHAT_TEMPERATURE=0.3
CHAT_MAX_TOKENS=1024

# Embeddings, no formato da OpenAI
EMBEDDING_MODEL=
EMBEDDING_MODEL_QUERY=
EMBEDDING_URL=https://seu-servico-de-embeddings/v1
EMBEDDING_DIMENSIONS=2048

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

# MinIO (container rag-minio, guarda os PDFs)
MINIO_URL=http://localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET_DOCUMENTOS=documentos

# Docling
DOCLING_URL=http://localhost:5001
DOCLING_TIMEOUT_SECONDS=1800
DOCLING_DO_OCR=false
DOCLING_PDF_BACKEND=pypdfium2
DOCLING_TABLE_MODE=accurate
DOCLING_DESCREVER_IMAGENS=true
DOCLING_IMAGEM_AREA_MINIMA=0.05
DOCLING_IMAGEM_MODELO=

# Reordenador (endpoint completo; a chave vai como Bearer)
RERANKER_URL=https://seu-reordenador/v1/rerank
RERANKER_KEY=

# RAGAS: o juiz roda em serviço próprio (sem RAGAS_LLM_KEY, vale a chave do chat)
RAGAS_LLM_MODEL=
RAGAS_LLM_URL=https://seu-servico-do-juiz/v1
RAGAS_LLM_KEY=
RAGAS_LLM_SEM_RACIOCINIO=false
RAGAS_TIMEOUT_SECONDS=120

# RAG e limites do estudo
RAG_SEARCH_LIMIT=6
RAG_ANCORAS=2
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
| `CHAT_API_KEY` | Chave do serviço de chat, enviada também ao de embeddings. |
| `CHAT_MODEL` | Modelo de geração. **Não troque por um modelo de raciocínio**: eles rejeitam `temperature` e gastam reasoning tokens, contaminando a telemetria. |
| `CHAT_BASE_URL` / `CHAT_TEMPERATURE` / `CHAT_MAX_TOKENS` | Endpoint (terminando em `/v1`) e parâmetros da geração. O Docling chama este mesmo endpoint para descrever imagens, então ele precisa ser alcançável a partir do docling-serve. |
| `EMBEDDING_MODEL` / `EMBEDDING_MODEL_QUERY` | Modelo usado para embutir os trechos na ingestão e modelo usado para embutir a pergunta. Em modelos assimétricos (como o `nv-embedqa`, com sufixos `-passage` e `-query`) os dois nomes diferem. |
| `EMBEDDING_URL` / `EMBEDDING_DIMENSIONS` | Endpoint (terminando em `/v1`) e dimensão dos embeddings. A dimensão precisa casar com o schema do Milvus: mudar exige remover as collections e reingerir. |
| `DB_URL` / `DB_NAME` / `DB_USERNAME` / `DB_PASSWORD` | Conexão do PostgreSQL. O compose usa as três últimas para criar o banco, apenas na primeira subida; trocá-las depois não altera um banco que já existe. |
| `MILVUS_HOST` / `MILVUS_PORT` / `MILVUS_USERNAME` / `MILVUS_PASSWORD` / `MILVUS_DATABASE_NAME` | Conexão do Milvus. |
| `MILVUS_COLLECTION_NAME_1` a `MILVUS_COLLECTION_NAME_4` | Collection de cada um dos 4 pipelines. |
| `MINIO_URL` / `MINIO_BUCKET_DOCUMENTOS` | URL da API do MinIO (porta 9000, não a do console) e bucket onde os PDFs enviados ficam guardados. |
| `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | Credenciais do MinIO. Precisam ser iguais às do `docker-compose.yml`, que o Milvus também usa. |
| `DOCLING_URL` / `DOCLING_TIMEOUT_SECONDS` | Endereço e timeout do docling-serve. |
| `DOCLING_DO_OCR` | Mantenha `false`: os documentos são PDFs digitais, e o OCR tornaria o tempo de ingestão incomparável ao do parser raw. |
| `RAGAS_LLM_MODEL` / `RAGAS_LLM_URL` / `RAGAS_LLM_KEY` | Modelo juiz do RAGAS, o endpoint dele (terminando em `/v1`) e a chave. O juiz é diferente do modelo de geração para evitar autopromoção. Sem `RAGAS_LLM_KEY`, vale `CHAT_API_KEY`. |
| `RAGAS_LLM_SEM_RACIOCINIO` | `true` quando o juiz é um modelo de raciocínio servido por vLLM/SGLang (DeepSeek, Qwen): envia `chat_template_kwargs.enable_thinking=false`. Ligado, o juiz responde cerca de 7× mais rápido. Desligado, o raciocínio esgota o `max_tokens` nas respostas longas e a nota sai com `IncompleteOutputException`. Deixe `false` na API da OpenAI, que rejeita o parâmetro. |
| `RAGAS_TIMEOUT_SECONDS` | Limite de cada chamada ao juiz. Sem ele, uma chamada sem resposta prenderia o lote por até 30 min. |
| `RAG_SEARCH_LIMIT` / `RAG_ANCORAS` | Chunks entregues ao LLM e âncoras dos pipelines 3 e 4, na semeadura. Só valem para pipelines criados depois: os já semeados guardam `top_k` e `ancoras` na própria configuração, que se altera na tela de pipelines da administração (com o estudo encerrado). |
| `RERANKER_URL` / `RERANKER_KEY` | Endpoint completo do reordenador (`.../v1/rerank`) e a chave, enviada como `Authorization: Bearer`. O nome do modelo e os tokens gravados na telemetria vêm da resposta do serviço. |
| `DOCLING_PDF_BACKEND` / `DOCLING_TABLE_MODE` | Backend de leitura do PDF e modo de extração de tabelas. Afetam o parser, um dos fatores do estudo: não altere depois de ingerir os documentos. |
| `DOCLING_DESCREVER_IMAGENS` / `DOCLING_IMAGEM_AREA_MINIMA` / `DOCLING_IMAGEM_MODELO` | Se as imagens são descritas, a área mínima (fração da página) para descrever e o modelo usado. Também afetam o parser. |
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

Interfaces para inspecionar os dados:

| Interface | URL | O que mostra |
|---|---|---|
| Attu | `http://localhost:3000` | Collections do Milvus. |
| Console do MinIO | `http://localhost:9001` (login `minioadmin` / `minioadmin`) | PDFs enviados, no bucket `documentos`. O `a-bucket` guarda os arquivos internos do Milvus. |

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

O front não depende de ser servido na raiz do host. Atrás de um proxy que publique o app sob um prefixo,
removendo-o do path e enviando `X-Forwarded-Prefix`, o `<base href>` do `index.html` passa a ser esse
prefixo. O login e o logout voltam para ele.

---

# Gerenciamento (`/admin`)

O menu superior leva a esta área em todas as telas, e ela **não tem senha nesta fase**. Antes da coleta, é preciso esconder esses links do avaliador, porque a área revela os pipelines.

- **Estudos:** só com um estudo aberto o avaliador responde. Encerrado, os dados ficam congelados nele,
  e o próximo começa zerado. O acervo é compartilhado entre estudos.
- **Documentos:** envio de **PDF digital** (até `MAX_UPLOAD_MB`), status da ingestão, contagem de
  páginas, tabelas e imagens. O PDF fica guardado no MinIO e o avaliador pode abri-lo na tela da avaliação.
  Documento enviado antes disso aparece com o botão "Anexar PDF", que só aceita o mesmo arquivo. Documento
  com rodadas não pode ser excluído.
- **Pipelines:** CRUD com a configuração em JSON. Com estudo aberto, nada muda. O braço de controle
  não liga técnicas avançadas. Cada resposta guarda um snapshot da configuração usada.
- **Avaliações:** navega nas perguntas de um ciclo e mostra respostas, pipeline, escolha, as outras
  marcadas como também corretas, tempos (inclusive o da marcação),
  tokens, custo e os chunks de cada etapa (denso, BM25, fusão, reordenação, contexto final), com
  ordem, scores e conteúdo.
- **Resultados:** taxa de vitória, H1 a H3, taxa de correção, viés de posição (na escolha e na
  marcação), fadiga, custo, RAGAS e exportação em CSV.

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

A marcação das outras respostas dá medidas **secundárias**, que não substituem os testes sobre a
vencedora:

- **Taxa de correção por pipeline:** proporção de respostas corretas nas rodadas completas, contando as
  quatro de cada rodada (a vencedora é correta, as outras valem a marcação, "nenhuma" vale quatro
  incorretas). Como as quatro respostas de uma rodada não são independentes, há IC por bootstrap de
  avaliadores além do Wilson. Rodadas com vencedora ainda sem marcação ficam fora, contadas à parte.
- **Marcação por posição:** entre as não escolhidas, a marcada depende da posição exibida?
  Qui-quadrado de homogeneidade, 3 graus de liberdade.
- **Uniformidade da marcação por avaliador:** quem marca sempre todas ou sempre nenhuma, para revisar.

O CSV ganha, no fim, `tambem_correta`, `correta`, `marcado_em`, `tempo_marcacao_ms` e
`tempo_marcacao_oculto_ms`.

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
| `GET` `PUT` | `/api/documents/{id}/arquivo` | Abre o PDF guardado; o `PUT` anexa o arquivo a um documento antigo, sem refazer a ingestão. |
| `GET` | `/api/documents/{id}/ingestions` | Telemetria de ingestão por pipeline, com `contexto_chunks` e `contexto_percentual` (fração do documento entregue ao LLM). |
| `GET` `POST` | `/api/pipelines` | CRUD dos pipelines. |
| `GET` `PUT` `DELETE` | `/api/pipelines/{id}` | CRUD dos pipelines. |
| `POST` | `/api/sessions` | Cria a sessão: `{"aceite": true, "termo_versao": "..."}`. |
| `GET` | `/api/sessions/{id}/progress` | Respondidas por documento. |
| `POST` | `/api/sessions/{sid}/documents/{slug}/questions` | Pergunta → rodada com as respostas cegas. |
| `GET` | `/api/sessions/{sid}/documents/{slug}/rounds` | Histórico, para reidratar o chat. |
| `POST` | `/api/rounds/{id}/choice` | Escolha e tempos; `rotulo: null` = nenhuma está correta. |
| `POST` | `/api/rounds/{id}/also-correct` | Segundo passo: `{"rotulos": ["B", "D"], "tempo_marcacao_ms": ..., "tempo_marcacao_oculto_ms": ...}`; lista vazia = nenhuma das outras está correta. Só em rodada decidida com vencedora e ainda sem marcação. |
| `GET` | `/api/admin/documents` | Acervo do pesquisador: a listagem de documentos mais `contexto` (chunks entregues ao LLM, tokens estimados e faixa do percentual do documento entre os pipelines ativos). |
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
uv run pytest -m integration     # exige a infraestrutura no ar e chama os modelos de verdade
uv run ruff check . --fix        # lint
uv run ruff format .             # formatação
uv run alembic revision --autogenerate -m "..."   # nova migração
```

Os testes de contrato usam o banco `rag-evaluation-test` (a fixture recria as tabelas a cada
execução). Os marcados como `integration` ficam **fora** da suíte padrão porque dependem dos serviços externos.

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
| Estudo não abre: "O reordenador não está no ar" | A API consulta `/health` na raiz do host de `RERANKER_URL`. Confira o endereço e se o serviço responde. Um 401 na pergunta indica `RERANKER_KEY` errada. |
| Front mostra "Não foi possível falar com o servidor" | API fora do ar, `apiBaseUrl` errado no `environment.ts`, ou a origem do front fora de `CORS_ORIGINS`. |
| Nenhum documento na tela de seleção | Nenhum documento está `pronto`; o front só lista `?status=pronto`. |
| Pergunta responde **502** | Algum pipeline falhou ou estourou `PIPELINE_TIMEOUT_SECONDS`. A rodada inteira é invalidada de propósito — escolher entre 3 respostas produziria um dado que não agrega com os demais. |
| Pergunta responde **409** | Há rodada pendente de escolha ou da marcação das outras respostas, o documento não está `pronto`, o limite de `MAX_PERGUNTAS` foi atingido ou o estudo foi encerrado. |
| Documento em `erro_parcial`: "O VLM não descreveu N imagens" | Veja os logs do docling-serve. Quem chama o modelo de visão é ele, não a API: `CHAT_BASE_URL` precisa ser alcançável de lá, e `DOCLING_IMAGEM_MODELO` precisa aceitar imagens. |
| Índice ou tamanho de chunk mudou | As collections só são criadas se não existirem: é preciso removê-las e reingerir o acervo. |

> **Custo:** cada pergunta dispara os 4 pipelines, e cada um faz embedding da query mais uma
> geração — os pipelines 3 e 4 ainda somam HyDE e a reordenação. O estudo mede esse custo em
> tempo e tokens, não em dinheiro; cada PDF com imagens gasta chamadas de visão em dois pipelines.
>
> **Tempo:** em CPU, a reordenação é o gargalo: quase 1 s por candidato de 256 tokens, em fila. Avaliadores
> simultâneos somam a espera. O tempo da etapa inclui a fila; para medir o custo da reordenação, meça-a isolada.

---

# Sistema visual

O front segue [`rag-evaluation-web/DESIGN.md`](rag-evaluation-web/DESIGN.md) (tipografia editorial
serifada, com a paleta alterada para tons azuis). Os tokens são espelhados como CSS custom properties em
`src/styles.css` — **nunca use hex inline nos componentes**. Fontes: Cormorant Garamond, Inter e
JetBrains Mono, carregadas do Google Fonts em `src/index.html`.
