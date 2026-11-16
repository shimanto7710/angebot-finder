# AngebotFinder DE

This learning project collects German supermarket offers, stores them in JSON and
PostgreSQL, and uses retrieval and generation to answer offer questions.

```text
scripts/
  fetch_offers.py               Fetch, parse, and save offers
  setup_database.py             Create the initial database tables
  import_offers.py              Import saved JSON into PostgreSQL
  refresh_data.py               Fetch, import, and rebuild embeddings in order
  build_embeddings.py           Build embeddings from PostgreSQL offers
  run_rag.py                    Run the offer assistant
src/angebotfinder/
  database/
    __init__.py
    connection.py               Open PostgreSQL connections
    offers.py                   Fetch and save offers with named queries
  embeddings.py                 Prepare and save embeddings
  retrieval.py                  Load data, hybrid search, and reranking
  generation.py                 Prompts, rewriting, and answer generation
  rag_pipeline.py               Connect the RAG steps
  models.py                     Load models once
notebooks/
  01_extract_offers.ipynb       Run fetching interactively
  02_inspect_offers.ipynb       Explore the saved data
  03_build_embeddings.ipynb     Experiment with offer embeddings
  04_rag_pipeline.ipynb         Experiment with the reusable RAG functions
sql/
  schema.sql                   Initial table definitions
  queries/offers.sql           Named offer queries grouped in one file
data/
  processed/offers_dataset.json Saved offers and source statuses
  samples/                      Example data
tests/                          Offline checks for fetching and export
compose.yaml                    PostgreSQL container and persistent storage
.env                            Local credentials (excluded from Git)
```

`src/` holds reusable Python code. `scripts/` contains commands you run, while
`notebooks/` contains learning experiments. SQL files define the schema and named
queries. The initial schema file is not a migration system; use migrations when
you need to track changes to existing tables.

Use the project's Python environment. For a new environment, install the dependencies with `python -m pip install -r requirements.txt`.

The script defaults to `FETCH_DATA = False`. To refresh the JSON, set it to `True` near the top of the script and run this from the project folder.

```sh
python scripts/fetch_offers.py
```

Set the flag back to `False` after the refresh.

Run the extraction checks offline with `python -m unittest discover -s tests`.

After preparing the offer embeddings, set `QUESTION`, `USE_REWRITING`, and
`MIN_RERANK_SCORE` in `scripts/run_rag.py`, then run the assistant.

```sh
python scripts/run_rag.py
```

The runner loads models once and asks one question. It uses cached files by
default. Set `LOCAL_FILES_ONLY = False` in the runner to download missing models,
then set it back to `True` to avoid network checks during startup.
Importing the modules defines functions without loading models.

Models use the project's ".cache/huggingface/hub/" directory automatically.
The path is defined in `src/angebotfinder/models.py` and works independently of
the terminal's current folder. No `HF_HOME` setting is required.

`RAGPipeline` holds the loaded models, offer data, and shared settings. Create it
once and call `pipeline.ask_question(question, history=history)` for each question.
Keep a separate history list for each conversation. Retrieval and generation
remain small reusable functions. `RAGPipeline.ask_question()` coordinates rewriting,
retrieval, relevance filtering, and answer generation.

The pipeline builds its BM25 index once during initialization and reuses it for
each question. After loading updated offers and embeddings, create a new pipeline
so the index matches the new chunks. When calling `hybrid_search` or `rerank_search`
directly, pass `bm25=pipeline.bm25`, or build an index with `build_bm25(chunks)` once.

## Database queries

`src/angebotfinder/database/connection.py` opens connections using `.env`.
Start PostgreSQL, then run the setup script once to create the initial table:

```sh
docker compose up -d postgres
python scripts/setup_database.py
```

The setup script executes `sql/schema.sql`. It reports an error if the table
already exists; do not rerun setup just to query or import offers.

Keep related offer queries together in `sql/queries/offers.sql`. Each query starts
with an aiosql name, such as `-- name: offers_by_store(store)`. The `:store`
placeholder receives a bound parameter; do not format user input into SQL text.
`src/angebotfinder/database/offers.py` loads the named queries once and exposes
Python functions that execute only the requested query, returning dictionaries.
Calling these functions does not execute the table setup file.

After installing the project with `python -m pip install -e .`, application code
can use:

```python
from angebotfinder.database.offers import fetch_offers_by_store

offers = fetch_offers_by_store("REWE")
for offer in offers:
    print(offer["product_name"], offer["offer_price"], offer["currency"])
```

PostgreSQL must be running and the `offers` table must exist. An empty table or
a store with no matching records returns an empty list. Run from a source checkout
with the `sql/` folder present. Add future offer queries to the same SQL file with
distinct names and corresponding repository functions.

Import the saved JSON after creating the table:

```sh
python scripts/import_offers.py
```

This saves each offer's columns and its complete JSON in `offer_data` together.
The named `save_offer` query updates matching `record_id` values and inserts new
ones. All records are imported in one transaction; an error rolls back the batch.
Reimporting the same records does not create duplicates. Old records absent from
the JSON are retained. Dataset metadata outside the `offers` list is not imported.

Build embeddings from the imported database offers:

```sh
python scripts/build_embeddings.py
```

`fetch_all_offers()` reads each complete `offer_data` JSONB object as a Python
dictionary. Embedding preparation excludes offers explicitly marked
`is_searchable = false`, then creates chunks and vectors as before. The outputs
remain in `data/processed/embeddings/`. The Python embedding and RAG loaders use
PostgreSQL for offer data, so PostgreSQL must be running. RAG still loads saved
chunks and vectors from disk; rebuild them after updating offers. Existing
historical records in the table remain eligible unless marked unsearchable.
The embedding experiment notebook retains its original JSON loading example.

## Refresh pipeline

Start PostgreSQL and create the table once as described above. For the initial
collection and later updates, set `FETCH_DATA = True` in `scripts/refresh_data.py`
and run:

```sh
python scripts/refresh_data.py
```

Set `FETCH_DATA` back to `False` afterward. With the default `False`, the script
does not fetch, connect to PostgreSQL, import, or load models. The pipeline calls
the existing functions directly: web extraction, database import, then embedding
generation. It fetches from the internet first, then writes to PostgreSQL, then
builds embeddings. It stops on a failed step. PostgreSQL must already be running.

`ALLOW_PARTIAL_REFRESH = False` rejects partial shop collections without replacing
the existing JSON or database records. The source statuses are printed for review.
Set it to `True` only when accepting the partial collection: offers missing from
that collection, including offers from failed shops, will become unsearchable.

An accepted refresh imports new records and marks missing old records
`is_searchable = false` in both the database column and stored JSON, in one
transaction. Old rows are retained for inspection. This is collection membership,
not proof that an offer is expired or currently valid. A standalone JSON import
does not deactivate missing records unless explicitly requested in Python.

If embedding generation fails after import, the database already contains the new
collection. Fix the error and run `python scripts/build_embeddings.py` before
starting RAG. The entire refresh is not one database-and-filesystem transaction.
After a successful refresh, start or restart `python scripts/run_rag.py` to load
the updated chunks, vectors, and BM25 index. The refresh script does not ask a
question or start the assistant automatically.
