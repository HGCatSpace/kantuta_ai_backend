import asyncio
from typing import Dict, List, Tuple
import chromadb
from langchain_chroma import Chroma
from ai.agents.conversational_assistant.states import RetrievalState

# Importar constantes y modelos (ajusta según tu estructura de archivos)
# from .config import CHROMA_HOST, CHROMA_PORT, embedding_model 
# O defínelos aquí si estás probando:
import os
from langchain_ollama import OllamaEmbeddings

OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11435")
CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", 8000))

embedding_model = OllamaEmbeddings(base_url=OLLAMA_URL, model="qwen3-embedding:8b")


# --- HELPER SÍNCRONO (Para evitar el bloqueo) ---
def _get_retriever_sync():
    """
    Crea la conexión a ChromaDB de forma síncrona.
    Esta función se ejecutará en un hilo separado.
    """
    print(f"📡 [RETRIEVAL] Conectando a ChromaDB (Hilo Síncrono)...")
    
    http_client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    
    vector_store = Chroma(
        client=http_client,
        collection_name="kantuta_legal",
        embedding_function=embedding_model
    )
    return vector_store


# --- NODO ASÍNCRONO ---
async def retrieve_node(state: RetrievalState):
    """
    Busca documentos relevantes usando asyncio para no bloquear el servidor.
    """
    last_message = state["messages"][-1]
    print(last_message, end='\n\n')
    raw_content = last_message.content

    # --- CORRECCIÓN DE LANGSMITH / MULTIMODAL ---
    # Verificamos si el contenido es una lista (formato complejo) o un string
    if isinstance(raw_content, str):
        query = raw_content
    elif isinstance(raw_content, list):
        # Es una lista de bloques (ej: LangSmith, GPT-4 Vision)
        # Extraemos solo el texto y lo unimos
        print("   ⚠️ Detectado formato complejo (LangSmith/Multimodal). Extrayendo texto...")
        text_parts = [block.get("text", "") for block in raw_content if block.get("type") == "text"]
        query = " ".join(text_parts)
    else:
        # Fallback por seguridad
        query = str(raw_content)
    # ---------------------------------------------

    print(f"   Query procesada: '{query}'")
    
    print(f"🔍 [RETRIEVAL] Buscando: '{query}'")

    try:
        # 1. Inicialización NO BLOQUEANTE
        # Movemos la creación del cliente a un hilo aparte
        vector_store = await asyncio.to_thread(_get_retriever_sync)
        
        # 2. Búsqueda Asíncrona
        # Usamos asimilarity_search_with_score que es nativo async de LangChain
        results = await vector_store.asimilarity_search_with_score(query, k=5)
        
        print(f"📄 [RETRIEVAL] Encontrados {len(results)} documentos.")
        
        # Retornamos la lista de tuplas (Document, float_score)
        return {"context": results}

    except Exception as e:
        print(f"❌ Error en retrieval: {e}")
        # En caso de error, devolvemos contexto vacío para que el LLM no falle
        return {"context": []}