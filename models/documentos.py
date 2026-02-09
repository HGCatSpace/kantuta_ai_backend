from typing import Optional, TYPE_CHECKING
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlmodel import SQLModel, Field, Relationship

if TYPE_CHECKING:
    from models.casos import Caso

# --- HELPER ---
def bolivia_now():
    return datetime.now(ZoneInfo("America/La_Paz")).replace(tzinfo=None)

# --- 1. CLASE BASE ---
class DocumentoBase(SQLModel):
    nombre_archivo: str = Field(max_length=255)
    ruta: str 
    hash_verificacion: Optional[str] = Field(default=None, max_length=64) 
    
    tipo_mime: Optional[str] = Field(default="application/pdf")
    
    caso_id: int = Field(foreign_key="casos.id_caso")
    
    fecha_subida: datetime = Field(default_factory=bolivia_now)

# --- 2. CLASE TABLE ---
class Documento(DocumentoBase, table=True):
    __tablename__ = "documentos" # Antes documentos_boveda
    
    id_documento: Optional[int] = Field(default=None, primary_key=True)
    
    # RELACIONES
    caso: "Caso" = Relationship(back_populates="documentos")

# --- 3. SCHEMAS ---
class DocumentoCreate(DocumentoBase):
    pass

class DocumentoUpdate(SQLModel):
    nombre_archivo: Optional[str] = None