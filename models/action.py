from typing import Optional, List, TYPE_CHECKING
from sqlmodel import SQLModel, Field, Relationship

from models.links import UsuarioActionLink

if TYPE_CHECKING:
    from models.user import Usuario

# 1. Clase Base (Esquema común)
class ActionBase(SQLModel):
    nombre: str
    descripcion: str

# 2. Clase de Tabla (Database Model)
class Action(ActionBase, table=True):
    __tablename__ = "actions"
    
    id_action: Optional[int] = Field(default=None, primary_key=True)
    
    usuarios: List["Usuario"] = Relationship(
        back_populates="actions",
        link_model=UsuarioActionLink 
    )

# 3. Modelo para Crear (Create CRUD)
class ActionCreate(ActionBase):
    pass

# 4. Modelo para Actualizar (Update CRUD)
class ActionUpdate(ActionBase):
    pass