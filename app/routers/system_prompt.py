from typing import List, Optional
from fastapi import APIRouter, Depends, status, HTTPException, Query
from sqlmodel import select, col
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from db import get_session
from models.user import Usuario
from models.system_prompt import (
    SystemPrompt,
    SystemPromptCreate,
    SystemPromptUpdate,
    SystemPromptPublic,
    bolivia_now,
)
from models.links import PromptDocumentoLink

router = APIRouter(
    prefix="/prompts",
    tags=["System Prompts"]
)


def _to_public(prompt: SystemPrompt) -> SystemPromptPublic:
    """Convierte un SystemPrompt (table) a SystemPromptPublic, incluyendo nombre del creador."""
    data = prompt.model_dump()
    data["nombre_creador"] = (
        prompt.experto_creador.nombre_completo
        if prompt.experto_creador else None
    )
    # Include linked document IDs
    data["documentos_conocimiento"] = [
        doc.id_documento for doc in prompt.documentos_conocimiento
    ] if prompt.documentos_conocimiento else []
    return SystemPromptPublic.model_validate(data)


# ==========================================
# 1. CREATE (POST)
# ==========================================
@router.post("/", response_model=SystemPromptPublic, status_code=status.HTTP_201_CREATED)
async def create_prompt(
    prompt_data: SystemPromptCreate,
    session: AsyncSession = Depends(get_session),
    current_user: Usuario = Depends(get_current_user),
):
    prompt_dict = prompt_data.model_dump(exclude={"documentos_conocimiento"})
    prompt_dict["id_experto_creador"] = current_user.id

    new_prompt = SystemPrompt.model_validate(prompt_dict)

    try:
        session.add(new_prompt)
        await session.commit()
        await session.refresh(new_prompt)

        result = await session.execute(
            select(SystemPrompt)
            .options(
                selectinload(SystemPrompt.experto_creador),
                selectinload(SystemPrompt.documentos_conocimiento),
            )
            .where(SystemPrompt.id_prompt == new_prompt.id_prompt)
        )
        new_prompt = result.scalar_one()

        # Agregar a la tabla de prompt_documento_link
        for doc_id in prompt_data.documentos_conocimiento:
            link = PromptDocumentoLink(system_prompt_id=new_prompt.id_prompt, documento_id=doc_id)
            session.add(link)
        await session.commit()

        return _to_public(new_prompt)
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=f"Error creando prompt: {str(e)}")


# ==========================================
# 2. READ ALL (GET) - Con Filtros
# ==========================================
@router.get("/", response_model=List[SystemPromptPublic])
async def read_prompts(
    offset: int = Query(0, ge=0),
    limit: int = Query(10),
    search: Optional[str] = Query(None, description="Búsqueda por nombre"),
    es_activo: Optional[bool] = Query(None, description="Filtrar por estado activo/inactivo"),
    session: AsyncSession = Depends(get_session),
    current_user: Usuario = Depends(get_current_user),
):
    query = select(SystemPrompt).options(
        selectinload(SystemPrompt.experto_creador),
        selectinload(SystemPrompt.documentos_conocimiento),
    )

    if search:
        query = query.where(col(SystemPrompt.nombre).ilike(f"%{search}%"))

    if es_activo is not None:
        query = query.where(SystemPrompt.es_activo == es_activo)

    query = query.order_by(SystemPrompt.fecha_creacion.desc())
    query = query.offset(offset).limit(limit)

    result = await session.execute(query)
    prompts = result.scalars().all()

    return [_to_public(p) for p in prompts]


# ==========================================
# 2b. COUNT (GET) - Para paginación
# ==========================================
@router.get("/count")
async def count_prompts(
    search: Optional[str] = Query(None, description="Búsqueda por nombre"),
    es_activo: Optional[bool] = Query(None, description="Filtrar por estado activo/inactivo"),
    session: AsyncSession = Depends(get_session),
    current_user: Usuario = Depends(get_current_user),
):
    from sqlalchemy import func
    query = select(func.count()).select_from(SystemPrompt)

    if search:
        query = query.where(col(SystemPrompt.nombre).ilike(f"%{search}%"))

    if es_activo is not None:
        query = query.where(SystemPrompt.es_activo == es_activo)

    result = await session.execute(query)
    total = result.scalar_one()
    return {"total": total}


