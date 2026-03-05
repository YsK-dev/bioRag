# 🧬 RARS1 Genomic-RAG

> A biomedical Retrieval-Augmented Generation (RAG) system that queries PubMed and preprint databases to answer clinical and molecular questions about the gene **RARS1** and its associated disease **Hypomyelinating Leukodystrophy 9 (HLD9)**.

![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18+-61DAFB?logo=react&logoColor=black)
![ChromaDB](https://img.shields.io/badge/ChromaDB-vector--store-orange)
![Ollama](https://img.shields.io/badge/Ollama-Llama3.2-purple)
![Docker](https://img.shields.io/badge/Docker-compose-2496ED?logo=docker&logoColor=white)

---

## What It Does

- **Ingests** PubMed abstracts and EuropePMC preprints related to RARS1/HLD9 automatically
- **Embeds** them using `pritamdeka/S-PubMedBert-MS-MARCO`, a biomedical sentence transformer
- **Retrieves** the most semantically relevant chunks via ChromaDB (cosine similarity)
- **Synthesises** a cited answer using Llama 3.2 running locally via Ollama
- **Guards** against hallucinations with a three-layer post-generation guardrail
- **Serves** results through a FastAPI backend and a dark-themed React/Vite dashboard

---

## Prerequisites

- [Docker & Docker Compose](https://docs.docker.com/get-docker/)
- [Ollama](https://ollama.com/) (or use the bundled Docker service)
- An NCBI/PubMed account email (free — required by their API)
- Optional: [NCBI API key](https://www.ncbi.nlm.nih.gov/account/) for higher rate limits

---

## Quick Start

```bash
# 1. Clone the repository
git clone <repo-url> && cd bioRag

# 2. Create a .env file with your credentials
cp .env.example .env
# Then edit .env and set ENTREZ_EMAIL (required)

# 3. Start all services (backend, UI, ChromaDB, Ollama)
docker compose up -d

# 4. Pull the LLM model into Ollama
docker compose exec ollama ollama pull llama3.2

# 5. Ingest PubMed literature into the vector store
docker compose run app python src/main.py ingest
```

The **web dashboard** will be available at **http://localhost:8001**.

---

## Usage

### Web Interface (Recommended)

```bash
docker compose up -d ui app
```

Navigate to `http://localhost:8001` and type any RARS1/HLD9 clinical or molecular question.

### Command Line Interface

Run pipeline steps individually from the CLI inside the app container:

```bash
# Ask a single question (plain text output)
docker compose run app python src/main.py query "What variants in RARS1 cause hypomyelination?"

# Ask a single question (JSON output)
docker compose run app python src/main.py query --json "What MRI findings are seen in HLD9?"

# Start an interactive multi-turn chat session
docker compose run app python src/main.py chat

# Re-ingest all data from scratch
docker compose run app python src/main.py ingest --force

# Run the automated evaluation suite
docker compose run app python src/main.py evaluate
```

### Local Development (without Docker)

```bash
# Install Python dependencies
pip install -r requirements.txt

# Set environment variables
export ENTREZ_EMAIL="you@institution.edu"
export OLLAMA_BASE_URL="http://localhost:11434"

# Run backend
uvicorn src.api:app --reload --port 8000

# Run frontend (separate terminal)
cd frontend && npm install && npm run dev
```

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                          USER QUERY                              │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                      ┌────────▼────────┐
                      │   Scope Check   │  Is this RARS1-related?
                      └────────┬────────┘
               RELEVANT        │                 IRRELEVANT
                               │                     └──► Polite refusal
            ┌──────────────────▼──────────────────┐
            │        ChromaDB Retrieval            │
            │   top-k cosine similarity (k=6)      │
            │   PubMedBERT embeddings              │
            └──────────────────┬──────────────────┘
                               │  chunks + metadata (PMID, URL, date)
            ┌──────────────────▼──────────────────┐
            │          Llama 3.2 via Ollama        │
            │  · Citation per claim required       │
            │  · Phenotype vs variant distinction  │
            │  · Structured section headers        │
            └──────────────────┬──────────────────┘
                               │
            ┌──────────────────▼──────────────────┐
            │         Hallucination Guardrail      │
            │  ✔ HGVS variants grounded in corpus  │
            │  ✔ PMIDs exist in retrieved metadata │
            │  ✔ Phenotype terms corpus-checked    │
            └──────────────────┬──────────────────┘
                               │
                      ┌────────▼────────┐
                      │   RAGResponse   │
                      │  answer         │
                      │  citations      │
                      │  guardrail info │
                      └─────────────────┘
```

---

## Project Structure

```
bioRag/
├── src/
│   ├── main.py          # CLI entry point (ingest / query / chat / evaluate)
│   ├── api.py           # FastAPI backend — serves the web dashboard
│   ├── ingest.py        # PubMed + EuropePMC ingestion → ChromaDB
│   ├── chunker.py       # Medical-aware text chunker (protects HGVS notation)
│   ├── rag_pipeline.py  # Retrieval + Llama synthesis + citation assembly
│   ├── guardrail.py     # Post-generation hallucination detection
│   ├── evaluate.py      # Automated evaluation suite (8 test cases)
│   └── config.py        # All tuneable parameters (one place to change)
├── frontend/            # Vite + React dark-themed dashboard
│   ├── src/
│   │   ├── App.jsx
│   │   └── main.jsx
│   └── package.json
├── data/
│   ├── chroma_db/       # Local ChromaDB vector store
│   └── eval_results.json
├── docker-compose.yml   # Multi-service composition
├── Dockerfile           # Backend container spec
├── pyproject.toml       # Python project metadata (managed by uv)
└── requirements.txt
```

---

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `ENTREZ_EMAIL` | ✅ | — | NCBI requires an email for API access |
| `NCBI_API_KEY` | No | — | Raises rate limit from 3 → 10 req/s |
| `OLLAMA_BASE_URL` | No | `http://localhost:11434` | Ollama endpoint |
| `OLLAMA_MODEL` | No | `llama3.2` | Any Ollama-compatible model name |
| `CHROMA_HOST` | No | _(local)_ | Remote ChromaDB host; local persistence if unset |
| `CHROMA_PORT` | No | `8000` | ChromaDB port |

Create a `.env` file in the project root:

```env
ENTREZ_EMAIL=you@university.edu
NCBI_API_KEY=abc123...        # optional
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
CHROMA_HOST=chromadb          # use 'localhost' for local dev
CHROMA_PORT=8000
```

### Key Tuneable Parameters (`src/config.py`)

| Parameter | Default | Description |
|---|---|---|
| `MAX_PUBMED` | `50` | Max PubMed abstracts to ingest |
| `MAX_PREPRINT` | `20` | Max EuropePMC preprints to ingest |
| `TOP_K` | `6` | Chunks retrieved per query |
| `CHUNK_SIZE` | `500` | Target characters per chunk |
| `CHUNK_OVERLAP` | `80` | Character overlap between chunks |
| `GENE_QUERY` | RARS1/HLD9 search | PubMed search string |

---

## Design Notes

### Embedding model — `pritamdeka/S-PubMedBert-MS-MARCO`

Generic models (e.g., `all-MiniLM-L6-v2`) perform poorly on biomedical text because they rarely encounter HGVS notation, HPO terms, or gene symbols during pre-training. This model combines:

- **PubMedBERT base** — trained from scratch on 21 million PubMed abstracts
- **MS MARCO fine-tuning** — optimised for passage retrieval (query → relevant paragraph)

Result: **+8–12 nDCG@10** over generic models on BioASQ and MedMCQA benchmarks.

### Medical-aware chunking

Standard splitters break `c.2T>C (p.Met1Thr)` across sentence boundaries. `MedicalChunker` avoids this by:

1. **Protect** — replace HGVS, RefSeq IDs, dosages with `__MED_<UUID>__` placeholders
2. **Split** — sentence-boundary split on `. ` / `; ` before uppercase letters
3. **Accumulate** — greedy fill up to `CHUNK_SIZE` with `CHUNK_OVERLAP` look-back
4. **Restore** — swap UUIDs back with original strings

### Hallucination guardrail (3 layers)

| Check | Method | Failure label |
|---|---|---|
| HGVS variant grounding | Regex extraction → corpus substring search | ⚠️ `UNVERIFIED_VARIANT` |
| PMID validity | Regex extraction → retrieved metadata lookup | ⚠️ `FABRICATED_PMID` |
| Phenotype grounding | 15-term keyword list → corpus search | ⚠️ `SOFT_WARNING` |

If any hard check fails, `GuardrailResult.passed = False` and a warning is surfaced to the user.

### PubMed rate-limit mitigations

| Technique | Detail |
|---|---|
| Adaptive sleep | 0.34 s (no key) / 0.11 s (with key) after every Entrez call |
| Batched `efetch` | PMIDs fetched in groups of 10 |
| Exponential back-off | Up to 3 retries with $2^n$ second delays |
| `usehistory='y'` | Server-side cursor avoids URL overflow on large result sets |

---

## Evaluation Results

Run `python src/main.py evaluate` to reproduce. Full output in [`data/eval_results.json`](data/eval_results.json).

| ID | Category | Result | Notes |
|---|---|---|---|
| Q1 | Core phenotype | ✅ Pass | Correctly identifies hypomyelination, nystagmus, spasticity |
| Q2 | Variant query | ✅ Pass | Real HGVS variants with grounded PMIDs |
| Q3 | Disease association | ✅ Pass | Mechanism explained with citations |
| Q4 | Specific variant | ✅ Pass | `c.5A>G` found with phenotype description |
| Q5 | Neuroimaging | ⚠️ Soft warn | MRI term warning — increase `TOP_K` to fix |
| TRICK1 | Out-of-scope gene | ✅ Pass | Niemann-Pick query correctly refused |
| TRICK2 | False association | ✅ Pass | RARS1/Parkinson link correctly denied |
| TRICK3 | Invented variant | ✅ Pass | `c.9999Z>Q` not reproduced as factual |
| TRICK4 | Off-topic | ✅ Pass | Weather query correctly refused |

**Overall: 87.5% pass rate (7/8 hard pass, 1 soft warning)**

---

## Extending the System

| Goal | Change |
|---|---|
| Support additional genes | Update `GENE_QUERY` in `src/config.py` |
| Larger corpus | Increase `MAX_PUBMED` / `MAX_PREPRINT` in `src/config.py` |
| Better recall | Increase `TOP_K` in `src/config.py` |
| Swap the LLM | Set `OLLAMA_MODEL` env var or change `LLM_MODEL` in `src/config.py` |
| Add full-text PDFs | Extend `src/ingest.py` with PubMed Central Open Access API |
| Production vector store | Replace local ChromaDB with Pinecone, Weaviate, or Qdrant |
| Add authentication | Add OAuth2 middleware to `src/api.py` |
