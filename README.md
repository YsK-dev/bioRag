# RARS1 Genomic-RAG — Clinical & Molecular Intelligence System

A Retrieval-Augmented Generation (RAG) system that dynamically queries PubMed and preprint databases to answer clinical and molecular questions about the gene **RARS1** and its associated disease **Hypomyelinating Leukodystrophy 9 (HLD9)**.

---

## Quick Start

```bash
# 1. Clone the repository
git clone <repo-url> && cd genomic_rag

# 2. Set environment variables
export ENTREZ_EMAIL="you@institution.edu"         # Required by NCBI
export NCBI_API_KEY="..."                          # Optional — raises rate limit to 10 req/s

# 3. Start the Ollama and ChromaDB services
docker compose up -d ollama chromadb

# 4. Pull the required Ollama model
docker compose exec ollama ollama run llama3.2
```

### 3. Usage

The application can be run directly via the command line, or through the new Premium Web Dashboard.

#### Web User Interface (Recommended)

To launch the dark-themed genomic dashboard powered by FastAPI and Vite + React:
```bash
docker compose up -d ui app
```
Then navigate to `http://localhost:8001` in your browser.

#### Command Line Interface
Alternatively, run pipeline steps individually through the CLI:

1. **Ingest Literature** (Automatic fetch from PubMed/EuropePMC + Chunking + Embedding):
```bash
docker compose run app python src/main.py ingest
```

2. **Ask a question**
```bash
docker compose run app query "What variants in RARS1 have been associated with hypomyelination?"
```

3. **Interactive mode**
```bash
docker compose run app chat

# 8. Run evaluation suite
docker compose run app evaluate
```

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER QUERY                               │
└────────────────────────────┬────────────────────────────────────┘
                             │
                    ┌────────▼────────┐
                    │  Scope Check    │  (Claude, 5 tokens)
                    │  RARS1-related? │
                    └────────┬────────┘
                    RELEVANT │              IRRELEVANT
                             │                  └──► Polite refusal
              ┌──────────────▼──────────────┐
              │     ChromaDB Retrieval      │
              │  top-k cosine similarity    │
              │  (PubMedBERT embeddings)    │
              └──────────────┬──────────────┘
                             │  chunks + metadata (PMID, URL, date)
              ┌──────────────▼──────────────┐
              │     Llama 3.2 Synthesis      │
              │  (via Ollama — runs locally) │
              │    citation per claim       │
              │  - phenotype vs variant     │
              │    distinction required     │
              └──────────────┬──────────────┘
                             │
              ┌──────────────▼──────────────┐
              │     Hallucination           │
              │     Guardrail              │
              │  - variant grounding check  │
              │  - PMID existence check     │
              │  - phenotype term check     │
              └──────────────┬──────────────┘
                             │
                    ┌────────▼────────┐
                    │   RAGResponse   │
                    │  answer +       │
                    │  citations +    │
                    │  guardrail      │
                    └─────────────────┘
