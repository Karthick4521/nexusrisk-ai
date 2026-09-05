"""
NexusRisk AI - Local policy retrieval (RAG).

Reads data/policies/*.txt, splits into chunks, uses TF-IDF similarity to
retrieve relevant sections. No external vector database. Fails safe to []
if anything goes wrong so the app keeps working without policy grounding.
"""
from __future__ import annotations
from typing import List
from pathlib import Path
import re

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    _SKLEARN_OK = True
except Exception:
    _SKLEARN_OK = False

from .config import POLICY_DIR


def _chunk_text(text: str, max_chars: int = 500) -> List[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks = []
    for p in paragraphs:
        if len(p) <= max_chars:
            chunks.append(p)
        else:
            for i in range(0, len(p), max_chars):
                chunks.append(p[i:i + max_chars])
    return chunks


def _load_chunks() -> List[str]:
    chunks = []
    try:
        if not POLICY_DIR.exists():
            return []
        for path in sorted(Path(POLICY_DIR).glob("*.txt")):
            text = path.read_text(encoding="utf-8", errors="ignore")
            for chunk in _chunk_text(text):
                chunks.append(f"[{path.name}] {chunk}")
    except Exception:
        return []
    return chunks


def retrieve_relevant_policies(query: str, top_k: int = 4) -> List[str]:
    """Returns up to top_k relevant policy chunks. Fails safe to []."""
    try:
        chunks = _load_chunks()
        if not chunks:
            return []
        if not _SKLEARN_OK:
            # naive fallback: keyword overlap scoring
            q_words = set(re.findall(r"\w+", query.lower()))
            scored = []
            for c in chunks:
                c_words = set(re.findall(r"\w+", c.lower()))
                overlap = len(q_words & c_words)
                scored.append((overlap, c))
            scored.sort(key=lambda x: x[0], reverse=True)
            return [c for _, c in scored[:top_k] if _ > 0]

        vectorizer = TfidfVectorizer(stop_words="english")
        matrix = vectorizer.fit_transform(chunks + [query])
        sims = cosine_similarity(matrix[-1], matrix[:-1]).flatten()
        ranked = sorted(zip(sims, chunks), key=lambda x: x[0], reverse=True)
        results = [c for s, c in ranked[:top_k] if s > 0]
        return results
    except Exception:
        return []
