from typing import List
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, status, HTTPException, Query
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session
from models.casos import Caso, CasoCreate, CasoUpdate, EstadoCaso
from models.user import Usuario

router = APIRouter(
    prefix="/casos",
    tags=["Casos Legales"]
)

# --- HELPER (Reutilizamos la lógica de hora boliviana) ---
def get_bolivia_now():
    return datetime.now(ZoneInfo("America/La_Paz")).replace(tzinfo=None)

# --- 1. CREAR CASO (POST) ---
@router.post("/", response_model=Caso, status_code=status.HTTP_201_CREATED)
async def create_caso(
    caso_data: CasoCreate, 
    session: AsyncSession = Depends(get_session)
):
    """
    Crea un nuevo caso legal.
    """
    # 1. Validar que el usuario (abogado) exista
    usuario = await session.get(Usuario, caso_data.usuario_id)
    if not usuario:
        raise HTTPException(status_code=404, detail="El usuario especificado no existe")

    # 2. Crear instancia
    # Nota: Las fechas se crean solas gracias al default_factory del modelo,
    # pero si quisieras forzarlas, podrías hacerlo aquí.
    new_caso = Caso.model_validate(caso_data)
    
    try:
        session.add(new_caso)
        await session.commit()
        await session.refresh(new_caso)
        return new_caso
    except Exception as e:
        await session.rollback()
        print(f"Error creando caso: {e}")
        raise HTTPException(status_code=500, detail="Error interno al crear el caso")

# --- 2. LEER TODOS LOS CASOS (GET) ---
@router.get("/", response_model=List[Caso])
async def read_casos(
    offset: int = Query(0, description="Casos a omitir"), 
    limit: int = Query(10, description="Número de casos"), 
    session: AsyncSession = Depends(get_session)
):
    """
    Lista todos los casos del sistema (Paginado).
    """
    statement = select(Caso).offset(offset).limit(limit)
    result = await session.execute(statement)
    return result.scalars().all()

# --- 3. LEER CASOS POR USUARIO (GET) ---
@router.get("/usuario/{usuario_id}", response_model=List[Caso])
async def read_casos_by_user(
    usuario_id: int,
    session: AsyncSession = Depends(get_session)
):
    """
    Obtiene todos los casos asignados a un usuario específico.
    """

    statement = select(Usuario).where(Usuario.id == usuario_id)
    result = await session.execute(statement)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")


    statement = select(Caso).where(Caso.usuario_id == usuario_id)
    result = await session.execute(statement)
    casos = result.scalars().all()
    
    # Retornamos lista vacía si no tiene casos, no es un error 404
    return casos

# --- 4. LEER UN CASO ESPECÍFICO (GET ID) ---
@router.get("/{id_caso}", response_model=Caso)
async def read_caso(
    id_caso: int,
    session: AsyncSession = Depends(get_session)
):
    caso = await session.get(Caso, id_caso)
    if not caso:
        raise HTTPException(status_code=404, detail="Caso no encontrado")
    return caso

# --- 5. ACTUALIZAR CASO (PATCH) ---
@router.patch("/{id_caso}", response_model=Caso)
async def update_caso(
    id_caso: int,
    caso_update: CasoUpdate,
    session: AsyncSession = Depends(get_session)
):
    """
    Actualiza título, descripción o estado.
    Actualiza automáticamente la fecha_actualizacion.
    """
    # 1. Buscar
    caso_db = await session.get(Caso, id_caso)
    if not caso_db:
        raise HTTPException(status_code=404, detail="Caso no encontrado")

    # 2. Procesar datos
    update_data = caso_update.model_dump(exclude_unset=True)
    
    # 3. Forzar actualización de fecha (Hora Bolivia)
    update_data["fecha_actualizacion"] = get_bolivia_now()

    # 4. Aplicar cambios
    caso_db.sqlmodel_update(update_data)
    
    session.add(caso_db)
    await session.commit()
    await session.refresh(caso_db)
    return caso_db

# --- 6. BORRAR (SOFT DELETE / ARCHIVAR) ---
@router.delete("/{id_caso}", response_model=Caso)
async def archive_caso(
    id_caso: int,
    session: AsyncSession = Depends(get_session)
):
    """
    No borra el registro de la DB.
    Cambia el estado a 'ARCHIVADO' y actualiza la fecha.
    """
    caso_db = await session.get(Caso, id_caso)
    if not caso_db:
        raise HTTPException(status_code=404, detail="Caso no encontrado")

    # Lógica de Soft Delete
    caso_db.estado = EstadoCaso.ARCHIVADO
    caso_db.fecha_actualizacion = get_bolivia_now()
    
    session.add(caso_db)
    await session.commit()
    await session.refresh(caso_db)
    
    return caso_db