# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv sync                              # Install dependencies (Python 3.12)
docker compose up -d                 # Start PostgreSQL (5432), ChromaDB (8000), Ollama (11435)
uv run fastapi dev app/main.py       # FastAPI dev server → http://localhost:8001
uv run langgraph dev                 # LangGraph dev server (agents only)

# Useful debug commands
docker exec -it kantuta_ollama ollama list       # Check loaded models
psql -h localhost -U kantuta -d kantuta_db       # Direct DB access
```

There are no automated tests. Evaluation notebooks live in `ai/test/`.

## Architecture

### Entry Point & Lifespan (`app/main.py`)

The FastAPI lifespan initializes two things on startup:
1. SQLModel table creation (`init_db()`)
2. A `AsyncPostgresSaver` LangGraph checkpointer backed by the same PostgreSQL DB

The checkpointer is stored on `app.state.checkpointer` and accessed in routers via `request.app.state.checkpointer`. This means **conversation memory for every chat thread is persisted in PostgreSQL**, not in memory.

### Database Session Pattern (`db.py`)

```python
# Dependency injected into every route handler
async def get_session() -> AsyncSession
```

Known bug: the `sessionmaker` factory is created on every call (line 29) — it should be a module-level singleton, but has not been fixed yet. All DB operations are async (`await session.execute(...)`, `await session.commit()`).

### LangGraph Agent Structure

Every agent under `ai/agents/{name}/` follows this layout:

```
agent.py      # StateGraph definition — add_sequence([node1, node2, ...])
states.py     # TypedDict or MessagesState subclass
llms.py       # Factory functions: get_chat_model(), get_embedding_model()
nodes/
  {node_name}/
    node.py   # async def {node_name}(state: XState) -> dict
```

Nodes are registered in `langgraph.json`. The conversational assistant is compiled without a checkpointer inside `agent.py`; the checkpointer is injected at invocation time in `app/routers/agent_chat.py`.

### Conversational Assistant (RAG) Flow

`retrieve_node` → `generate_node`, both in `ai/agents/conversational_assistant/nodes/`.

**Retriever:** Queries ChromaDB collection `"kantuta_legal"` using cosine similarity. Accepts optional `document_ids` in state to filter by specific documents, and `k_retrieval` for result count.

**Generator:** Filters retrieved docs by distance score `<= 0.65` (hardcoded in `node.py`). Builds a message list: `[SystemMessage(content_instruction), ...conversation_history, HumanMessage(question + context)]`. LLM parameters (`temperature`, `top_p`, `top_k`) are read from state so they can be overridden per-request from `SystemPrompt` config.

**LLM:** `ChatOllama(model="qwen3:8b", base_url="http://localhost:11435", num_ctx=4096)`. The Google Gemini path is in `llms.py` but currently unused.

### Ingestor Agent Flow

`document_loader_node` → `text_splitter_node` → `vector_store_node`

Legal-aware chunking uses custom separators prioritized for Bolivian statutes: `LIBRO`, `TÍTULO`, `CAPÍTULO`, `ARTÍCULO`. In the ingestor agent: `chunk_size=1200, chunk_overlap=200`. In `app/services/ingestion.py`: `chunk_size=800, chunk_overlap=50` — **these two are inconsistent; the router uses the service, not the agent**.

All blocking I/O (ChromaDB HTTP, file reads) is offloaded with `asyncio.to_thread(sync_fn)` to avoid blocking the event loop.

### Document Ingestion Lifecycle

1. `POST /conocimiento/` saves file to `backend/data/loaded/{timestamp}_{filename}`, creates a `DocumentoConocimiento` row with `estado_indexacion=PROCESANDO`.
2. An `asyncio.create_task()` runs `_run_ingest()` in the background.
3. On completion, status is updated to `COMPLETADO` or `ERROR`.
4. The RAG retriever then finds chunks by `source_filename` metadata in ChromaDB.

### Chat Session ↔ LangGraph Thread Alignment

`ChatSession.id_session` (a `str`) is the LangGraph `thread_id`. When invoking the agent, the router passes `{"configurable": {"thread_id": session_id}}`. This links DB-level session records to the checkpointer's persisted state.

### Authentication

`app/core/deps.py` exports `get_current_user` (OAuth2 + JWT decode). Only these endpoints currently enforce it: `/conocimiento`, `/chat-agent`, `/users/me`, `/users/dashboard`. All other CRUD routers are unprotected.

`app/core/security.py` contains a hardcoded `SECRET_KEY` — the real key must come from `.env`. The file also has a `datetime.utcnow()` deprecation (Python 3.12); prefer `datetime.now(timezone.utc)`.

## Key Conventions

- **All code, comments, variable names, and API responses are in Spanish.**
- Timestamps use `bolivia_now()` — naive datetimes in `America/La_Paz`. This helper is duplicated 9 times across model and router files; when adding new models, copy the pattern but do not rely on any single canonical import.
- Primary key naming is inconsistent across models: `Usuario.id`, `Rol.id_rol`, `Action.id_action`, `Caso.id_caso`, `ChatSession.id_session`, `DocumentoConocimiento.id_documento`, `SystemPrompt.id_prompt`.
- The file `app/routers/documento_comocimiento.py` has a typo (missing 'n'). Do not rename it without updating all imports and `main.py`.
- Enums for `DocumentoConocimiento`: categories are `EnumCategoriaBiblioteca`, icons are `EnumIconoArchivo`, ingestion status is `EnumEstadoIndexacion`.

## Adding New Agents

1. Create `ai/agents/{name}/` with `agent.py`, `states.py`, `llms.py`, `nodes/`.
2. Register in `langgraph.json` under `"graphs"`.
3. All node functions must be `async def node(state: YourState) -> dict`.
4. Use `asyncio.to_thread()` for any synchronous library calls (file I/O, HTTP clients without async support).

## Environment Variables (`.env`)

Required keys (not committed):

```
DATABASE_URL=postgresql+asyncpg://kantuta:...@localhost:5432/kantuta_db
GOOGLE_API_KEY=...
OPENAI_API_KEY=...          # Used only in ai/test/ evaluation notebooks
LANGSMITH_API_KEY=...
LANGSMITH_TRACING=true
LANGSMITH_PROJECT="Kantuta AI"
CHROMA_HOST=localhost
CHROMA_PORT=8000
OLLAMA_BASE_URL=http://localhost:11435
LLM_MODEL_NAME=qwen3:8b
```