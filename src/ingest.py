"""
ingest.py — Data ingestion pipeline for the RARS1 Genomic-RAG system.

Responsibilities
----------------
1. Query PubMed literature via Europe PMC REST API (mirrors MEDLINE/PubMed).
2. Query Europe PMC for preprint (bioRxiv / medRxiv) records.
3. Chunk all abstracts with MedicalChunker.
4. Embed chunks with a PubMed-fine-tuned Sentence Transformer.
5. Persist everything to ChromaDB for retrieval.

Note: Europe PMC (www.ebi.ac.uk/europepmc) is used as the primary data source
because it mirrors the full PubMed/MEDLINE catalogue and is accessible without
TLS restrictions that affect direct NCBI e-utilities access in some environments.

Rate-limit handling
-------------------
* Europe PMC allows generous public API access (no API key required).
* A 0.25 s sleep between paginated requests keeps well under rate limits.
* HTTP errors trigger exponential back-off (max 3 retries).
* All API errors are caught; failed records are logged and skipped gracefully.
"""

import logging
import time
from typing import List, Dict

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import chromadb
from chromadb.utils import embedding_functions

from chunker import MedicalChunker, Chunk
from config import (
    ENTREZ_EMAIL,
    GENE_QUERY, MAX_PUBMED, MAX_PREPRINT,
    CHROMA_DIR, COLLECTION_NAME,
    CHROMA_HOST, CHROMA_PORT,
    EMBEDDING_MODEL, FALLBACK_EMBEDDING_MODEL,
)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
log = logging.getLogger("ingest")

# ── Shared requests session with retry policy ─────────────────────────────────
_retry_policy = Retry(total=3, backoff_factor=1,
                      status_forcelist=[429, 500, 502, 503, 504])
_session = requests.Session()
_session.mount("https://", HTTPAdapter(max_retries=_retry_policy))
_session.headers.update({"User-Agent": f"bioRag/1.0 ({ENTREZ_EMAIL})"})

# ── Europe PMC REST endpoint ──────────────────────────────────────────────────
_EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


# ─────────────────────────────────────────────────────────────────────────────
#  PubMed literature via Europe PMC
# ─────────────────────────────────────────────────────────────────────────────

def fetch_pubmed_articles(
    query: str = GENE_QUERY,
    max_results: int = MAX_PUBMED,
) -> List[Dict[str, str]]:
    """
    Fetch peer-reviewed PubMed articles from Europe PMC (SRC:MED).

    Europe PMC mirrors the full MEDLINE/PubMed catalogue and is reachable
    even when direct NCBI e-utilities access is blocked by network policy.

    Returns a list of dicts with keys:
        pmid, title, abstract, authors, date, journal, url
    """
    # Europe PMC uses different field syntax from NCBI.
    # Strip NCBI-style field qualifiers like [Title/Abstract] so the terms
    # work natively as full-text search in Europe PMC.
    import re as _re
    clean_query = _re.sub(r'\[.*?\]', '', query).strip()
    # Scope to MEDLINE/PubMed source only
    epmc_query = f"({clean_query}) AND SRC:MED"
    log.info(f"Querying Europe PMC for PubMed articles: {epmc_query!r} (max {max_results})")

    articles: List[Dict[str, str]] = []
    page_size = min(max_results, 100)       # Europe PMC max per page is 1000
    cursor_mark = "*"                       # cursor-based pagination

    while len(articles) < max_results:
        try:
            params: Dict = {
                "query":      epmc_query,
                "resultType": "core",
                "format":     "json",
                "pageSize":   page_size,
                "sort":       "CITED desc",
                "synonym":    "TRUE",
                "cursorMark": cursor_mark,
            }
            resp = _session.get(_EPMC, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            log.error(f"Europe PMC request failed: {exc}")
            break

        results = data.get("resultList", {}).get("result", [])
        if not results:
            break

        for r in results:
            abstract = r.get("abstractText", "").strip()
            if not abstract:
                continue
            pmid = r.get("pmid", r.get("doi", ""))
            articles.append({
                "pmid":    pmid,
                "title":   r.get("title", ""),
                "abstract": abstract,
                "authors": r.get("authorString", ""),
                "date":    str(r.get("pubYear", "")),
                "journal": r.get("journalTitle", r.get("bookTitle", "")),
                "url":     (f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
                            if r.get("pmid") else
                            f"https://doi.org/{r.get('doi','')}" if r.get('doi') else ""),
            })
            if len(articles) >= max_results:
                break

        # Advance cursor; stop if no next page
        next_cursor = data.get("nextCursorMark", "")
        if not next_cursor or next_cursor == cursor_mark:
            break
        cursor_mark = next_cursor
        time.sleep(0.25)   # polite rate-limiting

    log.info(f"Fetched {len(articles)} PubMed articles with abstracts via Europe PMC")
    return articles


# ─────────────────────────────────────────────────────────────────────────────
#  Europe PMC — preprint ingestion (Bonus)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_preprints(query: str = "RARS1", max_results: int = MAX_PREPRINT) -> List[Dict[str, str]]:
    """
    Query Europe PMC REST API for preprints (source=PPR covers bioRxiv,
    medRxiv, Research Square, etc.).
    Returns the same dict schema as fetch_pubmed_abstracts for seamless merging.
    """
    log.info(f"Querying Europe PMC preprints for: {query!r} (max {max_results})")
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {
        "query":      f"{query} AND SRC:PPR",
        "resultType": "core",
        "format":     "json",
        "pageSize":   max_results,
        "sort":       "CITED desc",
    }

    preprints: List[Dict[str, str]] = []
    try:
        resp = _session.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("resultList", {}).get("result", [])

        for r in results:
            abstract = r.get("abstractText", "").strip()
            if not abstract:
                continue

            doi = r.get("doi", "")
            preprints.append({
                "pmid":     r.get("pmcid", doi),   # use DOI as fallback ID
                "title":    r.get("title", ""),
                "abstract": abstract,
                "authors":  r.get("authorString", ""),
                "date":     r.get("pubYear", ""),
                "journal":  r.get("source", "Preprint"),
                "url":      f"https://doi.org/{doi}" if doi else "",
                "is_preprint": True,
            })

        log.info(f"Found {len(preprints)} preprints with abstracts")
    except Exception as exc:
        log.warning(f"Europe PMC query failed: {exc} — continuing without preprints")

    return preprints


# ─────────────────────────────────────────────────────────────────────────────
#  Embedding + ChromaDB
# ─────────────────────────────────────────────────────────────────────────────

def _build_embedding_fn():
    """
    Build a SentenceTransformer embedding function.
    Falls back to a generic model if the biomedical one is unavailable.
    """
    try:
        ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=EMBEDDING_MODEL,
        )
        log.info(f"Loaded embedding model: {EMBEDDING_MODEL}")
        return ef
    except Exception as exc:
        log.warning(f"Could not load {EMBEDDING_MODEL}: {exc}. Using fallback.")
        return embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=FALLBACK_EMBEDDING_MODEL,
        )


