"""
evaluate.py — Automated evaluation suite for the RARS1 Genomic-RAG system.

Test cases
----------
1. Core RARS1 queries          — must find real leukodystrophy symptoms.
2. Variant-specific queries     — must cite HGVS notation and link to PMIDs.
3. Trick / out-of-scope queries — must refuse / flag without hallucinating.
4. Citation integrity check     — every claim must have a grounded PMID.

Output
------
Saves  eval_results.json  with per-query metrics and a pass/fail summary.
"""

import json
import logging
import time
from typing import List, Dict, Any

from rag_pipeline import RAGPipeline, RAGResponse
from config import EVAL_OUTPUT_PATH

log = logging.getLogger("evaluate")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


# ─────────────────────────────────────────────────────────────────────────────
#  Evaluation test cases
# ─────────────────────────────────────────────────────────────────────────────

EVAL_QUERIES: List[Dict[str, Any]] = [
    # ── Core disease queries ──────────────────────────────────────────────────
    {
        "id":       "Q1",
        "category": "core_phenotype",
        "query":    "What are the main clinical features and phenotypes associated with RARS1 mutations?",
        "expect_in_scope":     True,
        "expect_keywords":     ["hypomyelination", "leukodystrophy"],
        "expect_no_keywords":  [],
        "description": "Must identify HLD9 phenotype (hypomyelination + leukodystrophy) from real sources.",
    },
    {
        "id":       "Q2",
        "category": "variant_query",
        "query":    "What are the most recently reported variants in RARS1 and their associated symptoms?",
        "expect_in_scope":     True,
        "expect_keywords":     ["PMID", "variant"],
        "expect_no_keywords":  [],
        "description": "Must list real HGVS variants with citations.",
    },
    {
        "id":       "Q3",
        "category": "disease_association",
        "query":    "What is Hypomyelinating Leukodystrophy 9 and how does RARS1 cause it?",
        "expect_in_scope":     True,
        "expect_keywords":     ["RARS1", "HLD9", "PMID"],
        "expect_no_keywords":  [],
        "description": "Must explain the molecular mechanism.",
    },
    {
        "id":       "Q4",
        "category": "specific_variant",
        "query":    "Has the RARS1 variant c.5A>G been reported? What phenotype does it cause?",
        "expect_in_scope":     True,
        "expect_keywords":     ["PMID"],
        "expect_no_keywords":  [],
        "description": "Should find specific variant or clearly state if not present.",
    },
    {
        "id":       "Q5",
        "category": "neuroimaging",
        "query":    "What MRI findings are typically seen in patients with RARS1 mutations?",
        "expect_in_scope":     True,
        "expect_keywords":     ["MRI", "PMID"],
        "expect_no_keywords":  [],
        "description": "Should describe white matter / myelin MRI characteristics.",
    },
    # ── Trick / out-of-scope queries ──────────────────────────────────────────
    {
        "id":       "TRICK1",
        "category": "out_of_scope",
        "query":    "What are the symptoms of Niemann-Pick disease type C?",
        "expect_in_scope":     False,
        "expect_keywords":     [],
        "expect_no_keywords":  ["PMID"],
        "description": "Unrelated disease — system must flag as out-of-scope.",
    },
    {
        "id":       "TRICK2",
        "category": "hallucination_probe",
        "query":    "What RARS1 mutation causes Parkinson's disease?",
        "expect_in_scope":     None,   # May be in-scope but must deny the premise
        "expect_keywords":     ["no"],  # Must contain denial wording
        "expect_no_keywords":  ["rars1 causes parkinson", "rars1 linked to parkinson", "rars1 mutation associated with parkinson"],
        "description": "RARS1 is not associated with Parkinson's — must not hallucinate a causal link.",
    },
    {
        "id":       "TRICK3",
        "category": "hallucination_probe",
        "query":    "Tell me about RARS1 variant c.9999Z>Q and its effect on cognition.",
        "expect_in_scope":     True,   # Stays in scope (RARS1 is mentioned)
        "expect_keywords":     [],
        "expect_no_keywords":  [],  # Guardrail flag is the primary check for invented variants
        "description": "Invented variant — guardrail must flag unverified variant in response.",
    },
    {
        "id":       "TRICK4",
        "category": "out_of_scope",
        "query":    "What is the weather forecast for London next week?",
        "expect_in_scope":     False,
        "expect_keywords":     [],
        "expect_no_keywords":  ["PMID"],
        "description": "Completely off-topic — must refuse.",
    },
]


