from enum import Enum
from typing import Optional, List, TYPE_CHECKING
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlmodel import SQLModel, Field, Relationship

from models.links import UsuarioActionLink

if TYPE_CHECKING:
    from models.rol import Rol
    from models.action import Action
    from models.casos import Caso
    from models.documento_conocimiento import DocumentoConocimiento
    from models.system_prompt import SystemPrompt

def bolivia_now():
    """Retorna la fecha y hora actual en zona horaria de La Paz"""
    return datetime.now(ZoneInfo("America/La_Paz")).replace(tzinfo=None)

# --- 0. ENUM para el estado ---
class ActiveUserEnum(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"

# --- 2. MODELO USUARIO ---
class UsuarioBase(SQLModel):
    nombre_de_usuario: str = Field(index=True, unique=True)
    email: str = Field(unique=True, index=True)
    nombre_completo: str
    activo: ActiveUserEnum = Field(default=ActiveUserEnum.ACTIVE)
    id_rol: Optional[int] = Field(default=None, foreign_key="roles.id_rol")

class Usuario(UsuarioBase, table=True):
    __tablename__ = "usuarios"

    id: Optional[int] = Field(default=None, primary_key=True)
    password: str  # En producción esto debe ser el Hash, no texto plano
    
    # Fechas automáticas
    fecha_registro: datetime = Field(default_factory=bolivia_now)
    fecha_ultima_modificacion: datetime = Field(default_factory=bolivia_now)

    # RELACIONES
    # 1. Relación con Rol (N:1 - Muchos usuarios tienen un Rol)
    # Usamos string "Role" para evitar problemas de importación circular
    rol: Optional["Rol"] = Relationship(back_populates="usuarios")

    # 2. Relación con Acciones (N:N - Muchos usuarios tienen muchas acciones)
    casos: List["Caso"] = Relationship(back_populates="usuario")
    documentos_conocimiento: list["DocumentoConocimiento"] = Relationship(back_populates="usuario")

    actions: List["Action"] = Relationship(
        back_populates="usuarios",
        link_model=UsuarioActionLink
    )

    prompts_creados: list["SystemPrompt"] = Relationship(back_populates="experto_creador")

# Modelos para CRUD (Create/Update)
class UsuarioCreate(UsuarioBase):
    password: str # El usuario envía la password plana aquí

class UsuarioUpdate(SQLModel):
    nombre_completo: Optional[str] = None
    email: Optional[str] = None
    activo: Optional[ActiveUserEnum] = None
    password: Optional[str] = None
    id_rol: Optional[int] = None