def build_vector_store(articles: List[Dict[str, str]]) -> chromadb.Collection:
    """
    Chunk all article abstracts and upsert into ChromaDB.

    Document IDs are  <pmid>_<chunk_index>  so re-running ingest is
    idempotent — existing chunks are overwritten rather than duplicated.
    """
    chunker = MedicalChunker()
    if CHROMA_HOST:
        client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    else:
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    ef      = _build_embedding_fn()

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )

    ids, documents, metadatas = [], [], []

    for art in articles:
        chunks: List[Chunk] = chunker.chunk_abstract(
            text=art["abstract"],
            source_id=art["pmid"],
            source_title=art["title"],
            source_date=art["date"],
            source_url=art.get("url", ""),
        )

        for chunk in chunks:
            doc_id = f"{chunk.source_id}_{chunk.chunk_index}"
            ids.append(doc_id)
            documents.append(chunk.text)
            metadatas.append({
                "pmid":        chunk.source_id,
                "title":       chunk.source_title,
                "date":        chunk.source_date,
                "url":         chunk.source_url,
                "journal":     art.get("journal", ""),
                "authors":     art.get("authors", ""),
                "chunk_index": chunk.chunk_index,
                "is_preprint": str(art.get("is_preprint", False)),
            })

    if not ids:
        log.warning("No chunks generated — check abstracts.")
        return collection

    # Upsert in batches of 100 (ChromaDB recommendation)
    batch = 100
    for i in range(0, len(ids), batch):
        collection.upsert(
            ids=ids[i : i + batch],
            documents=documents[i : i + batch],
            metadatas=metadatas[i : i + batch],
        )
        log.info(f"Upserted chunks {i+1}–{min(i+batch, len(ids))} / {len(ids)}")

    log.info(
        f"Vector store ready — {collection.count()} total chunks in '{COLLECTION_NAME}'"
    )
    return collection


# ─────────────────────────────────────────────────────────────────────────────
#  Public entrypoint
# ─────────────────────────────────────────────────────────────────────────────

def load_or_ingest(force: bool = False) -> chromadb.Collection:
    """
    If the ChromaDB collection already exists and *force* is False, just
    return it.  Otherwise, run the full ingestion pipeline.
    """
    if CHROMA_HOST:
        client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    else:
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    ef     = _build_embedding_fn()

    existing_names = [c.name for c in client.list_collections()]

    if COLLECTION_NAME in existing_names and not force:
        col = client.get_collection(COLLECTION_NAME, embedding_function=ef)
        count = col.count()
        if count > 0:
            log.info(f"Loaded existing collection '{COLLECTION_NAME}' ({count} chunks)")
            return col
        log.info("Existing collection is empty — re-ingesting.")

    # ── Fetch data ────────────────────────────────────────────────────────────
    try:
        articles = fetch_pubmed_articles()
    except Exception as e:
        log.error(f"PubMed fetch failed entirely: {e}. Attempting to proceed with preprints only.")
        articles = []

    preprints = fetch_preprints()
    all_articles = articles + preprints

    if not all_articles:
        raise RuntimeError("No articles fetched — check your network / NCBI credentials.")

    log.info(f"Total articles for indexing: {len(all_articles)} "
             f"({len(articles)} PubMed + {len(preprints)} preprints)")

    return build_vector_store(all_articles)


# ─────────────────────────────────────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="RARS1 Genomic-RAG — ingestion")
    parser.add_argument("--force", action="store_true",
                        help="Force re-ingestion even if collection exists")
    args = parser.parse_args()

    collection = load_or_ingest(force=args.force)
    print(f"\nIngestion complete -- {collection.count()} chunks indexed.")
