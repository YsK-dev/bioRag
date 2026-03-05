"""
rag_pipeline.py — Retrieval-Augmented Generation pipeline for RARS1 queries.

Flow
----
user_query
    → semantic search (ChromaDB)
    → context assembly with provenance metadata
    → structured LLM prompt (Claude)
        ↳ enforces: citations | phenotype vs variant distinction | scope check
    → guardrail verification
    → RAGResponse (answer + citations + guardrail result)
"""

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional

import ollama
import chromadb
from chromadb.utils import embedding_functions

from config import (
    OLLAMA_BASE_URL,
    LLM_MODEL,
    MAX_TOKENS,
    TOP_K,
    CHROMA_DIR,
    COLLECTION_NAME,
    CHROMA_HOST,
    CHROMA_PORT,
    EMBEDDING_MODEL,
    FALLBACK_EMBEDDING_MODEL,
)
from guardrail import apply_guardrail, GuardrailResult

log = logging.getLogger("rag_pipeline")

# ─────────────────────────────────────────────────────────────────────────────
#  Response dataclass
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class RAGResponse:
    query: str
    answer: str
    citations: List[Dict]  # [{pmid, title, url, date, journal}]
    contexts_used: List[Dict]  # raw retrieved chunks
    guardrail: Optional[GuardrailResult] = None
    in_scope: bool = True  # False if query is off-topic for RARS1

    def pretty_print(self) -> str:
        lines = [
            "=" * 70,
            f"QUERY:  {self.query}",
            "-" * 70,
        ]

        if not self.in_scope:
            lines += [
                "[OUT-OF-SCOPE]",
                self.answer,
                "=" * 70,
            ]
            return "\n".join(lines)

        lines.append(self.answer)
        lines.append("")
        lines.append(
            "--- Citations ---------------------------------------------------"
        )
        seen = set()
        for c in self.citations:
            pmid = c.get("pmid", "")
            if pmid in seen:
                continue
            seen.add(pmid)
            lines.append(
                f"  * PMID {pmid} -- {c.get('title','')[:80]}...\n"
                f"    {c.get('url','')}  ({c.get('date','')})"
            )

        if self.guardrail:
            lines.append("")
            lines.append(
                "--- Guardrail ---------------------------------------------------"
            )
            lines.append(f"  {self.guardrail.summary}")
            if self.guardrail.warnings:
                for w in self.guardrail.warnings:
                    lines.append(f"  [!] {w}")

        lines.append("=" * 70)
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
#  Prompt templates
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are a clinical genomics assistant specialising in rare genetic diseases.
Your task is to synthesise information from PubMed abstracts about the gene RARS1
(Arginyl-tRNA Synthetase 1) and its associated disease Hypomyelinating Leukodystrophy 9 (HLD9).

HLD9 is a white matter disorder characterised by defective myelination of the central nervous
system.  When describing RARS1-associated phenotypes, always note the white matter / myelin
involvement where relevant.

STRICT RULES you must follow:
1. Only use information present in the provided SOURCE DOCUMENTS below.
2. Clearly distinguish between:
   • VARIANTS — specific genetic mutations using HGVS notation (e.g., c.5A>G, p.Met1Thr).
   • PHENOTYPES — observed clinical traits (e.g., hypomyelination / white matter abnormalities,
     nystagmus, spasticity, intellectual disability).
   • DISEASES — named diagnoses (e.g., Hypomyelinating Leukodystrophy 9 / HLD9).
3. Every factual claim MUST be followed by its citation in the format  [PMID: XXXXXXXX].
   If a fact comes from a preprint DOI, use  [DOI: xx.xxxxx/xxxxx].
4. If the query asks about something NOT covered by the source documents, say so explicitly.
   Do NOT invent information.
5. Structure your response with clearly labelled sections when appropriate:
   "Variants Reported", "Phenotypes / Clinical Features", "Disease Association".
"""

_USER_TEMPLATE = """SOURCE DOCUMENTS (retrieved from PubMed / preprint databases):
{context_block}

─────────────────────────────────────────────────────────────────────
USER QUERY: {query}
─────────────────────────────────────────────────────────────────────

Please answer the query using ONLY the source documents above.
Cite every claim with [PMID: XXXXXXXX] or [DOI: ...].
If the source documents do not contain information relevant to this query,
state that clearly and do NOT speculate."""

_SCOPE_CHECK_PROMPT = """You are a strict relevance classifier.

The RARS1 Genomic-RAG system indexes literature about:
  - Gene: RARS1 (Arginyl-tRNA Synthetase 1)
  - Disease: Hypomyelinating Leukodystrophy 9 (HLD9)
  - Related: white matter disorders, aminoacyl-tRNA synthetase deficiencies

User query: "{query}"

