import os
from dotenv import load_dotenv
from langchain_ollama import OllamaEmbeddings 

load_dotenv()

def get_embedding_model():
    """
    NODO 3: Embedding Model Factory
    Retorna una instancia configurada del modelo de embeddings.
    Centraliza la configuración para evitar desajustes entre Ingesta y Consulta.
    """
    
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11435")
    
    print(f"[EMBEDDING] Conectando a Ollama en: {ollama_url}")
    print(f"[EMBEDDING] Modelo seleccionado: qwen3-embedding:8b")

    embeddings = OllamaEmbeddings(
        model="qwen3-embedding:8b",
        base_url=ollama_url,
    )
    
    return embeddings