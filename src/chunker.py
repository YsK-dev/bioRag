"""
chunker.py — Medical-aware text chunker for genomic abstracts.

Core challenge: standard sentence/word splitters break HGVS variant notation
such as  c.5A>G  or  p.Met1?(p.Met1Thr)  in half, corrupting the variant
string and making it un-retrievable.  This module:

  1. Detects and *protects* medical patterns with unique placeholders.
  2. Splits on sentence boundaries.
  3. Accumulates sentences into size-bounded chunks with overlap.
  4. Restores the original medical strings before returning.
"""

import re
import uuid
from dataclasses import dataclass, field
from typing import List, Dict, Tuple

from config import CHUNK_SIZE, CHUNK_OVERLAP


# ── Protected pattern catalogue ───────────────────────────────────────────────
# Each entry is (name, compiled_regex).  Order matters – more specific
# patterns must appear before broader ones.
_PROTECTED_PATTERNS: List[Tuple[str, re.Pattern]] = [
    # HGVS coding DNA  e.g.  c.2T>C,  c.1577G>A,  c.1A>G
    ("hgvs_cdna",    re.compile(r'c\.\d+[-+]?\d*[A-Z]>[A-Z]', re.IGNORECASE)),
    # HGVS protein     e.g.  p.Met1Thr,  p.Arg378*,  p.(Leu12Pro)
    ("hgvs_prot",    re.compile(r'p\.[\(\[]?[A-Z][a-z]{2}\d+[A-Z*][a-z]*[\)\]]?', re.IGNORECASE)),
    # Combined HGVS    e.g.  (c.2T>C; p.Met1Thr)
    ("hgvs_combo",   re.compile(r'\(c\.\S+;\s*p\.\S+\)', re.IGNORECASE)),
    # RefSeq accession e.g.  NM_002926.3,  NP_002917.1
    ("refseq",       re.compile(r'[NX][MRP]_\d{6,9}(\.\d+)?', re.IGNORECASE)),
    # ClinVar / dbSNP  e.g.  rs12345678,  VCV000123456
    ("variantid",    re.compile(r'(rs\d{6,12}|VCV\d{9})', re.IGNORECASE)),
    # Chromosomal loci e.g.  5q35.1,  Xq22.3
    ("locus",        re.compile(r'\d{1,2}[pq]\d{1,2}(\.\d{1,3})?')),
    # Dosage / lab     e.g.  10 mg/kg,  3.5 mmol/L  (keep unit with number)
    ("dosage",       re.compile(r'\d+(\.\d+)?\s?(mg/kg|mmol/L|µmol/L|g/dL|IU/L)')),
]


@dataclass
class Chunk:
    text: str
    source_id: str          # PMID or DOI
    source_title: str
    source_date: str
    chunk_index: int
    source_url: str = ""


class MedicalChunker:
    """
    Sentence-aware chunker that protects genomic / medical notation from
    being split across chunk boundaries.
    """

    def __init__(
        self,
        chunk_size: int = CHUNK_SIZE,
        chunk_overlap: int = CHUNK_OVERLAP,
    ) -> None:
        self.chunk_size    = chunk_size
        self.chunk_overlap = chunk_overlap
        # Sentence boundary: period/semicolon/exclamation followed by whitespace
        # and an uppercase letter (avoids splitting "e.g. " or "vs. ").
        self._sent_re = re.compile(r'(?<=[.!;])\s+(?=[A-Z])')

    # ── public API ────────────────────────────────────────────────────────────

    def chunk_abstract(
        self,
        text: str,
        source_id: str,
        source_title: str = "",
        source_date: str  = "",
        source_url: str   = "",
    ) -> List[Chunk]:
        """
        Split *text* into overlap-aware chunks, preserving medical notation.
        Returns a list of Chunk objects with full provenance metadata.
        """
        if not text or not text.strip():
            return []

        protected_text, registry = self._protect(text)
        sentences = self._split_sentences(protected_text)
        raw_chunks = self._accumulate(sentences)
        chunks = []

        for idx, raw in enumerate(raw_chunks):
            restored = self._restore(raw, registry)
            chunks.append(
                Chunk(
                    text=restored.strip(),
                    source_id=source_id,
                    source_title=source_title,
                    source_date=source_date,
                    source_url=source_url,
                    chunk_index=idx,
                )
            )

        return chunks

    # ── internals ─────────────────────────────────────────────────────────────

    def _protect(self, text: str) -> Tuple[str, Dict[str, str]]:
        """
        Replace each medical token with a UUID placeholder.
        Returns (modified_text, registry) where registry maps placeholder→original.
        """
        registry: Dict[str, str] = {}

        for _name, pattern in _PROTECTED_PATTERNS:
            def _replacer(m: re.Match, reg=registry) -> str:
                token = m.group(0)
                # Re-use the same placeholder if we've already seen this token
                for ph, orig in reg.items():
                    if orig == token:
                        return ph
                ph = f"__MED_{uuid.uuid4().hex[:12].upper()}__"
                reg[ph] = token
                return ph

            text = pattern.sub(_replacer, text)

        return text, registry

    @staticmethod
    def _restore(text: str, registry: Dict[str, str]) -> str:
        for placeholder, original in registry.items():
            text = text.replace(placeholder, original)
        return text

    def _split_sentences(self, text: str) -> List[str]:
        parts = self._sent_re.split(text)
        # Further break on newlines (abstract sections often separated by \n)
        sentences: List[str] = []
        for part in parts:
            for line in part.splitlines():
                line = line.strip()
                if line:
                    sentences.append(line)
        return sentences

    def _accumulate(self, sentences: List[str]) -> List[str]:
        """
        Greedily accumulate sentences until chunk_size is reached, then start
        a new chunk that begins by repeating the last *overlap* characters of
        the previous chunk.
        """
        chunks: List[str] = []
        current_parts: List[str] = []
        current_len = 0

        for sent in sentences:
            sent_len = len(sent) + 1  # +1 for the space we'll join with

            if current_len + sent_len > self.chunk_size and current_parts:
                # Flush current chunk
                chunk_text = " ".join(current_parts)
                chunks.append(chunk_text)

                # Build overlap: walk backwards through current_parts until
                # we've collected chunk_overlap characters.
                overlap_parts: List[str] = []
                overlap_len = 0
                for p in reversed(current_parts):
                    if overlap_len + len(p) + 1 <= self.chunk_overlap:
                        overlap_parts.insert(0, p)
                        overlap_len += len(p) + 1
                    else:
                        break

                current_parts = overlap_parts + [sent]
                current_len   = sum(len(p) + 1 for p in current_parts)
            else:
                current_parts.append(sent)
                current_len += sent_len

        if current_parts:
            chunks.append(" ".join(current_parts))

        return chunks