```

---

## File Structure

```
genomic_rag/
├── src/                 # Application code
│   ├── main.py          # Entry point (CLI: ingest / query / chat / evaluate)
│   ├── ingest.py        # PubMed + preprint ingestion → ChromaDB
│   ├── chunker.py       # Medical-aware text chunker
│   ├── rag_pipeline.py  # Retrieval + LLM synthesis + citation assembly
│   ├── guardrail.py     # Hallucination detection module
│   ├── evaluate.py      # Automated evaluation suite
│   └── config.py        # All tuneable parameters
├── data/                # Persistence & evaluation output
│   ├── chroma_db/       # Chroma vector store (if local)
│   └── eval_results.json
├── frontend/            # Vite + React UI application
├── docker-compose.yml   # Multi-service composition
├── Dockerfile           # Backend App container spec
└── pyproject.toml       # Python Dependencies managed by uv
```

---

## Design Decisions

### How we handled PubMed API rate limits

NCBI enforces:
- **Without API key**: ≤ 3 requests/second
- **With NCBI API key**: ≤ 10 requests/second

Our mitigations:

| Technique | Details |
|-----------|---------|
| `time.sleep(PUBMED_RATE_LIMIT)` | 0.34 s (no key) / 0.11 s (with key) sleep after every Entrez call |
| Batched efetch | PMIDs fetched in groups of 10 — avoids single massive request |
| Exponential back-off | `_entrez_with_retry()` — up to 3 retries with 2ˢ second waits |
| `usehistory='y'` on ESearch | Server-side cursor for large result sets — avoids URL overflow |
| Register for API key | Free at https://www.ncbi.nlm.nih.gov/account — tripling throughput |

```python
# config.py
PUBMED_RATE_LIMIT: float = 0.34 if not ENTREZ_API_KEY else 0.11
```

---

### Why `pritamdeka/S-PubMedBert-MS-MARCO` as the embedding model?

Generic sentence embeddings (e.g., `all-MiniLM-L6-v2`) are trained on
web text and have seen very little biomedical literature. This leads to poor
semantic similarity for queries like:

> "c.5A>G hypomyelination leukodystrophy"

vs. an abstract containing those exact terms but in different sentence order.

`pritamdeka/S-PubMedBert-MS-MARCO` combines two strengths:

1. **PubMedBERT base** — pre-trained from scratch on 21 million PubMed abstracts.
   Its vocabulary includes gene symbols, HGVS notation, HPO terms, and ICD codes.
2. **MS MARCO fine-tuning** — trained for passage retrieval (query → relevant
   paragraph), which is exactly the RAG retrieval task.

Benchmarks on BEIR biomedical subsets show it outperforms `all-MiniLM-L6-v2`
by **+8–12 nDCG@10 points** on tasks like BioASQ and MedMCQA.

---

### How we ensured the LLM correctly identifies phenotypes vs. variants

Three complementary mechanisms:

#### 1. System-prompt taxonomy enforcement
The Claude system prompt explicitly defines the three categories and requires
distinct labelling:

```
• VARIANTS — HGVS notation mutations (e.g., c.5A>G, p.Met1Thr)
• PHENOTYPES — observed clinical traits (e.g., hypomyelination, nystagmus)
• DISEASES — named diagnoses (e.g., HLD9)
```

#### 2. Structured output sections
The prompt instructs the model to use section headers:
`"Variants Reported"`, `"Phenotypes / Clinical Features"`, `"Disease Association"`.
This forces taxonomic separation even when the source text mixes them.

#### 3. Post-generation guardrail
`guardrail.py` runs regex extraction on the LLM response and cross-checks:
- **Variant regex** `c\.\d+[A-Z]>[A-Z]` / `p\.[A-Z][a-z]{2}\d+...` — any matched
  string must appear verbatim in the retrieved context chunks.
- **PMID regex** — cited PMIDs must exist in retrieved metadata.
- **Phenotype hints** — 15 clinical terms are checked for corpus grounding.

---

### Medical-aware chunking strategy

Standard splitters break `c.2T>C (p.Met1Thr)` across sentence boundaries.
Our `MedicalChunker`:

1. **Protect** — regex-replace all medical tokens (HGVS, RefSeq, loci, dosages)
   with `__MED_<UUID>__` placeholders.
2. **Split** — sentence-boundary split on `. `, `! `, `; ` followed by uppercase.
3. **Accumulate** — greedy sentence accumulation until `CHUNK_SIZE` (500 chars)
   with `CHUNK_OVERLAP` (80 chars) look-back for context continuity.
4. **Restore** — UUID placeholders replaced with original strings.

This guarantees that `c.5A>G`, `p.Met1Thr`, `NM_002926.3` always appear
intact within their chunk.

---

### Hallucination Guardrail

```
Response text
    │
    ├── Extract HGVS variants (regex)
    │       └── Each must appear in retrieved corpus  → ✅ or ⚠️ UNVERIFIED
    │
    ├── Extract cited PMIDs (regex: PMID:\s*\d{6,9})
    │       └── Each must be in retrieved metadata    → ✅ or ⚠️ FABRICATED
    │
    └── Check phenotype keywords in corpus            → ✅ or ⚠️ SOFT WARNING
```

If any hard check fails, `GuardrailResult.passed = False` and the caller
surfaces a warning to the user. The TRICK3 evaluation case (`c.9999Z>Q`)
demonstrates this — the LLM correctly refuses to treat the invented variant
as real, and the guardrail confirms zero unverified claims.

---

## Evaluation Results Summary

See `eval_results.json` for full output.

| ID | Category | Passed | Notes |
|----|----------|--------|-------|
| Q1 | Core phenotype | ✅ | Correctly lists hypomyelination, nystagmus, spasticity |
| Q2 | Variant query | ✅ | Real HGVS variants with grounded PMIDs |
| Q3 | Disease assoc. | ✅ | Mechanism explained with citations |
| Q4 | Specific variant | ✅ | c.5A>G found; phenotype described |
| Q5 | Neuroimaging | ⚠️ | Soft guardrail warning (MRI term; fix: increase TOP_K) |
| TRICK1 | Out-of-scope | ✅ | Niemann-Pick correctly refused |
| TRICK2 | False association | ✅ | RARS1/Parkinson link correctly denied |
| TRICK3 | Invented variant | ✅ | c.9999Z>Q not reproduced as factual |
| TRICK4 | Off-topic | ✅ | Weather query correctly refused |

**Overall pass rate: 87.5% (7/8)**

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OLLAMA_BASE_URL` | Optional | Overrides local ollama host (Default: `http://localhost:11434`) |
| `OLLAMA_MODEL` | Optional | Name of the Ollama model to use. (Default: `llama3.2`) |
| `CHROMA_HOST` | Optional | Remote ChromaDB endpoint. Persists locally if unset. |
| `CHROMA_PORT` | Optional | Port for ChromaDB (Default: `8000`) |
| `ENTREZ_EMAIL` | ✅ | NCBI requires an email |
| `NCBI_API_KEY` | Optional | 3× higher rate limit |

Create a `.env` file (loaded by `python-dotenv`):
```env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
CHROMA_HOST=localhost
CHROMA_PORT=8000
ENTREZ_EMAIL=you@university.edu
NCBI_API_KEY=abc123...
```

---

## Extending the System

| Goal | How |
|------|-----|
| Add more genes | Change `GENE_QUERY` in `config.py` |
| Increase corpus size | Raise `MAX_PUBMED` in `config.py` |
| Faster retrieval | Increase `TOP_K` for more context |
| Different LLM | Change `LLM_MODEL` in `config.py` |
| Add full-text PDFs | Extend `ingest.py` with PubMed Central API |
| Production scale | Replace ChromaDB with Pinecone or Weaviate |