Answer ONLY with one word: RELEVANT or IRRELEVANT.
A query is IRRELEVANT if it clearly asks about a different gene, a completely
unrelated disease, or non-scientific topics."""


# ─────────────────────────────────────────────────────────────────────────────
#  Pipeline class
# ─────────────────────────────────────────────────────────────────────────────


class RAGPipeline:
    """
    End-to-end RAG pipeline:
      retrieve → assemble context → call LLM → apply guardrail → return.
    """

    def __init__(self) -> None:
        self._llm = ollama.Client(host=OLLAMA_BASE_URL)
        self._col = self._load_collection()

    # ── setup ─────────────────────────────────────────────────────────────────

    def _load_collection(self) -> chromadb.Collection:
        """
        Initialise the embedding function and connect to ChromaDB.

        Uses an HTTP client when CHROMA_HOST is configured (Docker / remote),
        otherwise falls back to a local PersistentClient.  Falls back from the
        biomedical PubMedBERT model to all-MiniLM-L6-v2 when the primary model
        is unavailable.
        """
                model_name=EMBEDDING_MODEL
            )
        except Exception:
            ef = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=FALLBACK_EMBEDDING_MODEL
            )
        if CHROMA_HOST:
            client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
        else:
            client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        col = client.get_or_create_collection(COLLECTION_NAME, embedding_function=ef)
        log.info(f"Collection loaded: {col.count()} chunks")
        return col

    # ── scope check ───────────────────────────────────────────────────────────

    # Keywords that indicate a query is related to RARS1 / HLD9 genomics.
    _SCOPE_KEYWORDS = {
        # Gene & disease names
        "rars1",
        "rars",
        "hld9",
        "arginyl",
        "trna synthetase",
        "hypomyelinating leukodystrophy",
        "leukodystrophy",
        # Genomic / clinical terms likely used in legitimate queries
        "variant",
        "mutation",
        "phenotype",
        "genotype",
        "allele",
        "homozygous",
        "heterozygous",
        "compound heterozygous",
        "hypomyelination",
        "myelination",
        "white matter",
        "nystagmus",
        "spasticity",
        "ataxia",
        "microcephaly",
        "mri",
        "neuroimaging",
        "cerebellum",
        "aminoacyl",
        "trna",
        "synthetase",
        "hgvs",
        "c.5a>g",
        "p.met1thr",
        "exon",
        "intron",
        "pubmed",
        "pmid",
        "clinical",
        "patient",
        "gene",
        "genomic",
        "genetic",
        "rare disease",
    }

    def _is_in_scope(self, query: str) -> bool:
        """
        Fast keyword-based relevance classifier — eliminates the ~16 s Ollama
        round-trip that the old LLM scope check required.
        Returns True if any RARS1-related keyword appears in the query.
        """
        q_lower = query.lower()
        for kw in self._SCOPE_KEYWORDS:
            if kw in q_lower:
                return True
        log.info("Query flagged as out-of-scope (keyword check).")
        return False

    # ── retrieval ─────────────────────────────────────────────────────────────

    def retrieve(self, query: str, top_k: int = TOP_K) -> List[Dict]:
        """
        Semantic search in ChromaDB.
        Returns a list of dicts: {document, metadata, distance}.
        """
        results = self._col.query(
            query_texts=[query],
            n_results=min(top_k, self._col.count()),
            include=["documents", "metadatas", "distances"],
        )

        contexts = []
        docs = results["documents"][0]
        metas = results["metadatas"][0]
        dists = results["distances"][0]

        for doc, meta, dist in zip(docs, metas, dists):
            contexts.append(
                {
                    "document": doc,
                    "metadata": meta,
                    "distance": dist,
                }
            )

        log.info(f"Retrieved {len(contexts)} chunks (top distance: {dists[0]:.4f})")
        return contexts

    # ── context assembly ──────────────────────────────────────────────────────

    @staticmethod
    def _build_context_block(contexts: List[Dict]) -> str:
        """
        Format retrieved chunks into a numbered source block for the LLM prompt.

        Each source is labelled with its PMID, publication date, journal, title,
        URL, and the raw chunk text so the model can cite them precisely.
        """
        for i, ctx in enumerate(contexts, 1):
            meta = ctx["metadata"]
            pmid = meta.get("pmid", "")
            url = meta.get("url", f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/")
            parts.append(
                f"[Source {i} | PMID: {pmid} | {meta.get('date','')} | "
                f"{meta.get('journal','')}]\n"
                f"Title: {meta.get('title','')}\n"
                f"URL: {url}\n"
                f"Text: {ctx['document']}"
            )
        return "\n\n".join(parts)

    # ── LLM synthesis ─────────────────────────────────────────────────────────

    def _synthesise(self, query: str, contexts: List[Dict]) -> str:
        """
        Call the local Ollama LLM with a structured prompt and return the full
        response text.

        Parameters
        ----------
        query : str
            The user question.
        contexts : list[dict]
            Retrieved chunks from ChromaDB (used to build the source block).
        """
        user_msg = _USER_TEMPLATE.format(
            context_block=context_block,
            query=query,
        )

        response = self._llm.chat(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            options={"num_predict": min(MAX_TOKENS, 1024)},
        )
        return response["message"]["content"]

    def _synthesise_stream(self, query: str, contexts: List[Dict]):
        """Generator that yields token strings as they arrive from Ollama."""
        context_block = self._build_context_block(contexts)
        user_msg = _USER_TEMPLATE.format(
            context_block=context_block,
            query=query,
        )

        stream = self._llm.chat(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            options={"num_predict": min(MAX_TOKENS, 1024)},
            stream=True,
        )
        for chunk in stream:
            token = chunk["message"]["content"]
            if token:
                yield token

    # ── out-of-scope handler ──────────────────────────────────────────────────

    def _out_of_scope_response(self, query: str) -> RAGResponse:
        """
        Build a canned RAGResponse for queries that fall outside the RARS1 /
        HLD9 domain, without calling the LLM or ChromaDB.
        """
            "[OUT-OF-SCOPE] This query does not appear to be related to RARS1 or "
            "Hypomyelinating Leukodystrophy 9 (HLD9).\n\n"
            "This system is specialised for RARS1 genomics. If you intended to ask about "
            "RARS1, please rephrase your question. For questions about other genes or "
            "diseases, please consult PubMed directly."
        )
        return RAGResponse(
            query=query,
            answer=answer,
            citations=[],
            contexts_used=[],
            in_scope=False,
        )

    # ── public entrypoint ─────────────────────────────────────────────────────

    def query(self, question: str, run_guardrail: bool = True) -> RAGResponse:
        """
        Full RAG pipeline: scope check → retrieve → synthesise → guardrail.
        """
        log.info(f"Query: {question!r}")

        # 1. Scope check
        if not self._is_in_scope(question):
            log.info("Query flagged as out-of-scope.")
            return self._out_of_scope_response(question)

        # 2. Retrieve relevant chunks
        contexts = self.retrieve(question)

        # 3. LLM synthesis
        answer = self._synthesise(question, contexts)

        # 4. Collect citations from retrieved metadata
        citations = self._collect_citations(contexts)

        # 5. Guardrail
        guardrail_result = None
        if run_guardrail:
            guardrail_result = apply_guardrail(answer, contexts)

        return RAGResponse(
            query=question,
            answer=answer,
            citations=citations,
            contexts_used=contexts,
            guardrail=guardrail_result,
            in_scope=True,
        )

    def _collect_citations(self, contexts: List[Dict]) -> List[Dict]:
        """Extract unique citations from retrieved contexts."""
        citations = []
        seen_pmids: set = set()
        for ctx in contexts:
            pmid = ctx["metadata"].get("pmid", "")
            if pmid and pmid not in seen_pmids:
                seen_pmids.add(pmid)
                citations.append(
                    {
                        "pmid": pmid,
                        "title": ctx["metadata"].get("title", ""),
                        "url": ctx["metadata"].get("url", ""),
                        "date": ctx["metadata"].get("date", ""),
                        "journal": ctx["metadata"].get("journal", ""),
                    }
                )
        return citations

    def query_stream(self, question: str):
        """
        Streaming RAG pipeline. Yields dicts that the API layer
        serialises as SSE events:
          {"event": "scope",     "data": {"in_scope": bool}}
          {"event": "citations", "data": [...]}
          {"event": "token",     "data": "..."}
          {"event": "guardrail", "data": {...}}
          {"event": "done",      "data": {}}
        """
        import json

        log.info(f"Query (stream): {question!r}")

        # 1. Scope check (instant keyword check)
        if not self._is_in_scope(question):
            log.info("Query flagged as out-of-scope (stream).")
            resp = self._out_of_scope_response(question)
            yield {"event": "scope", "data": {"in_scope": False}}
            yield {"event": "token", "data": resp.answer}
            yield {"event": "done", "data": {}}
            return

        yield {"event": "scope", "data": {"in_scope": True}}

        # 2. Retrieve
        contexts = self.retrieve(question)
        citations = self._collect_citations(contexts)
        yield {"event": "citations", "data": citations}

        # 3. Stream tokens
        full_answer = []
        for token in self._synthesise_stream(question, contexts):
            full_answer.append(token)
            yield {"event": "token", "data": token}

        # 4. Guardrail (run on full answer)
        answer_text = "".join(full_answer)
        guardrail_result = apply_guardrail(answer_text, contexts)
        yield {
            "event": "guardrail",
            "data": {
                "passed": guardrail_result.passed,
                "warnings": guardrail_result.warnings,
                "unverified_variants": guardrail_result.unverified_variants,
                "fabricated_pmids": guardrail_result.fabricated_pmids,
                "summary": guardrail_result.summary,
            },
        }

        yield {"event": "done", "data": {}}
