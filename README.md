# AngebotFinder DE

This learning project collects offer candidates from eight German supermarkets and saves them to JSON.

```text
scripts/
  fetch_offers.py               Fetch, parse, and save offers
  build_embeddings.py           Build chunks and offer embeddings
  run_rag.py                    Run the offer assistant
src/angebotfinder/
  embeddings.py                 Prepare and save embeddings
  retrieval.py                  Load data, hybrid search, and reranking
  generation.py                 Prompts, rewriting, and answer generation
  rag_pipeline.py               Connect the RAG steps
  models.py                     Load models once
notebooks/
  02_shop_extraction.ipynb      Run the same fetching code interactively
  04_rag_pipeline.ipynb         Experiment with the reusable RAG functions
data/
  processed/offers_dataset.json Saved offers and source statuses
  samples/                      Example data
tests/                          Offline checks for fetching and export
```

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
