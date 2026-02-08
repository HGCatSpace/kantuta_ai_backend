from typing import List
from fastapi import APIRouter, Depends, status, HTTPException
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_session
from models.action import Action, ActionCreate, ActionUpdate

router = APIRouter(
    prefix="/actions",
    tags=["Actions"]
)

# --- CREATE (POST) ---
@router.post("/", response_model=Action, status_code=status.HTTP_201_CREATED)
async def create_action(
    action_data: ActionCreate, 
    session: AsyncSession = Depends(get_session)
):
    """
    Registra una nueva acción en el sistema.
    """
    new_action = Action.model_validate(action_data)
    session.add(new_action)
    await session.commit()
    await session.refresh(new_action)
    return new_action

# --- READ (GET List) ---
@router.get("/", response_model=List[Action])
async def read_actions(
    session: AsyncSession = Depends(get_session)
):
    """
    Obtiene la lista de todas las acciones registradas.
    """
    statement = select(Action)
    result = await session.execute(statement)
    actions = result.scalars().all()
    return actions

# --- UPDATE (PUT) ---
@router.put("/{id_action}", response_model=Action)
async def update_action(
    id_action: int,
    action_update: ActionUpdate,
    session: AsyncSession = Depends(get_session)
):
    """
    Actualiza una acción existente. 
    Requiere enviar TODOS los campos (nombre y descripción).
    """
    # 1. Buscar la acción en la DB
    statement = select(Action).where(Action.id_action == id_action)
    result = await session.execute(statement)
    action_db = result.scalar_one_or_none()

    # 2. Verificar existencia
    if not action_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"La acción con ID {id_action} no existe"
        )

    # 3. Actualizar datos (Sobreescribir todo)
    action_db.sqlmodel_update(action_update.model_dump())

    # 4. Guardar
    session.add(action_db)
    await session.commit()
    await session.refresh(action_db)

    return action_db