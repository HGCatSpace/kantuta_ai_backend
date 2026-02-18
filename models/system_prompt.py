from typing import Optional, List, TYPE_CHECKING
from sqlmodel import SQLModel, Field, Relationship
from datetime import datetime
from zoneinfo import ZoneInfo

from models.links import PromptDocumentoLink

if TYPE_CHECKING:
    from models.user import Usuario
    from models.documento_conocimiento import DocumentoConocimiento
    from models.chat_session import ChatSession

# --- HELPER ---
def bolivia_now():
    return datetime.now(ZoneInfo("America/La_Paz")).replace(tzinfo=None)

# ==========================================
# 1. CLASE BASE (Campos Comunes)
# ==========================================
class SystemPromptBase(SQLModel):
    nombre: str = Field(max_length=100)
    es_activo: bool = Field(default=True)
    descripcion: Optional[str] = Field(default=None, max_length=500)
    contenido_rol: Optional[str] = Field(default=None)
    contenido_tarea: Optional[str] = Field(default=None)
    contenido_alcances: Optional[str] = Field(default=None)
    contenido_contexto: Optional[str] = Field(default=None)
    temperatura: float = Field(default=0.7)
    top_p: float = Field(default=0.95)
    top_k: int = Field(default=20)

# ==========================================
# 2. CLASE TABLE (Base de Datos)
# ==========================================
class SystemPrompt(SystemPromptBase, table=True):
    __tablename__ = "system_prompts"

    id_prompt: Optional[int] = Field(default=None, primary_key=True)

    # Relación con el Experto (Usuario)
    id_experto_creador: int = Field(foreign_key="usuarios.id")

    experto_creador: "Usuario" = Relationship(back_populates="prompts_creados")
    sesiones_de_chat: List["ChatSession"] = Relationship(back_populates="system_prompt")

    # Relación con Documentos de Conocimiento
    documentos_conocimiento: List["DocumentoConocimiento"] = Relationship(
        back_populates="prompts",
        link_model=PromptDocumentoLink
    )

    # Fechas de Auditoría
    fecha_creacion: datetime = Field(default_factory=bolivia_now)
    fecha_actualizacion: datetime = Field(default_factory=bolivia_now)

# ==========================================
# 3. MODELO PUBLIC (Output para respuestas)
# ==========================================
class SystemPromptPublic(SystemPromptBase):
    id_prompt: int
    id_experto_creador: int
    nombre_creador: Optional[str] = None
    fecha_creacion: datetime
    fecha_actualizacion: datetime
    documentos_conocimiento: List[int] = []

# ==========================================
# 4. MODELO CREATE (Input para POST)
# ==========================================
class SystemPromptCreate(SystemPromptBase):
    """
    Datos necesarios para crear un prompt.
    El 'id_experto_creador' no se pide aquí, se inyecta desde el Token del usuario logueado.
    """
    documentos_conocimiento: List[int] = []

# ==========================================
# 5. MODELO UPDATE (Input para PATCH)
# ==========================================
class SystemPromptUpdate(SQLModel):
    nombre: Optional[str] = None
    es_activo: Optional[bool] = None
    descripcion: Optional[str] = None
    contenido_rol: Optional[str] = None
    contenido_tarea: Optional[str] = None
    contenido_alcances: Optional[str] = None
    contenido_contexto: Optional[str] = None
    temperatura: Optional[float] = None
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    documentos_conocimiento: Optional[List[int]] = None
