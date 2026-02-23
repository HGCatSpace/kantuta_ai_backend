"""
Servicio de ingesta: carga, fragmenta y almacena documentos en ChromaDB.
Reutiliza la misma lógica que los nodos del agente ingestor pero como
funciones standalone invocables desde los endpoints REST.
"""

import os
import asyncio
from typing import List

import chromadb
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings


# ─── Config ───
OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11435")
CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", 8000))
COLLECTION_NAME = "kantuta_legal"

LOADER_MAPPING = {
    ".pdf": PyPDFLoader,
    ".docx": Docx2txtLoader,
    ".txt": TextLoader,
}

LEGAL_SEPARATORS = [
    "\nLIBRO ",
    "\nTÍTULO ",
    "\nCAPÍTULO ",
    "\nARTÍCULO ",
    "\nArtículo ",
    "\nArt. ",
    "\n\n",
    "\n",
    ". ",
    "\u200b",
    "\uff0c",
    "\u3001",
    "\uff0e",
    "\u3002",
    " ",
    "",
]


def _get_embedding_model():
    return OllamaEmbeddings(base_url=OLLAMA_URL, model="qwen3-embedding:8b")


def _get_chroma_client():
    return chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)


def _get_vector_store(client=None):
    if client is None:
        client = _get_chroma_client()
    return Chroma(
        client=client,
        collection_name=COLLECTION_NAME,
        embedding_function=_get_embedding_model(),
    )


# ─── 1. Load ───
def _load_file_sync(file_path: str, source_filename: str) -> List[Document]:
    """Carga un archivo y enriquece los metadatos (síncrono)."""
    ext = os.path.splitext(source_filename)[1].lower()
    loader_class = LOADER_MAPPING.get(ext)
    if loader_class is None:
        raise ValueError(f"Formato no soportado: {ext}")

    if ext == ".txt":
        loader = loader_class(file_path, encoding="utf-8")
    else:
        loader = loader_class(file_path)

    docs = loader.load()
    for doc in docs:
        doc.metadata["source_filename"] = source_filename
        doc.metadata["file_type"] = ext
        doc.metadata["source_path"] = file_path
    return docs


# ─── 2. Split ───
MIN_CHUNK_LENGTH = 120  # chars mínimos para que un fragmento sea útil

def _split_documents(docs: List[Document]) -> List[Document]:
    """Fragmenta documentos usando los separadores legales."""
    splitter = RecursiveCharacterTextSplitter(
        separators=LEGAL_SEPARATORS,
        chunk_size=800,
        chunk_overlap=50,
        length_function=len,
        is_separator_regex=False,
        strip_whitespace=True,
    )
    chunks = splitter.split_documents(docs)

    # Descarta fragmentos que solo contienen encabezados estructurales (LIBRO, TÍTULO, etc.)
    chunks = [c for c in chunks if len(c.page_content.strip()) >= MIN_CHUNK_LENGTH]

    for i, chunk in enumerate(chunks):
        chunk.metadata["chunk_index"] = i
    return chunks


# ─── 3. Enrich + Store ───


# ─── Public API ───

async def ingest_file(file_path: str, source_filename: str, extra_metadata: dict | None = None) -> int:
    """
    Pipeline completo: carga → fragmenta → enriquece → almacena en ChromaDB.
    Retorna la cantidad de chunks indexados.
    """
    print(f"📥 [INGEST] Procesando: {source_filename}")

    # Load (blocking I/O → thread)
    docs = await asyncio.to_thread(_load_file_sync, file_path, source_filename)
    print(f"   📄 {len(docs)} páginas cargadas")

    # Inject extra metadata if provided (titulo, categoria, etc.)
    if extra_metadata:
        for doc in docs:
            doc.metadata.update(extra_metadata)

    # Split
    chunks = await asyncio.to_thread(_split_documents, docs)
    print(f"   ✂️  {len(chunks)} fragmentos generados")


    # Store
    vector_store = await asyncio.to_thread(_get_vector_store)
    ids = await vector_store.aadd_documents(documents=chunks)
    print(f"   ✅ {len(ids)} vectores almacenados en ChromaDB")

    return len(ids)


async def delete_file_chunks(source_filename: str) -> int:
    """
    Elimina de ChromaDB todos los chunks con source_filename dado.
    Retorna la cantidad de chunks eliminados.
    """
    print(f"🗑️  [INGEST] Eliminando chunks de: {source_filename}")

    client = await asyncio.to_thread(_get_chroma_client)
    collection = await asyncio.to_thread(client.get_collection, COLLECTION_NAME)

    # Find IDs matching the source_filename
    results = await asyncio.to_thread(
        collection.get,
        where={"source_path": source_filename},
    )
    ids_to_delete = results.get("ids", [])

    if ids_to_delete:
        await asyncio.to_thread(collection.delete, ids=ids_to_delete)
        print(f"   ✅ {len(ids_to_delete)} chunks eliminados")
    else:
        print(f"   ℹ️  No se encontraron chunks para '{source_filename}'")

    return len(ids_to_delete)
