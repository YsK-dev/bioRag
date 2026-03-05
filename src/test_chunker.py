"""
tests/test_chunker.py — Unit tests for MedicalChunker.

Run with:  pytest tests/
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from chunker import MedicalChunker, Chunk


VARIANT_ABSTRACT = (
    "We report two siblings with compound heterozygous RARS1 mutations: "
    "c.5A>G (p.Met1?) and c.1577G>A (p.Arg526His). "
    "Brain MRI showed hypomyelination and cerebellar atrophy. "
    "Both patients had early-onset nystagmus and spasticity consistent with HLD9. "
    "Functional studies confirmed loss of arginyl-tRNA synthetase activity. "
    "These findings expand the mutational spectrum of NM_002926.3."
)

SHORT_ABSTRACT = "RARS1 causes HLD9. Patients have nystagmus."


class TestMedicalChunker:
    def setup_method(self):
        self.chunker = MedicalChunker(chunk_size=200, chunk_overlap=40)

    def test_returns_chunks(self):
        chunks = self.chunker.chunk_abstract(
            VARIANT_ABSTRACT, source_id="12345678"
        )
        assert len(chunks) >= 1
        assert all(isinstance(c, Chunk) for c in chunks)

    def test_variants_intact(self):
        """Critical: HGVS variant strings must never be split across chunks."""
        chunks = self.chunker.chunk_abstract(
            VARIANT_ABSTRACT, source_id="12345678"
        )
        full_text = " ".join(c.text for c in chunks)
        assert "c.5A>G" in full_text, "Coding variant was destroyed during chunking"
        assert "p.Met1?" in full_text, "Protein notation was destroyed during chunking"
        assert "c.1577G>A" in full_text, "Second variant was destroyed"
        assert "p.Arg526His" in full_text, "Second protein change destroyed"

    def test_refseq_intact(self):
        chunks = self.chunker.chunk_abstract(
            VARIANT_ABSTRACT, source_id="12345678"
        )
        full_text = " ".join(c.text for c in chunks)
        assert "NM_002926.3" in full_text, "RefSeq accession was split"

    def test_metadata_propagated(self):
        chunks = self.chunker.chunk_abstract(
            VARIANT_ABSTRACT,
            source_id="99999999",
            source_title="Test Title",
            source_date="2024",
            source_url="https://pubmed.ncbi.nlm.nih.gov/99999999/",
        )
        for c in chunks:
            assert c.source_id == "99999999"
            assert c.source_title == "Test Title"
            assert c.source_date == "2024"

    def test_empty_abstract_returns_no_chunks(self):
        chunks = self.chunker.chunk_abstract("", source_id="0")
        assert chunks == []

    def test_short_abstract_single_chunk(self):
        chunks = self.chunker.chunk_abstract(SHORT_ABSTRACT, source_id="1")
        assert len(chunks) == 1

    def test_chunk_index_sequential(self):
        chunks = self.chunker.chunk_abstract(
            VARIANT_ABSTRACT * 5,   # long enough to generate multiple chunks
            source_id="42"
        )
        for i, c in enumerate(chunks):
            assert c.chunk_index == i


class TestGuardrail:
    def test_passes_on_grounded_response(self):
        from guardrail import apply_guardrail

        contexts = [{
            "document": "Patient had c.5A>G variant and showed hypomyelination.",
            "metadata": {"pmid": "12345678"},
        }]
        response = "The variant c.5A>G was reported [PMID: 12345678] with hypomyelination."
        result = apply_guardrail(response, contexts)
        assert result.passed

    def test_flags_unverified_variant(self):
        from guardrail import apply_guardrail

        contexts = [{
            "document": "Patients had nystagmus and spasticity.",
            "metadata": {"pmid": "12345678"},
        }]
        # Variant c.9999Z>Q is NOT in the context
        response = "The variant c.9999A>G was found in the patient [PMID: 12345678]."
        result = apply_guardrail(response, contexts)
        # c.9999A>G should be flagged as unverified
        assert len(result.unverified_variants) > 0

    def test_flags_fabricated_pmid(self):
        from guardrail import apply_guardrail

        contexts = [{
            "document": "RARS1 causes leukodystrophy.",
            "metadata": {"pmid": "11111111"},
        }]
        # PMID 99999999 is NOT in the retrieved metadata
        response = "RARS1 causes HLD9 [PMID: 99999999]."
        result = apply_guardrail(response, contexts)
        assert "99999999" in result.fabricated_pmids
        assert not result.passed

    def test_passes_with_no_variants_or_pmids(self):
        from guardrail import apply_guardrail

        contexts = [{"document": "Some text.", "metadata": {"pmid": "11111111"}}]
        response = "This system indexes RARS1 literature."
        result = apply_guardrail(response, contexts)
        assert result.passed
