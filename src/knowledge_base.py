"""
knowledge_base.py - Local knowledge retrieval inspired by Foundry IQ
-----------------------------------------------
A minimal, local, permission-tagged knowledge base built on ChromaDB.

Selected concepts approximated at prototype scale, not product parity:
  - Knowledge Source  -> a `source` tag on each ingested chunk (e.g. "excel-workbook",
                          "business-glossary", "prior-run-docs")
  - Knowledge Base    -> a single Chroma collection shared by local runs
  - Agentic retrieval -> `retrieve()` supports source filtering + top-k semantic search,
                          which the agent calls before asking the LLM to draft docs.
  - Permission-aware  -> `allowed_sources` param simulates a coarse allow-list; swap for
                          real ACL/Purview-label checks in a production build.
"""
from __future__ import annotations

from typing import Iterable, List, Optional

import chromadb
from chromadb.utils import embedding_functions


class KnowledgeBase:
    def __init__(self, persist_dir: str = ".chroma_kb", collection_name: str = "business_logic_kb"):
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._embedder = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        self._collection = self._client.get_or_create_collection(
            name=collection_name, embedding_function=self._embedder
        )

    def ingest(self, doc_id: str, text: str, source: str, extra_metadata: Optional[dict] = None) -> None:
        metadata = {"source": source}
        if extra_metadata:
            metadata.update(extra_metadata)
        self._collection.upsert(ids=[doc_id], documents=[text], metadatas=[metadata])

    def ingest_many(self, items: Iterable[tuple[str, str, str]]) -> None:
        for doc_id, text, source in items:
            self.ingest(doc_id, text, source)

    def retrieve(self, query: str, top_k: int = 5, allowed_sources: Optional[List[str]] = None) -> List[dict]:
        where = {"source": {"$in": allowed_sources}} if allowed_sources else None
        results = self._collection.query(query_texts=[query], n_results=top_k, where=where)
        hits = []
        for i in range(len(results["ids"][0])):
            hits.append(
                {
                    "id": results["ids"][0][i],
                    "text": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "distance": results["distances"][0][i] if results.get("distances") else None,
                }
            )
        return hits


BUSINESS_GLOSSARY_SEED = [
    ("gloss-kpi", "KPI (Key Performance Indicator): a measurable value used to track progress toward a business objective.", "business-glossary"),
    ("gloss-period-change", "Period-over-period change: percentage change of a metric compared with the preceding period.", "business-glossary"),
    ("gloss-variance", "Variance analysis: comparison of actual and planned values to explain deviations.", "business-glossary"),
    ("gloss-contribution", "Unit contribution: unit price minus unit cost before shared or fixed costs.", "business-glossary"),
]


def seed_glossary(kb: KnowledgeBase) -> None:
    kb.ingest_many(BUSINESS_GLOSSARY_SEED)
