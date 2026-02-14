from sqlmodel import SQLModel, Field
from typing import List, Optional
# --- 1. TABLA INTERMEDIA (N:N) ---
# Esta tabla une a los Usuarios con las Acciones
class UsuarioActionLink(SQLModel, table=True):
    __tablename__ = "usuario_action_link"
    
    id: int = Field(primary_key=True)
    usuario_id: Optional[int] = Field(foreign_key="usuarios.id")
    action_id: Optional[int] = Field(foreign_key="actions.id_action")


class PromptDocumentoLink(SQLModel, table=True):
    """
    Tabla intermedia para conectar Prompts con Documentos de Conocimiento.
    Permite que un Asistente (Prompt) tenga acceso exclusivo a ciertos docs.
    """
    __tablename__ = "prompt_documento_link"

    # Claves foráneas compuestas (Primary Key Compuesta)
    id: int = Field(primary_key=True)
    system_prompt_id: int = Field(
        foreign_key="system_prompts.id_prompt", 
        primary_key=True
    )
    
    documento_id: int = Field(
        foreign_key="documentos_conocimiento.id_documento", 
        primary_key=True
    )