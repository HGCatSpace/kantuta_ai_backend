from typing import Optional, List, TYPE_CHECKING
from sqlmodel import SQLModel, Field, Relationship

if TYPE_CHECKING:
    from models.user import Usuario


# 1. Clase Base (Schema)
class RolBase(SQLModel):
    nombre: str
    description: str 

# 2. Clase de Tabla (Database Model)
class Rol(RolBase, table=True):
    __tablename__ = "roles"  
    id_rol: Optional[int] = Field(default=None, primary_key=True)
    usuarios: List["Usuario"] = Relationship(back_populates="rol")

# 3. Modelo para Create CRUD
class RolCreate(RolBase):
    pass

# 4. Modelo para Update CRUD
class RolUpdate(RolBase):
    pass