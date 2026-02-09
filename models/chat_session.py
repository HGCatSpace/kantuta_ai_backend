from typing import Optional, List, TYPE_CHECKING
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlmodel import SQLModel, Field, Relationship

if TYPE_CHECKING:
    from models.user import Usuario
    from models.casos import Caso

# --- HELPER PARA HORA BOLIVIA ---
def bolivia_now():
    return datetime.now(ZoneInfo("America/La_Paz")).replace(tzinfo=None)

# --- 1. CLASE BASE (Schema común) ---
class ChatSessionBase(SQLModel):
    titulo: str = Field(default="Nuevo Chat", max_length=150)
    usuario_id: int = Field(foreign_key="usuarios.id", index=True)
    
    # Opcional: Un chat puede pertenecer a un caso o ser libre
    caso_id: Optional[int] = Field(default=None, foreign_key="casos.id_caso")
    
    fecha_creacion: datetime = Field(default_factory=bolivia_now)
    ultimo_acceso: datetime = Field(default_factory=bolivia_now)

# --- 2. CLASE TABLE (Base de Datos) ---
class ChatSession(ChatSessionBase, table=True):
    __tablename__ = "chat_sessions"

    # Usamos string para compatibilidad total con thread_id de LangGraph
    id_session: str = Field(primary_key=True, index=True) 
    
    # RELACIONES
    caso: Optional["Caso"] = Relationship(back_populates="chats")

# --- 3. SCHEMAS (Pydantic) ---
class ChatSessionCreate(SQLModel):
    id_session: str # El frontend o backend debe generar este UUID
    titulo: str
    usuario_id: int
    caso_id: Optional[int] = None

class ChatSessionUpdate(SQLModel):
    titulo: Optional[str] = None
    ultimo_acceso: Optional[datetime] = None