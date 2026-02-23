import os
from langchain_ollama import OllamaEmbeddings 
from langchain_ollama import ChatOllama


def get_embedding_model():
    """
    NODO 3: Embedding Model Factory
    Retorna una instancia configurada del modelo de embeddings.
    Centraliza la configuración para evitar desajustes entre Ingesta y Consulta.
    """
    
    
    print(f"[EMBEDDING] Conectando a Ollama en: {"http://localhost:11435"}")
    print(f"[EMBEDDING] Modelo seleccionado: qwen3-embedding:8b")

    embeddings = OllamaEmbeddings(
        model="qwen3-embedding:8b",
        base_url="http://localhost:11435",
    )
    
    return embeddings

def get_chat_model(temperature: float = 0.0, top_p: float = 0.95, top_k: int = 20):
    """
    Factory que configura el modelo con parámetros dinámicos.
    """
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11435")
    model_name = os.getenv("LLM_MODEL_NAME", "qwen3:8b") 

    llm = ChatOllama(
        model=model_name,
        base_url=ollama_url,
        temperature=temperature,
        top_p=top_p,
        top_k=top_k,
        # Otros parámetros útiles para RAG:
        keep_alive="5m",
        num_ctx=4096, # Ventana de contexto amplia para leer leyes largas
    )
    
    return llm