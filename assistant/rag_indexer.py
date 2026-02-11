from sentence_transformers import SentenceTransformer
import chromadb
from pathlib import Path
from typing import List, Dict
import textwrap

class RAGIndexer:
    """Indexes documentation and makes it searchable via embeddings."""
    def __init__(self, persist_dir: str = "data/chroma"):
        self.embedder = SentenceTransformer("all-MiniLM-L6-v2")
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.collection = self.client.get_or_create_collection("kaal_kb")

    def _chunk_text(self, text: str, chunk_size: int = 500) -> List[str]:
        return textwrap.wrap(text, chunk_size, break_long_words=False, replace_whitespace=False)

    def index_document(self, text: str, metadata: Dict):
        """Split text into chunks, embed, and store in ChromaDB."""
        chunks = self._chunk_text(text)
        embeddings = self.embedder.encode(chunks).tolist()
        ids = [f"{metadata['id']}_{i}" for i in range(len(chunks))]
        self.collection.add(
            documents=chunks,
            embeddings=embeddings,
            metadatas=[metadata] * len(chunks),
            ids=ids
        )

    def search(self, query: str, n_results: int = 5) -> List[str]:
        """Retrieve the most relevant document chunks for a query."""
        q_emb = self.embedder.encode([query]).tolist()
        results = self.collection.query(query_embeddings=q_emb, n_results=n_results)
        return results["documents"][0] if results["documents"] else []