# ==========================================
# 3. READ ONE (GET by ID)
# ==========================================
@router.get("/{id_prompt}", response_model=SystemPromptPublic)
async def read_prompt(
    id_prompt: int,
    session: AsyncSession = Depends(get_session),
    current_user: Usuario = Depends(get_current_user),
):
    result = await session.execute(
        select(SystemPrompt)
        .options(
            selectinload(SystemPrompt.experto_creador),
            selectinload(SystemPrompt.documentos_conocimiento),
        )
        .where(SystemPrompt.id_prompt == id_prompt)
    )
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt no encontrado")
    return _to_public(prompt)


# ==========================================
# 4. UPDATE (PATCH)
# ==========================================
@router.patch("/{id_prompt}", response_model=SystemPromptPublic)
async def update_prompt(
    id_prompt: int,
    prompt_update: SystemPromptUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: Usuario = Depends(get_current_user),
):
    result = await session.execute(
        select(SystemPrompt)
        .options(selectinload(SystemPrompt.experto_creador))
        .where(SystemPrompt.id_prompt == id_prompt)
    )
    prompt_db = result.scalar_one_or_none()
    if not prompt_db:
        raise HTTPException(status_code=404, detail="Prompt no encontrado")

    update_data = prompt_update.model_dump(exclude_unset=True)
    update_data["fecha_actualizacion"] = bolivia_now()

    # Handle documentos_conocimiento separately (it's a link table, not a column)
    doc_ids = update_data.pop("documentos_conocimiento", None)

    prompt_db.sqlmodel_update(update_data)

    session.add(prompt_db)
    await session.commit()
    await session.refresh(prompt_db)

    # Sync link table if documentos_conocimiento was provided
    if doc_ids is not None:
        # Delete existing links
        existing = await session.execute(
            select(PromptDocumentoLink).where(
                PromptDocumentoLink.system_prompt_id == id_prompt
            )
        )
        for link in existing.scalars().all():
            await session.delete(link)
        # Add new links
        for doc_id in doc_ids:
            session.add(PromptDocumentoLink(system_prompt_id=id_prompt, documento_id=doc_id))
        await session.commit()

    # Recargar con relación
    result = await session.execute(
        select(SystemPrompt)
        .options(
            selectinload(SystemPrompt.experto_creador),
            selectinload(SystemPrompt.documentos_conocimiento),
        )
        .where(SystemPrompt.id_prompt == id_prompt)
    )
    prompt_db = result.scalar_one()
    return _to_public(prompt_db)


# ==========================================
# 5. DELETE (Soft delete)
# ==========================================
@router.delete("/{id_prompt}", response_model=SystemPromptPublic)
async def delete_prompt(
    id_prompt: int,
    session: AsyncSession = Depends(get_session),
    current_user: Usuario = Depends(get_current_user),
):
    result = await session.execute(
        select(SystemPrompt)
        .options(
            selectinload(SystemPrompt.experto_creador),
            selectinload(SystemPrompt.documentos_conocimiento),
        )
        .where(SystemPrompt.id_prompt == id_prompt)
    )
    prompt_db = result.scalar_one_or_none()
    if not prompt_db:
        raise HTTPException(status_code=404, detail="Prompt no encontrado")

    prompt_db.es_activo = False
    prompt_db.fecha_actualizacion = bolivia_now()

    session.add(prompt_db)
    await session.commit()
    await session.refresh(prompt_db)

    # Recargar con relación
    result = await session.execute(
        select(SystemPrompt)
        .options(
            selectinload(SystemPrompt.experto_creador),
            selectinload(SystemPrompt.documentos_conocimiento),
        )
        .where(SystemPrompt.id_prompt == id_prompt)
    )
    prompt_db = result.scalar_one()
    return _to_public(prompt_db)
