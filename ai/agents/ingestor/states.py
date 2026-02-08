from typing import TypedDict, List, Annotated
from langchain_core.documents import Document
import operator

class IngestionState(TypedDict):
    """
    Representa el estado del flujo de ingesta de documentos.
    """
    file_path: List[str]  
    file_names: List[str]   
    raw_documents: List[Document]
    chunks: Annotated[List[Document], operator.add]
    metadata: dict
    status: str
    status_message: str
    ids_vector_lists: List[str]