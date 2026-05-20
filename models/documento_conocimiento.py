from enum import Enum
from typing import Optional, TYPE_CHECKING, List
from sqlmodel import SQLModel, Field, Relationship
from datetime import datetime
from zoneinfo import ZoneInfo

from models.links import PromptDocumentoLink

if TYPE_CHECKING:
    from models.user import Usuario
    from models.system_prompt import SystemPrompt

# --- HELPER ---
def bolivia_now():
    return datetime.now(ZoneInfo("America/La_Paz")).replace(tzinfo=None)


# --- ENUMS (Para restringir valores en BD y Frontend) ---
class EnumCategoriaBiblioteca(str, Enum):
    NORMATIVA_SUSTANTIVA = "Normativa sustantiva"
    NORMATIVA_ADJETIVA = "Normativa adjetiva (procesal)"
    NORMATIVA_GENERAL = "Normativa general / principios"
    MATERIAL_REFERENCIA = "Material de referencia"

class EnumIconoArchivo(str, Enum):
    PDF = "pdf"       # Color Rojo en front
    DOC = "doc"       # Color Azul
    OTHER = "other"   # Color Gris

class EnumEstadoIndexacion(str, Enum):
    PENDIENTE = "PENDIENTE"
    PROCESANDO = "PROCESANDO"
    COMPLETADO = "COMPLETADO"
    ERROR = "ERROR"

# ==========================================
# 1. MODELO BASE (Campos compartidos)
# ==========================================
class DocumentoConocimientoBase(SQLModel):
    titulo: str = Field(max_length=255, index=True)
    categoria: EnumCategoriaBiblioteca = Field(default=EnumCategoriaBiblioteca.MATERIAL_REFERENCIA)
    icono: EnumIconoArchivo = Field(default=EnumIconoArchivo.OTHER)
    descripcion: Optional[str] = Field(default=None, max_length=500)

# ==========================================
# 2. MODELO DE TABLA (Base de Datos)
# ==========================================
class DocumentoConocimiento(DocumentoConocimientoBase, table=True):
    __tablename__ = "documentos_conocimiento"

    id_documento: Optional[int] = Field(default=None, primary_key=True)

    # Ubicación física en el servidor
    ruta: str
    # Nombre original del archivo (sin prefijo de timestamp)
    nombre_archivo: Optional[str] = Field(default=None)

    # --- RELACIÓN CON USUARIO (1:N) ---
    usuario_id: int = Field(foreign_key="usuarios.id")
    usuario: "Usuario" = Relationship(back_populates="documentos_conocimiento")

    # Relación con Prompts
    prompts: List["SystemPrompt"] = Relationship(
        back_populates="documentos_conocimiento",
        link_model=PromptDocumentoLink
    )

    # --- FECHAS DE AUDITORÍA (Bolivia) ---
    fecha_creacion: datetime = Field(default_factory=bolivia_now)
    ultima_modificacion: datetime = Field(default_factory=bolivia_now)
    estado_indexacion: EnumEstadoIndexacion = Field(default=EnumEstadoIndexacion.PENDIENTE)

    # --- Progreso de indexación (chunks embebidos / chunks totales) ---
    chunks_procesados: Optional[int] = Field(default=None)
    chunks_totales: Optional[int] = Field(default=None)

# ==========================================
# 3. MODELO CREATE (Input para POST)
# ==========================================
class DocumentoConocimientoCreate(DocumentoConocimientoBase):
    """
    Lo que envía el Frontend al crear (metadatos).
    'ruta' y 'usuario_id' se inyectan en el backend.
    """
    pass

# ==========================================
# 4. MODELO UPDATE (Input para PATCH)
# ==========================================
class DocumentoConocimientoUpdate(SQLModel):
    titulo: Optional[str] = None
    categoria: Optional[EnumCategoriaBiblioteca] = None
    icono: Optional[EnumIconoArchivo] = None
    descripcion: Optional[str] = None

# ==========================================
# 5. MODELO PUBLIC (Output para GET)
# ==========================================
class DocumentoConocimientoPublic(DocumentoConocimientoBase):
    id_documento: int
    estado_indexacion: EnumEstadoIndexacion
    fecha_creacion: datetime
    ultima_modificacion: datetime
    nombre_archivo: Optional[str] = None
    chunks_procesados: Optional[int] = None
    chunks_totales: Optional[int] = None
