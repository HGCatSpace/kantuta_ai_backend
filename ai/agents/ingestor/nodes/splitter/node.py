from typing import List
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from ai.agents.ingestor.states import IngestionState

def text_splitter_node(state: IngestionState) -> dict:
    """
    NODO 2: Toma los documentos crudos del estado y los fragmenta
    respetando la estructura jerárquica legal/académica.
    """
    raw_docs = state.get("raw_documents", [])
    
    if not raw_docs:
        print("[SPLITTER] No hay documentos para fragmentar.")
        return {"status": "error", "error_message": "No hay documentos cargados."}

    print(f"[SPLITTER] Iniciando fragmentación de {len(raw_docs)} documentos/páginas...")

    separators = [
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
        ""
    ]
    
    text_splitter = RecursiveCharacterTextSplitter(
        separators=separators,
        chunk_size=1200,  
        chunk_overlap=200,
        length_function=len,
        is_separator_regex=False,
        strip_whitespace=True
    )
    
    new_chunks = text_splitter.split_documents(raw_docs)
    
    for i, chunk in enumerate(new_chunks):
        chunk.metadata["chunk_index"] = i

    print(f"[SPLITTER] Generados {len(new_chunks)} fragmentos.")

    return {
        "chunks": new_chunks,
        "raw_documents": [], # Limpieza de estado anterior
        "status": "splitted",
        "status_message": "Proceso de split terminado"
    }