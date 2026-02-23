import os
import asyncio # <--- Importante
import chromadb
from typing import Dict
from langchain_chroma import Chroma
from langchain_core.runnables import RunnableConfig
from ai.agents.ingestor.states import IngestionState
from ai.agents.ingestor.llms import get_embedding_model 

# --- FUNCIÓN HELPER SÍNCRONA ---
# para poder enviarlo a un hilo separado después.
def _initialize_chroma_sync(host: str, port: int, collection_name: str, embedding_model, should_reset: bool):
    print(f"📡 [VECTOR STORE] Inicializando cliente Chroma (Hilo Síncrono)...")
    
    # 1. Conexión Síncrona
    http_client = chromadb.HttpClient(host=host, port=port)
    
    # 2. Wrapper de LangChain
    vector_db = Chroma(
        client=http_client,
        collection_name=collection_name,
        embedding_function=embedding_model,
    )
    
    # 3. Borrado Síncrono (si aplica)
    if should_reset:
        try:
            print(f"🧹 [VECTOR STORE] Eliminando colección '{collection_name}'...")
            vector_db.delete_collection()
            # Reinicializamos para asegurar que la colección se recree vacía
            vector_db = Chroma(
                client=http_client,
                collection_name=collection_name,
                embedding_function=embedding_model,
            )
        except Exception:
            print(f"⚠️ La colección no existía, continuando...")
            
    return vector_db

# --- NODO ASÍNCRONO PRINCIPAL ---
async def vector_store_node(state: IngestionState, config: RunnableConfig) -> Dict:
    """
    NODO 4 (SERVER MODE): Ingesta hacia ChromaDB optimizada para asyncio.
    """
    chunks = state.get("chunks", [])
    
    if not chunks:
        return {"status": "error", "status_message": "Lista de chunks vacía."}

    # Configuración
    host = os.getenv("CHROMA_HOST", "localhost")
    port = int(os.getenv("CHROMA_PORT", 8000))
    collection_name = "kantuta_legal"
    
    # Obtenemos el modelo (asumiendo que get_embedding_model es seguro o ligero)
    embedding_model = get_embedding_model()
    
    # Flag de reset desde metadata
    should_reset = state.get("reset_db", False)

    try:
        # --- LA SOLUCIÓN MÁGICA ---
        # Usamos asyncio.to_thread para ejecutar la inicialización bloqueante
        # en un hilo aparte y esperamos el resultado sin congelar el server.
        vector_db = await asyncio.to_thread(
            _initialize_chroma_sync, 
            host, 
            port, 
            collection_name, 
            embedding_model, 
            should_reset
        )

        print(f"💾 [VECTOR STORE] Indexando {len(chunks)} fragmentos...")

        # Enriquecimiento (Ligero, puede quedarse aquí)

        # --- INGESTA ASÍNCRONA ---
        # aadd_documents YA es asíncrono nativo, así que usamos await directo
        ids_list = await vector_db.aadd_documents(documents=chunks)
        
        print(f"✅ [VECTOR STORE] Ingesta completada. {len(ids_list)} vectores guardados.")
        
        return {
            "chunks": [], 
            "status": "success",
            "status_message": ""
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "status": "error", 
            "status_message": f"Error en ChromaDB: {str(e)}"
        }