import os
from typing import Dict
from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader, TextLoader
from ai.agents.ingestor.states import IngestionState

def document_loader_node(state: IngestionState) -> Dict:
    """
    NODO 1: Cargador de documentos (Lista de Archivos).
    Recibe una LISTA de rutas exactas en 'file_path' y carga cada una.
    """
    file_paths = state.get("file_path", [])
    
    print(f"[NODO: LOADER] Recibida lista de {len(file_paths)} archivos.")
    
    if not file_paths or not isinstance(file_paths, list):
        return {
            "status": "error",
            "status_message": "No se proporcionó una lista válida de archivos."
        }

    all_docs = []
    loaded_filenames = []
    
    LOADER_MAPPING = {
        ".pdf": PyPDFLoader,
        ".docx": Docx2txtLoader,
        ".txt": TextLoader
    }

    for file_path in file_paths:
        
        if not os.path.exists(file_path):
            print(f"   Archivo no encontrado (saltando): {file_path}")
            continue

        filename = os.path.basename(file_path)
        ext = os.path.splitext(filename)[1].lower()

        if ext not in LOADER_MAPPING:
            print(f"   Formato no soportado ({ext}): {filename}")
            continue

        try:
            # 3. Carga
            loader_class = LOADER_MAPPING[ext]
            
            if ext == ".txt":
                loader = loader_class(file_path, encoding="utf-8")
            else:
                loader = loader_class(file_path)
                
            docs = loader.load()
            
            # 4. Inyección de Metadatos
            for doc in docs:
                doc.metadata["source_filename"] = filename
                doc.metadata["file_type"] = ext
                doc.metadata["source_path"] = file_path # Ruta original para referencia
            
            all_docs.extend(docs)
            loaded_filenames.append(filename)
            print(f"   ✅ {filename} cargado ({len(docs)} fragmentos/páginas)")
            
        except Exception as e:
            print(f"   ❌ Error crítico cargando {filename}: {str(e)}")

    # 5. Evaluación Final
    if not all_docs:
        return {

            "raw_documents": [],
            "status": "error",
            "status_message": "No se pudo cargar ningún archivo de la lista."
        }

    # Éxito: Retornamos solo las llaves que actualizamos (LangGraph hace el merge)
    return {
        "file_names": loaded_filenames,
        "raw_documents": all_docs,
        "status": "loaded",
        "status_message": f"Carga exitosa de {len(loaded_filenames)} archivos."
    }