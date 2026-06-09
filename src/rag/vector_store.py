from __future__ import annotations

from pathlib import Path
from typing import Any


import chromadb
from rag.parser import parse_policy_markdown


class ChromaPolicyStore:
    """Student scaffold for the real Chroma-backed policy index."""

    def __init__(
        self,
        persist_directory: Path,
        embedding_model: Any,
        collection_name: str = "policy_chunks",
    ) -> None:
        # Ensure persist directory exists
        persist_directory.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(persist_directory))
        self.collection = self.client.get_or_create_collection(name=collection_name)
        self.embedding_model = embedding_model

    def ensure_index(self, markdown_path: Path) -> None:
        if self.collection.count() == 0:
            self.rebuild(markdown_path)

    def rebuild(self, markdown_path: Path) -> None:
        try:
            existing = self.collection.get()
            if existing and existing["ids"]:
                self.collection.delete(ids=existing["ids"])
        except Exception:
            pass

        if not markdown_path.exists():
            raise FileNotFoundError(f"Markdown policy file not found at {markdown_path}")

        with open(markdown_path, "r", encoding="utf-8") as f:
            markdown_text = f.read()

        chunks = parse_policy_markdown(markdown_text)
        if not chunks:
            return

        ids = [f"chunk_{i}" for i in range(len(chunks))]
        documents = [chunk["rendered_text"] for chunk in chunks]
        metadatas = [
            {
                "section_h2": chunk["section_h2"] or "",
                "section_h3": chunk["section_h3"] or "",
                "citation": chunk["citation"] or "",
            }
            for chunk in chunks
        ]

        embeddings = self.embedding_model.embed_documents(documents)

        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=documents,
        )

    def search(self, query: str, top_k: int = 4) -> list[dict[str, Any]]:
        query_embedding = self.embedding_model.embed_query(query)
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
        )

        hits = []
        if results and "documents" in results and results["documents"]:
            docs = results["documents"][0]
            metas = results["metadatas"][0]
            dists = results["distances"][0]
            for doc, meta, dist in zip(docs, metas, dists):
                hits.append({
                    "citation": meta.get("citation", "") if meta else "",
                    "content": doc,
                    "distance": dist,
                })
        return hits



