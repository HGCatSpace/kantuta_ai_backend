import asyncio
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import os
import chromadb
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings

router = APIRouter(
    prefix="/knowledge",
    tags=["Base de Conocimiento - Búsqueda"]
)

# --- Config (same as the retriever node) ---
OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11435")
CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", 8000))

embedding_model = OllamaEmbeddings(base_url=OLLAMA_URL, model="qwen3-embedding:8b")


# --- Schemas ---
class SearchRequest(BaseModel):
    query: str
    k: int = 5
    source_filename: Optional[str] = None


class ChunkResult(BaseModel):
    content: str
    score: float
    metadata: dict


class SearchResponse(BaseModel):
    query: str
    results: List[ChunkResult]


# --- Helpers ---
def _get_chroma_client():
    return chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)


def _get_vector_store(client=None):
    if client is None:
        client = _get_chroma_client()
    return Chroma(
        client=client,
        collection_name="kantuta_legal",
        embedding_function=embedding_model,
    )


# --- Endpoints ---

@router.get("/sources")
async def list_sources():
    """
    Lista los nombres de archivo (source_filename) distintos presentes
    en la colección de ChromaDB, útiles para filtrar búsquedas.
    """
    try:
        client = await asyncio.to_thread(_get_chroma_client)
        collection = await asyncio.to_thread(
            client.get_collection, "kantuta_legal"
        )
        # get() with no args returns all entries; we only need metadata
        all_data = await asyncio.to_thread(
            collection.get, include=["metadatas"]
        )
        filenames: set[str] = set()
        for meta in (all_data.get("metadatas") or []):
            fname = (meta or {}).get("source_filename")
            if fname:
                filenames.add(fname)

        return {"sources": sorted(filenames)}
    except Exception as e:
        print(f"❌ Error listando fuentes: {e}")
        raise HTTPException(status_code=500, detail=f"Error listando fuentes: {str(e)}")


@router.post("/search", response_model=SearchResponse)
async def search_knowledge_base(body: SearchRequest):
    """
    Busca en la base de conocimiento vectorial (ChromaDB) y retorna
    los fragmentos más relevantes con puntaje y metadata.
    Si se pasa source_filename, filtra sólo chunks de ese documento.
    """
    if not body.query.strip():
        raise HTTPException(status_code=400, detail="La consulta no puede estar vacía")

    k = min(max(body.k, 1), 20)  # clamp between 1-20

    # Build optional ChromaDB where filter
    where_filter = None
    if body.source_filename:
        where_filter = {"source_filename": body.source_filename}

    try:
        vector_store = await asyncio.to_thread(_get_vector_store)
        kwargs: dict = {"query": body.query, "k": k}
        if where_filter:
            kwargs["filter"] = where_filter
        results = await vector_store.asimilarity_search_with_score(**kwargs)
    except Exception as e:
        print(f"❌ Error en búsqueda vectorial: {e}")
        raise HTTPException(status_code=500, detail=f"Error en la búsqueda: {str(e)}")

    chunks: List[ChunkResult] = []
    for doc, score in results:
        chunks.append(ChunkResult(
            content=doc.page_content,
            score=round(float(score), 4),
            metadata=doc.metadata or {},
        ))

    return SearchResponse(query=body.query, results=chunks)
