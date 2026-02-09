from enum import Enum
from typing import Optional, List, TYPE_CHECKING
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlmodel import SQLModel, Field, Relationship

if TYPE_CHECKING:
    from models.user import Usuario
    from models.chat_session import ChatSession
    from models.documentos import Documento

# --- ENUM ESTADO DEL CASO ---
class EstadoCaso(str, Enum):
    ABIERTO = "ABIERTO"
    ARCHIVADO = "ARCHIVADO"
    CERRADO = "CERRADO"

# --- HELPER PARA HORA BOLIVIA (Naive) ---
def bolivia_now():
    return datetime.now(ZoneInfo("America/La_Paz")).replace(tzinfo=None)
class CasoBase(SQLModel):
    usuario_id: int = Field(foreign_key="usuarios.id") # El abogado/dueño
    
    titulo: str = Field(max_length=200)
    descripcion: Optional[str] = Field(default=None)
    
    estado: EstadoCaso = Field(default=EstadoCaso.ABIERTO)
    
    fecha_creacion: datetime = Field(default_factory=bolivia_now)
    fecha_actualizacion: datetime = Field(default_factory=bolivia_now)

# --- MODELO DEL CASO ---
class Caso(CasoBase, table=True):
    __tablename__ = "casos"
    id_caso: Optional[int] = Field(default=None, primary_key=True)

     # RELACIONES
    usuario: "Usuario" = Relationship(back_populates="casos")
    
    documentos: List["Documento"] = Relationship(back_populates="caso")
    
    chats: List["ChatSession"] = Relationship(back_populates="caso")   

# --- SCHEMAS para CREACIÓN ---
class CasoCreate(SQLModel):
    titulo: str
    descripcion: Optional[str] = None
    usuario_id: int 

class CasoUpdate(SQLModel):
    titulo: Optional[str] = None
    descripcion: Optional[str] = None
    estado: Optional[EstadoCaso] = None