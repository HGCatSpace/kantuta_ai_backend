from typing import List
from fastapi import APIRouter, Depends, status, HTTPException
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_session
from models.rol import Rol, RolCreate, RolUpdate

router = APIRouter(
    prefix="/roles",    # Todas las rutas empezarán con /roles
    tags=["Roles"]      # Para agruparlo en la documentación automática
)

# --- ENDPOINT POST (Crear) ---
@router.post("/", response_model=Rol, status_code=status.HTTP_201_CREATED)
async def create_rol(
    rol_data: RolCreate, 
    session: AsyncSession = Depends(get_session)
):
    """
    Crea un nuevo rol en la base de datos.
    """
    # 1. Convertir el modelo de entrada (RolCreate) a modelo de tabla (Rol)
    new_rol = Rol.model_validate(rol_data)
    
    # 2. Guardar en la DB
    session.add(new_rol)
    await session.commit()
    
    # 3. Refrescar para obtener el ID generado automáticamente
    await session.refresh(new_rol)
    
    return new_rol

# --- ENDPOINT GET (Listar) ---
@router.get("/", response_model=List[Rol])
async def read_roles(
    session: AsyncSession = Depends(get_session)
):
    """
    Obtiene la lista de roles registrados.
    """
    # 1. Crear la consulta SQL (SELECT * FROM roles)
    statement = select(Rol)
    
    # 2. Ejecutar la consulta de forma asíncrona
    result = await session.execute(statement)
    
    # 3. Retornar los resultados escalares (objetos Rol)
    roles = result.scalars().all()
    
    return roles

# --- ENDPOINT PATCH (Actualizar) ---
@router.patch("/{id_rol}", response_model=Rol)
async def update_rol(
    id_rol: int,
    rol_update: RolUpdate,
    session: AsyncSession = Depends(get_session)
):
    """
    Actualiza la información de un rol existente.
    """
    # 1. Buscar el rol por ID
    statement = select(Rol).where(Rol.id_rol == id_rol)
    result = await session.execute(statement)
    rol_db = result.scalar_one_or_none()

    # 2. Validar que exista
    if not rol_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=f"El rol con ID {id_rol} no existe."
        )

    # 3. Actualizar los campos
    # exclude_unset=True permite que solo se actualicen los datos que enviaste
    update_data = rol_update.model_dump(exclude_unset=True)
    
    rol_db.sqlmodel_update(update_data)

    # 4. Guardar cambios
    session.add(rol_db)
    await session.commit()
    await session.refresh(rol_db)

    return rol_db