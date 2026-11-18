# AngebotFinder DE

A German supermarket offer assistant with product filtering and conversational
search. Offers, chat history, chunks, and embeddings are stored in PostgreSQL.

## How it works

```text
Shop pages → extraction → JSON → PostgreSQL offers
                                    ↓
                           chunks → E5 embeddings
                                    ↓
                           PostgreSQL + pgvector
                                    ↓
Question → rewriting → vector search + BM25 → RRF → reranking → answer
```

The extractor covers configured pages for REWE, EDEKA, ALDI Nord, ALDI Süd,
PENNY, Lidl, Kaufland, and Netto Marken-Discount. It uses retailer pages and
third-party listings through HTTP requests.

- Embeddings: `intfloat/multilingual-e5-base` (768 dimensions)
- Reranker: `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`
- Generator: `Qwen/Qwen2.5-1.5B-Instruct`
- API: FastAPI, with Argon2 password hashing and JWT authentication
- Storage: PostgreSQL 17, JSONB, and pgvector cosine search with an HNSW index

BM25 is built once per pipeline instance. Models load on the first chat request
and are reused. Follow-up questions use the user's last three completed turns.

## Local setup

Requires Python 3.11+ and Docker with Compose. Run commands from the project root.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Create an untracked `.env`:

```ini
POSTGRES_HOST=localhost
POSTGRES_PORT=5433
POSTGRES_DB=angebotfinder
POSTGRES_USER=angebotfinder
POSTGRES_PASSWORD=your_database_password
JWT_SECRET_KEY=your_random_signing_secret
```

Generate a signing secret with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
Keep the same secret across restarts to preserve token validity.

Start PostgreSQL and prepare tables, offers, and embeddings:

```bash
docker compose up -d postgres
python -c "from scripts.setup_data import setup_data; setup_data(enabled=True)"
```

Setup creates missing tables without replacing existing ones. It then fetches
offers, imports them, and generates embeddings. It does not start PostgreSQL or
the API. Existing table definitions require migrations when changed.

Download the remaining RAG models before the first chat request:

```bash
python -c "from angebotfinder.models import load_models; load_models('intfloat/multilingual-e5-base')"
```

Models are cached in `.cache/huggingface/hub/`. The API uses local model files.
Start the API:

```bash
python -m uvicorn angebotfinder.api.app:app --app-dir src --reload
```

Open [API docs](http://127.0.0.1:8000/docs). Run one API worker: model inference and
chat writes use a process-local lock. Remove `--reload` outside development.

## Updating offers

```bash
python -c "from scripts.refresh_data import refresh_data; refresh_data(enabled=True)"
```

The refresh fetches offers, updates PostgreSQL, and replaces the chunk/vector
collection. Restart the API afterward to reload its cached retrieval data.
Standalone setup and refresh scripts are disabled by default; the explicit
function calls above enable them.

Partial shop collections stop the refresh before import. Set `allow_partial=True`
only to accept that result. Missing old offers are retained but marked
unsearchable, including offers from failed shops in an accepted partial refresh.
Offer import and embedding replacement are separate transactions. If embedding
generation fails, rebuild it with `python scripts/build_embeddings.py` before
restarting the API.

Other commands:

| Command | Purpose |
|---|---|
| `python scripts/setup_database.py` | Create missing tables and indexes |
| `python scripts/import_offers.py` | Import existing `data/processed/offers_dataset.json` |
| `python scripts/build_embeddings.py` | Build and store database chunks and vectors |
| `python scripts/run_rag.py` | Ask the question configured in the script |

A standalone JSON import updates matching record IDs but does not deactivate
missing offers. Full refresh does. No chunk JSON or NumPy files are needed at runtime.

## API

| Method | Endpoint | Authentication | Purpose |
|---|---|---|---|
| POST | `/auth/register` | Public | Register with name, email, and password |
| POST | `/auth/login` | Public | Get a 30-minute bearer token |
| GET | `/auth/me` | Bearer token | Get the current user's profile |
| POST | `/chat` | Bearer token | Ask a question and save the turn |
| GET | `/chat/history` | Bearer token | Read the user's recent turns |
| GET | `/offers` | Public | List and filter saved offers |
| GET | `/rag/data` | Public | Download chunks, vectors, and model settings |

Registration requires a name of 1–100 characters and a password of 12–128
characters. Emails are normalized to lowercase; duplicate registration returns
409. Passwords are stored as Argon2 hashes. Login returns `access_token`,
`token_type`, and `expires_in`. Send `Authorization: Bearer <token>` on protected requests.

Chat request:

```json
{
  "user_id": "your-user-uuid",
  "question": "Which stores have Haribo offers?"
}
```

The user ID must match the token. Each user currently has one conversation.
`GET /chat/history?user_id=<uuid>` returns the latest three turns in chronological
order; `limit` accepts 1–100. Older turns remain stored.

Offer filters: `search`, `store`, `brand`, `category`, `min_price`, `max_price`,
`requires_loyalty`, and `include_unsearchable`. Filters combine with AND. Search
is a case-insensitive substring; store, brand, and category use exact
case-insensitive matches. Loyalty filters exclude unknown eligibility. Pagination
uses `limit` (default 20, maximum 100) and `offset`. Results include the total
match count and complete `offer_data`. Decimal prices are returned as strings.

The Android bundle contains `dataset_version`, `config`, `chunks`, and
`embeddings`. Vector `i` belongs to chunk `i`; replace the bundle together.
Android needs the same E5 model, tokenizer, prefixes, pooling, and normalization
for query embeddings. Model weights and an Android inference implementation are
not included. [E5 model documentation](https://huggingface.co/intfloat/multilingual-e5-base)

Import the files in `postman/` for prepared API requests. See
[Postman setup](postman/README.md).

## Project layout

```text
src/angebotfinder/
    api/                 Routes, request/response models, and authentication dependencies
    database/            Connections and database operations
    embeddings.py        Document preparation, chunking, and embedding generation
    retrieval.py         Hybrid ranking and Android data export
    generation.py        Prompts, rewriting, and generation
    rag_pipeline.py      Question-to-answer orchestration
    models.py            Model loading
    security.py          Password hashing and access tokens
scripts/                 Setup, refresh, import, and CLI entry points
sql/                     Schema, named queries, and schema changes
notebooks/               Extraction, inspection, embedding, and RAG experiments
tests/                   Unit and API tests
postman/                 API collection and local environment template
compose.yaml             PostgreSQL service and persistent volume
```

Named queries are grouped by purpose in `sql/queries/` and loaded with aiosql.
Run from the source checkout so the SQL directory is available.

## Tests and limitations

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests
```

Tests cover extraction, refresh failures, vector validation, authentication,
user-history isolation, filters, and Android exports. Chat API tests use simulated
RAG output; model answer quality needs separate evaluation.

Listings are candidates from configured pages, not complete nationwide coverage.
Stock, branch participation, loyalty eligibility, and yearless validity dates may
be unknown. The prompt requires source citations, but the generator can still
omit offers or produce unsupported details. Published prices need compatible pack
sizes and currency for comparison.

Deployment is not configured yet. Before public use, add HTTPS, login rate limits,
backups, and secret management. Email ownership verification, token revocation,
and multiple conversations per user are not implemented. The current vector
schema supports one active 768-dimensional embedding model.
