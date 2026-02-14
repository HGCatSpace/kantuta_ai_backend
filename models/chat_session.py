from typing import Optional, List, TYPE_CHECKING
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlmodel import SQLModel, Field, Relationship

if TYPE_CHECKING:
    from models.user import Usuario
    from models.casos import Caso
    from models.system_prompt import SystemPrompt

# --- HELPER PARA HORA BOLIVIA ---
def bolivia_now():
    return datetime.now(ZoneInfo("America/La_Paz")).replace(tzinfo=None)

# --- 1. CLASE BASE (Schema común) ---
class ChatSessionBase(SQLModel):
    titulo: str = Field(default="Nuevo Chat", max_length=150)
    
    caso_id: Optional[int] = Field(default=None, foreign_key="casos.id_caso", index=True)
    system_prompt_id: Optional[int] = Field(default=None, foreign_key="system_prompts.id_prompt", index=True)
    
    es_activo: bool = Field(default=True)
    fecha_creacion: datetime = Field(default_factory=bolivia_now)
    ultimo_acceso: datetime = Field(default_factory=bolivia_now)

# --- 2. CLASE TABLE (Base de Datos) ---
class ChatSession(ChatSessionBase, table=True):
    __tablename__ = "chat_sessions"

    # Usamos string para compatibilidad total con thread_id de LangGraph
    id_session: str = Field(primary_key=True, index=True) 
    
    # RELACIONES
    system_prompt: Optional["SystemPrompt"] = Relationship(back_populates="sesiones_de_chat")
    caso: Optional["Caso"] = Relationship(back_populates="chats")

# --- 3. SCHEMAS (Pydantic) ---
class ChatSessionCreate(SQLModel):
    titulo: str
    caso_id: int
    system_prompt_id: int

class ChatSessionUpdate(SQLModel):
    titulo: Optional[str] = None
    ultimo_acceso: Optional[datetime] = None
    es_activo: bool