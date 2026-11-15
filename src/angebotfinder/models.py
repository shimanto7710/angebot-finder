"""Load the models once before asking questions."""

from pathlib import Path

import torch
from sentence_transformers import SentenceTransformer, CrossEncoder
from transformers import AutoTokenizer, AutoModelForCausalLM

RERANKER_MODEL = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
GENERATION_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"
MODEL_CACHE = Path(__file__).resolve().parents[2] / ".cache" / "huggingface" / "hub"


def load_models(embedding_model_name, reranker_model_name=RERANKER_MODEL,
                generation_model_name=GENERATION_MODEL, local_files_only=False):
    print("Loading embedding model...", flush=True)
    embedding_model = SentenceTransformer(
        embedding_model_name, cache_folder=str(MODEL_CACHE),
        local_files_only=local_files_only,
    )
    print("Loading reranker...", flush=True)
    reranker_model = CrossEncoder(
        reranker_model_name, max_length=512, cache_folder=str(MODEL_CACHE),
        local_files_only=local_files_only,
    )

    if torch.cuda.is_available():
        device = "cuda"
    elif torch.backends.mps.is_available():
        device = "mps"
    else:
        device = "cpu"

    model_dtype = torch.float32 if device == "cpu" else torch.float16
    print(f"Loading generator on {device}...", flush=True)
    generator_tokenizer = AutoTokenizer.from_pretrained(
        generation_model_name, cache_dir=str(MODEL_CACHE),
        local_files_only=local_files_only,
    )
    generator_model = AutoModelForCausalLM.from_pretrained(
        generation_model_name,
        dtype=model_dtype,
        cache_dir=str(MODEL_CACHE),
        local_files_only=local_files_only,
    ).to(device)
    generator_model.eval()
    generator_model.config.use_cache = True
    print("All models ready.", flush=True)

    return embedding_model, reranker_model, generator_model, generator_tokenizer
