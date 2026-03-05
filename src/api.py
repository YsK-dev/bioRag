"""
api.py -- FastAPI application exposing the RARS1 Genomic-RAG system over HTTP.

Endpoints
---------
GET  /api/status          Health-check; reports whether the RAG pipeline is ready.
POST /api/query           Non-streaming query; returns the full answer + citations.
POST /api/query/stream    SSE streaming query; emits scope / citation / token events.
GET  /api/variants        Extract genomic entities found in the indexed literature.
GET  /api/gene-info       Return curated RARS1 / HLD9 reference data.
"""
import json
import re
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional

from src.rag_pipeline import RAGPipeline, RAGResponse

log = logging.getLogger("api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

app = FastAPI(
    title="RARS1 Genomic Intelligence API",
    description="Backend API for querying the RARS1 RAG system.",
    version="1.0.0"
)

# Enable CORS for the Vite frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

pipeline = None

@app.on_event("startup")
async def startup_event():
    global pipeline
    try:
        log.info("Initializing RAGPipeline...")
        pipeline = RAGPipeline()
        log.info("RAGPipeline initialized successfully.")
    except Exception as e:
        log.error(f"Failed to initialize RAGPipeline: {e}")
        raise e

# --- Models ---
class QueryRequest(BaseModel):
    """Request body for /api/query and /api/query/stream."""

    query: str

class CitationModel(BaseModel):
    """A single bibliographic citation returned alongside a RAG answer."""

    pmid: str
    title: str
    url: str

class GuardrailModel(BaseModel):
    """Hallucination-detection result attached to every query response."""

    passed: bool
    warnings: List[str] = []
    unverified_variants: List[str] = []
    fabricated_pmids: List[str] = []
    summary: str = ""

class QueryResponse(BaseModel):
    """Full non-streaming response returned by /api/query."""
    answer: str
    citations: List[CitationModel]
    guardrail: Optional[GuardrailModel]

# --- Endpoints ---
@app.get("/api/status")
async def status():
    """Health check endpoint."""
    return {"status": "ok", "pipeline_loaded": pipeline is not None}

@app.post("/api/query", response_model=QueryResponse)
async def query_endpoint(req: QueryRequest):
    """Process a user query through the RAG pipeline (non-streaming)."""
    if not pipeline:
        raise HTTPException(status_code=503, detail="Pipeline is still initializing or failed to load.")
    
    try:
        rag_resp: RAGResponse = pipeline.query(req.query)
        
        citations = []
        for c in rag_resp.citations:
            citations.append(CitationModel(
                pmid=c.get("pmid", ""),
                title=c.get("title", ""),
                url=c.get("url", ""),
            ))
        
        guardrail = None
        if rag_resp.guardrail:
            guardrail = GuardrailModel(
                passed=rag_resp.guardrail.passed,
                warnings=rag_resp.guardrail.warnings,
                unverified_variants=rag_resp.guardrail.unverified_variants,
                fabricated_pmids=rag_resp.guardrail.fabricated_pmids,
                summary=rag_resp.guardrail.summary,
            )
        
        return QueryResponse(
            in_scope=rag_resp.in_scope,
            answer=rag_resp.answer,
            citations=citations,
            guardrail=guardrail
        )
    except Exception as e:
        log.error(f"Error processing query: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/query/stream")
async def query_stream_endpoint(req: QueryRequest):
    """
    SSE streaming endpoint. Sends events as they happen:
      event: scope     → {"in_scope": true/false}
      event: citations → [{pmid, title, url}, ...]
      event: token     → "chunk of text"
      event: guardrail → {passed, warnings, ...}
      event: done      → {}
    """
    if not pipeline:
        raise HTTPException(status_code=503, detail="Pipeline is still initializing or failed to load.")

    def event_generator():
        try:
            for evt in pipeline.query_stream(req.query):
                event_name = evt["event"]
                data = json.dumps(evt["data"], ensure_ascii=False)
                yield f"event: {event_name}\ndata: {data}\n\n"
        except Exception as e:
            log.error(f"Streaming error: {e}")
            error_data = json.dumps({"error": str(e)})
            yield f"event: error\ndata: {error_data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


# ── Variant regex (same as guardrail.py) ──────────────────────────────────────
_VARIANT_RE = re.compile(
    r'(?:'
    r'c\.\d+[-+]?\d*[A-Za-z]>[A-Za-z]'
    r'|p\.[A-Z][a-z]{2}\d+[A-Z*][a-z]*'
    r'|p\.\([A-Z][a-z]{2}\d+[A-Z*][a-z]*\)'
    r')',
    re.IGNORECASE,
)


@app.get("/api/variants")
async def variants_endpoint():
    """Extract all known RARS1 variants and key genomic entities from the indexed literature."""
    if not pipeline:
        raise HTTPException(status_code=503, detail="Pipeline not ready.")

    col = pipeline._col
    all_data = col.get(include=["documents", "metadatas"])

    # Broader patterns to catch different variant/gene mention styles
    patterns = {
        "hgvs": re.compile(
            r'(?:c\.\d+[-+]?\d*[A-Za-z]>[A-Za-z]'
            r'|p\.[A-Z][a-z]{2}\d+[A-Z*][a-z]*'
            r'|p\.\([A-Z][a-z]{2}\d+[A-Z*][a-z]*\))',
            re.IGNORECASE
        ),
        "gene": re.compile(
            r'\b(RARS1|RARS|DARS|KARS|AARS|MARS|IARS|LARS|EPRS|CHD1|MAP3K7|TP53|BRCA[12]|EGFR)\b'
        ),
        "mutation_term": re.compile(
            r'\b(missense|nonsense|frameshift|splice.site|truncat\w+|loss.of.function|gain.of.function'
            r'|knock.?out|homozygous|heterozygous|compound.heterozygous|biallelic|monoallelic'
            r'|pathogenic|likely.pathogenic|variant.of.uncertain|benign'
            r'|deletion|duplication|insertion|substitution)\b',
            re.IGNORECASE
        ),
    }

    phenotype_terms = [
        "hypomyelination", "leukodystrophy", "nystagmus", "spasticity",
        "ataxia", "developmental delay", "microcephaly", "hypotonia",
        "seizure", "intellectual disability", "white matter",
        "peripheral neuropathy", "cerebellar", "myelination",
        "neurodegeneration", "motor", "cognitive",
    ]

    entities = {}  # entity_str -> {type, sources, phenotypes}

    for doc, meta in zip(all_data["documents"], all_data["metadatas"]):
        doc_lower = doc.lower()
        pmid = meta.get("pmid", "")
        title = meta.get("title", "")

        # Find co-occurring phenotypes in this chunk
        chunk_phenotypes = set()
        for term in phenotype_terms:
            if term in doc_lower:
                chunk_phenotypes.add(term)

        for ptype, regex in patterns.items():
            for match in regex.findall(doc):
                key = match.strip()
                if key not in entities:
                    entities[key] = {"type": ptype, "sources": set(), "phenotypes": set(), "titles": set()}
                if pmid:
                    entities[key]["sources"].add(pmid)
                if title:
                    entities[key]["titles"].add(title[:100])
                entities[key]["phenotypes"].update(chunk_phenotypes)

    result = []
    for ent, info in sorted(entities.items(), key=lambda x: (-len(x[1]["sources"]), x[0])):
        result.append({
            "variant": ent,
            "type": info["type"],
            "sources": list(info["sources"]),
            "phenotypes": list(info["phenotypes"]),
            "source_count": len(info["sources"]),
            "titles": list(info["titles"])[:3],  # top 3 paper titles
        })

    return {"variants": result, "total": len(result)}


@app.get("/api/gene-info")
async def gene_info_endpoint():
    """Return curated RARS1 gene information."""
    chunk_count = 0
    if pipeline:
        chunk_count = pipeline._col.count()

    return {
        "gene": {
            "symbol": "RARS1",
            "name": "Arginyl-tRNA Synthetase 1",
            "aliases": ["RARS", "ArgRS"],
            "chromosome": "5q35.1",
            "gene_id": "5917",
            "uniprot": "P54136",
            "function": "Catalyzes the attachment of arginine to its cognate tRNA during protein synthesis. Essential for proper aminoacylation and protein translation in all tissues, with particular importance in CNS myelination.",
            "links": {
                "omim": "https://omim.org/entry/107820",
                "genecards": "https://www.genecards.org/cgi-bin/carddisp.pl?gene=RARS1",
                "uniprot": "https://www.uniprot.org/uniprot/P54136",
                "ncbi": "https://www.ncbi.nlm.nih.gov/gene/5917",
                "clinvar": "https://www.ncbi.nlm.nih.gov/clinvar/?term=RARS1",
            }
        },
        "disease": {
            "name": "Hypomyelinating Leukodystrophy 9 (HLD9)",
            "omim": "616140",
            "inheritance": "Autosomal Recessive",
            "key_phenotypes": [
                "Hypomyelination on MRI",
                "Progressive spasticity",
                "Nystagmus",
                "Cerebellar atrophy",
                "Developmental delay",
                "Intellectual disability",
                "Microcephaly",
                "Peripheral neuropathy",
            ],
            "onset": "Infancy to early childhood",
            "prevalence": "Ultra-rare (<1 in 1,000,000)",
        },
        "corpus": {
            "indexed_chunks": chunk_count,
            "embedding_model": "pritamdeka/S-PubMedBert-MS-MARCO",
            "sources": "PubMed + Europe PMC preprints",
        }
    }

