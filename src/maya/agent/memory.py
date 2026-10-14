"""Maya memory — short-term (SQLite checkpointer) and long-term (ChromaDB)."""

import asyncio
import logging
from pathlib import Path
import sqlite3
from typing import Any
import uuid

from maya.core.config import get_config

logger = logging.getLogger(__name__)

try:
    from langgraph.checkpoint.sqlite import SqliteSaver
    SQLITE_SAVER_AVAILABLE = True
except ImportError:
    try:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver as SqliteSaver
        SQLITE_SAVER_AVAILABLE = True
    except ImportError:
        SqliteSaver = Any
        SQLITE_SAVER_AVAILABLE = False

try:
    import chromadb
    CHROMADB_AVAILABLE = True
except ImportError:
    chromadb = None
    CHROMADB_AVAILABLE = False


class ShortTermMemory:
    """Short-term conversational memory using LangGraph SQLite checkpointer."""

    def __init__(self, db_path: str = ".maya/memory.db") -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        if SQLITE_SAVER_AVAILABLE and callable(SqliteSaver):
            self._checkpointer = SqliteSaver(self._conn)
            if hasattr(self._checkpointer, "setup"):
                try:
                    self._checkpointer.setup()
                except Exception as e:
                    logger.debug("Checkpointer setup note: %s", e)
        else:
            self._checkpointer = None

    def get_checkpointer(self) -> Any:
        """Return the LangGraph SqliteSaver instance."""
        return self._checkpointer

    def clear_session(self, session_id: str) -> None:
        """Delete all checkpoints for a session (thread_id)."""
        cursor = self._conn.cursor()
        for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
            try:
                cursor.execute(f"DELETE FROM {table} WHERE thread_id = ?", (session_id,))
            except sqlite3.OperationalError:
                pass
        self._conn.commit()


class LongTermMemory:
    """Long-term semantic memory powered by ChromaDB vector store."""

    def __init__(self, persist_path: str = ".maya/chroma") -> None:
        self.persist_path = persist_path
        Path(persist_path).mkdir(parents=True, exist_ok=True)
        self._client: Any = None
        self._collection: Any = None

        if CHROMADB_AVAILABLE:
            try:
                self._client = chromadb.PersistentClient(path=self.persist_path)
                self._collection = self._client.get_or_create_collection(name="maya_memory")
            except Exception as e:
                logger.warning("Could not initialize ChromaDB collection: %s", e)

    async def store(
        self,
        session_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Embed and store a memory record in ChromaDB."""
        if not self._collection or not content.strip():
            return

        meta = dict(metadata or {})
        meta["session_id"] = session_id
        doc_id = f"mem_{uuid.uuid4().hex[:12]}"

        try:
            await asyncio.to_thread(
                self._collection.add,
                documents=[content],
                metadatas=[meta],
                ids=[doc_id],
            )
        except Exception as e:
            logger.warning("Error storing memory in ChromaDB: %s", e)

    async def search(self, query: str, n_results: int = 5) -> list[dict[str, Any]]:
        """Perform semantic search over stored long-term memories."""
        if not self._collection or not query.strip():
            return []

        try:
            results = await asyncio.to_thread(
                self._collection.query,
                query_texts=[query],
                n_results=n_results,
            )
            hits: list[dict[str, Any]] = []
            if results and "documents" in results and results["documents"]:
                docs = results["documents"][0]
                metas = (
                    results["metadatas"][0]
                    if "metadatas" in results and results["metadatas"]
                    else [{}] * len(docs)
                )
                ids = (
                    results["ids"][0]
                    if "ids" in results and results["ids"]
                    else [""] * len(docs)
                )
                distances = (
                    results["distances"][0]
                    if "distances" in results and results["distances"]
                    else [0.0] * len(docs)
                )
                for doc, m, i, d in zip(docs, metas, ids, distances):
                    hits.append({
                        "id": i,
                        "document": doc,
                        "metadata": m,
                        "distance": d,
                    })
            return hits
        except Exception as e:
            logger.warning("Error querying ChromaDB: %s", e)
            return []

    async def remember_fact(self, key: str, value: str) -> None:
        """Store a durable user fact (e.g. name, preferences, habits)."""
        content = f"{key}: {value}"
        await self.store(
            session_id="facts",
            content=content,
            metadata={"type": "fact", "key": key, "value": value},
        )

    async def get_relevant_context(self, query: str) -> str:
        """Return a formatted string of memories relevant to the query."""
        results = await self.search(query=query, n_results=5)
        if not results:
            return ""

        docs = [hit["document"] for hit in results if hit.get("document")]
        if not docs:
            return ""

        return "Relevant Context from Memory:\n" + "\n".join(f"- {d}" for d in docs)


class MemoryManager:
    """Combines short-term SQLite checkpoints with long-term ChromaDB recall."""

    def __init__(self, short_term: ShortTermMemory, long_term: LongTermMemory) -> None:
        self.short_term = short_term
        self.long_term = long_term

    def get_checkpointer(self) -> Any:
        """Delegate checkpointer access to short-term memory."""
        return self.short_term.get_checkpointer()

    async def enrich_with_memories(self, query: str) -> str:
        """Retrieve relevant context from long-term memory for the query."""
        return await self.long_term.get_relevant_context(query)


_memory_manager_instance: MemoryManager | None = None


def get_memory_manager() -> MemoryManager:
    """Return the singleton MemoryManager instance configured with app settings."""
    global _memory_manager_instance
    if _memory_manager_instance is None:
        config = get_config()
        short_term = ShortTermMemory(db_path=config.memory_db_path)
        long_term = LongTermMemory(persist_path=config.chroma_persist_path)
        _memory_manager_instance = MemoryManager(short_term=short_term, long_term=long_term)
    return _memory_manager_instance
