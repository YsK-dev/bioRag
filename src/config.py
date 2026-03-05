"""
config.py — Central configuration for the RARS1 Genomic-RAG system.
All tuneable parameters live here so the rest of the codebase stays
free of magic strings / numbers.
"""

import os
from pathlib import Path

# ── NCBI / PubMed ─────────────────────────────────────────────────────────────
# Provide your email so NCBI can contact you if you abuse their API.
ENTREZ_EMAIL = os.getenv("ENTREZ_EMAIL", "researcher@example.com")

# Optional NCBI API key – raises rate limit from 3 req/s → 10 req/s.
# Register free at https://www.ncbi.nlm.nih.gov/account/
ENTREZ_API_KEY: str = os.getenv("NCBI_API_KEY", "")

# Inter-request sleep in seconds (conservative defaults).
PUBMED_RATE_LIMIT: float = 0.34 if not ENTREZ_API_KEY else 0.11

# PubMed search query – covers gene symbol, full name, and disease alias.
GENE_QUERY: str = (
    '(RARS1[Title/Abstract] OR '
    '"arginyl-tRNA synthetase 1"[Title/Abstract] OR '
    '"hypomyelinating leukodystrophy 9"[Title/Abstract] OR '
    '"HLD9"[Title/Abstract])'
)

MAX_PUBMED: int   = 50   # max PubMed abstracts to ingest
MAX_PREPRINT: int = 20   # max Europe-PMC preprints to ingest

# ── Vector Store ──────────────────────────────────────────────────────────────
CHROMA_DIR: Path    = Path("./data/chroma_db")
COLLECTION_NAME: str = "rars1_genomics"
CHROMA_HOST: str    = os.getenv("CHROMA_HOST", "")
CHROMA_PORT: int    = int(os.getenv("CHROMA_PORT", "8000"))

# ── Embeddings ────────────────────────────────────────────────────────────────
# Why this model?
# pritamdeka/S-PubMedBert-MS-MARCO is a Sentence-Transformer fine-tuned on
# PubMed abstracts using the MS MARCO retrieval framework.  It consistently
# outperforms generic models (e.g., all-MiniLM-L6-v2) on biomedical IR
# benchmarks because its vocabulary includes domain-specific tokens like
# gene symbols, HGVS notation, and ICD terms.
EMBEDDING_MODEL: str = "pritamdeka/S-PubMedBert-MS-MARCO"

# Fallback if the PubMedBERT model cannot be downloaded (offline environments).
FALLBACK_EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"

# ── LLM ───────────────────────────────────────────────────────────────────────
OLLAMA_BASE_URL: str   = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LLM_MODEL: str         = os.getenv("OLLAMA_MODEL", "llama3.2")
MAX_TOKENS: int        = 2048

# ── Chunking ──────────────────────────────────────────────────────────────────
CHUNK_SIZE: int    = 500   # target characters per chunk
CHUNK_OVERLAP: int = 80    # overlap to preserve context across chunk boundaries

# ── Retrieval ─────────────────────────────────────────────────────────────────
TOP_K: int = 6   # number of chunks returned per query

# ── Evaluation ────────────────────────────────────────────────────────────────
EVAL_OUTPUT_PATH: Path = Path("./data/eval_results.json")
