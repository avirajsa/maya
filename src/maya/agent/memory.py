"""Persistent short-term and semantic long-term memory for Maya."""
import asyncio
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any

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
    """SQLite checkpoints preserve message history across process restarts."""
    def __init__(self, db_path: str = ".maya/memory.db") -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.commit()
        self._checkpointer = None
        if SQLITE_SAVER_AVAILABLE and callable(SqliteSaver):
            try:
                self._checkpointer = SqliteSaver(self._conn)
                if hasattr(self._checkpointer, "setup"):
                    self._checkpointer.setup()
            except Exception:
                logger.exception("Could not initialize SQLite checkpointer")
    def get_checkpointer(self) -> Any:
        return self._checkpointer
    def clear_session(self, session_id: str) -> None:
        cursor = self._conn.cursor()
        for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
            try:
                cursor.execute(f"DELETE FROM {table} WHERE thread_id = ?", (session_id,))
            except sqlite3.OperationalError:
                pass
        self._conn.commit()

class LongTermMemory:
    """ChromaDB archive for durable facts and searchable past conversation turns."""
    def __init__(self, persist_path: str = ".maya/chroma") -> None:
        self.persist_path = persist_path
        Path(persist_path).mkdir(parents=True, exist_ok=True)
        self._client = self._collection = None
        if CHROMADB_AVAILABLE:
            try:
                self._client = chromadb.PersistentClient(path=persist_path)
                self._collection = self._client.get_or_create_collection(name="maya_memory")
            except Exception:
                logger.exception("Could not initialize ChromaDB")
        else:
            logger.warning("ChromaDB unavailable; semantic memory is disabled")
    
    async def store(
        self,
        session_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        *,
        record_id: str | None = None,
        user_id: str = "local",
    ) -> None:
        if self._collection is None or not content.strip():
            return

        meta = dict(metadata or {})
        meta["session_id"] = session_id
        meta["user_id"] = user_id
        meta["created_at"] = datetime.now(timezone.utc).isoformat()

        digest = hashlib.sha256(
            (user_id + session_id + content + meta["created_at"]).encode()
        ).hexdigest()[:24]

        try:
            await asyncio.to_thread(
                self._collection.upsert,
                documents=[content],
                metadatas=[meta],
                ids=[record_id or f"mem_{digest}"],
            )
        except Exception:
            logger.exception("Could not store long-term memory")

    async def search(
            self,
            query: str,
            n_results: int = 8,
            *,
            user_id: str = "local",
            ) -> list[dict[str, Any]]:
        if self._collection is None or not query.strip():
            return []
        try:
            result = await asyncio.to_thread(
                    self._collection.query,
                    query_texts=[query],
                    n_results=n_results,
                    where={"user_id": user_id},
                    )
            docs = (result.get("documents") or [[]])[0] or []
            metas = (result.get("metadatas") or [[]])[0] or [{}] * len(docs)
            ids = (result.get("ids") or [[]])[0] or [""] * len(docs)
            distances = (result.get("distances") or [[]])[0] or [0.0] * len(docs)
            return [{"id": i, "document": d, "metadata": m or {}, "distance": dist} for d, m, i, dist in zip(docs, metas, ids, distances) if d]
        except Exception:
            logger.exception("Could not search long-term memory")
            return []
    async def remember_fact(
            self,
            key: str,
            value: str,
            *,
            user_id: str = "local",
            ) -> None:
        """Update a fact in place so changed preferences do not accumulate duplicates."""
        key_hash = hashlib.sha256(
                f"{user_id}:{key.strip().lower()}".encode()
                ).hexdigest()[:24]
        await self.store(
                "facts",
                f"{key}:{value}",
                {"type": "fact", "key": key, "value": value},
                record_id=f"fact_{key_hash}",
                user_id=user_id,
                )
                
    async def get_relevant_context(
            self,
            query: str,
            *,
            user_id: str = "local",
            ) -> str:
        hits = await self.search(query, 8, user_id=user_id)
        docs, seen = [], set()
        for hit in hits:
            doc = str(hit.get("document", "")).strip()
            if doc and doc.casefold() not in seen:
                seen.add(doc.casefold())
                docs.append(doc)
        return "Relevant memories (use only when applicable; newer user statements override older ones):\n" + "\n".join(f"- {d}" for d in docs[:8]) if docs else ""

class MemoryManager:
    def __init__(self, short_term: ShortTermMemory, long_term: LongTermMemory) -> None:
        self.short_term, self.long_term = short_term, long_term
    def get_checkpointer(self) -> Any:
        return self.short_term.get_checkpointer()
    async def enrich_with_memories(
            self,
            query: str,
            *,
            user_id: str = "local",
            ) -> str:
        return await self.long_term.get_relevant_context(query, user_id=user_id)
    async def remember_turn(
            self,
            session_id: str,
            user_input: str,
            response: str,
            *,
            user_id: str = "local",
            ) -> None:
        user_input, response = user_input.strip()[:3000], response.strip()[:3000]
        if user_input and response:
            await self.long_term.store(session_id, f"User said: {user_input}\nMaya replied: {response}", {"type": "conversation"})
            await self.long_term.store(
                    session_id,
                    f"User said: {user_input}\nMaya replied: {response}",
                    {"type": "conversation"},
                    user_id=user_id,
                    )

_memory_manager_instance: MemoryManager | None = None
def get_memory_manager() -> MemoryManager:
    global _memory_manager_instance
    if _memory_manager_instance is None:
        config = get_config()
        _memory_manager_instance = MemoryManager(ShortTermMemory(config.memory_db_path), LongTermMemory(config.chroma_persist_path))
    return _memory_manager_instance