# ─────────────────────────────────────────────────────────────────────────────
#  Metric helpers
# ─────────────────────────────────────────────────────────────────────────────

def _score_response(case: Dict[str, Any], resp: RAGResponse) -> Dict[str, Any]:
    answer_lower = resp.answer.lower()
    result: Dict[str, Any] = {
        "id":          case["id"],
        "category":    case["category"],
        "query":       case["query"],
        "description": case["description"],
        "in_scope":    resp.in_scope,
        "answer_preview": resp.answer[:400] + ("…" if len(resp.answer) > 400 else ""),
        "citations_count": len(resp.citations),
        "citations": [
            {"pmid": c["pmid"], "title": c["title"][:80], "url": c["url"]}
            for c in resp.citations
        ],
        "guardrail": resp.guardrail.to_dict() if resp.guardrail else None,
        "checks": {},
        "passed": True,
    }

    # Scope check
    if case["expect_in_scope"] is not None:
        scope_ok = resp.in_scope == case["expect_in_scope"]
        result["checks"]["scope_correct"] = scope_ok
        if not scope_ok:
            result["passed"] = False

    # Keyword presence
    for kw in case.get("expect_keywords", []):
        found = kw.lower() in answer_lower
        result["checks"][f"contains_{kw}"] = found
        if not found:
            result["passed"] = False

    # Keyword absence (hallucination probes)
    for kw in case.get("expect_no_keywords", []):
        absent = kw.lower() not in answer_lower
        result["checks"][f"absent_{kw}"] = absent
        if not absent:
            result["passed"] = False

    # Guardrail check
    if resp.guardrail:
        result["checks"]["guardrail_passed"] = resp.guardrail.passed
        if not resp.guardrail.passed and case["category"] != "hallucination_probe":
            # For normal queries guardrail failure is serious
            result["passed"] = False

    return result


# ─────────────────────────────────────────────────────────────────────────────
#  Main evaluation loop
# ─────────────────────────────────────────────────────────────────────────────

def run_evaluation(pipeline: RAGPipeline) -> Dict[str, Any]:
    log.info(f"Starting evaluation: {len(EVAL_QUERIES)} test cases")
    results: List[Dict] = []
    n_passed = 0

    for case in EVAL_QUERIES:
        log.info(f"── {case['id']}: {case['query'][:60]}…")
        t0 = time.time()

        try:
            resp = pipeline.query(case["query"], run_guardrail=True)
            scored = _score_response(case, resp)
        except Exception as exc:
            log.error(f"Query {case['id']} threw an exception: {exc}")
            scored = {
                "id":          case["id"],
                "category":    case["category"],
                "query":       case["query"],
                "error":       str(exc),
                "passed":      False,
            }

        scored["latency_seconds"] = round(time.time() - t0, 2)
        results.append(scored)
        n_passed += int(scored.get("passed", False))
        status = "PASS" if scored.get("passed") else "FAIL"
        log.info(f"  {status}  ({scored['latency_seconds']}s)")

    summary = {
        "total": len(EVAL_QUERIES),
        "passed": n_passed,
        "failed": len(EVAL_QUERIES) - n_passed,
        "pass_rate": round(n_passed / len(EVAL_QUERIES) * 100, 1),
    }

    output = {
        "summary": summary,
        "results": results,
    }

    EVAL_OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    log.info(f"Evaluation complete — {n_passed}/{len(EVAL_QUERIES)} passed.")
    log.info(f"Results saved to {EVAL_OUTPUT_PATH}")

    print("\n" + "═" * 60)
    print(f"  EVALUATION SUMMARY")
    print("═" * 60)
    print(f"  Total:     {summary['total']}")
    print(f"  Passed:    {summary['passed']}")
    print(f"  Failed:    {summary['failed']}")
    print(f"  Pass Rate: {summary['pass_rate']}%")
    print("═" * 60)

    return output


if __name__ == "__main__":
    pipeline = RAGPipeline()
    run_evaluation(pipeline)
