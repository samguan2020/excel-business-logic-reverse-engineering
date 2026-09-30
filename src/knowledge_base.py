"""
knowledge_base.py - Local knowledge retrieval inspired by Foundry IQ
-----------------------------------------------
A minimal, local, permission-tagged knowledge base built on ChromaDB.

Selected concepts approximated at prototype scale, not product parity:
  - Knowledge Source  -> a `source` tag on each ingested chunk (e.g. "excel-workbook",
                          "finance-glossary", "prior-run-docs")
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
    def __init__(self, persist_dir: str = ".chroma_kb", collection_name: str = "finance_excel_kb"):
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


FINANCE_GLOSSARY_SEED = [
    ("gloss-npv", "NPV (Net Present Value): discounted sum of future cash flows minus initial investment.", "finance-glossary"),
    ("gloss-yoy", "YoY (Year over Year): percentage change of a metric compared to the same period last year.", "finance-glossary"),
    ("gloss-variance", "Variance analysis: comparison of actual vs. forecast/budget figures to explain deviations.", "finance-glossary"),
    ("gloss-accrual", "Accrual: recognizing revenue/expense when incurred, not when cash changes hands.", "finance-glossary"),
]


def seed_glossary(kb: KnowledgeBase) -> None:
    kb.ingest_many(FINANCE_GLOSSARY_SEED)
