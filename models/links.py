from sqlmodel import SQLModel, Field
from typing import List, Optional
# --- 1. TABLA INTERMEDIA (N:N) ---
# Esta tabla une a los Usuarios con las Acciones
class UsuarioActionLink(SQLModel, table=True):
    __tablename__ = "usuario_action_link"
    
    id: int = Field(primary_key=True)
    usuario_id: Optional[int] = Field(foreign_key="usuarios.id")
    action_id: Optional[int] = Field(foreign_key="actions.id_action")