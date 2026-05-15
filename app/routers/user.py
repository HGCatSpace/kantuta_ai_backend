from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, status, HTTPException, Query
from sqlmodel import select
from sqlalchemy import func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from passlib.context import CryptContext
from app.core.deps import get_current_user

from db import get_session
from models.user import Usuario, UsuarioCreate, UsuarioUpdate, ActiveUserEnum
from models.action import Action
from models.links import UsuarioActionLink
from models.casos import Caso, EstadoCaso
from models.documento_conocimiento import DocumentoConocimiento
from models.chat_session import ChatSession
from app.schemas.user import UserDashboardSchema, DocumentoRecienteSchema

ACCION_GESTION_DOCS = "Gestión de documentos para la base de conocimiento"


def _bolivia_now():
    return datetime.now(ZoneInfo("America/La_Paz")).replace(tzinfo=None)

router = APIRouter(
    prefix="/users",
    tags=["Users"]
)

# --- CONFIGURACIÓN DE SEGURIDAD (HASHING) ---
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


@router.get("/me", response_model=Usuario)
async def read_users_me(
    session: AsyncSession = Depends(get_session),
    current_user: Usuario = Depends(get_current_user)
):
    """
    Este endpoint atrapa '/users/me' ANTES de que llegue al de abajo.
    Usa el token para saber quién eres.
    Carga relaciones (rol, actions) para el frontend.
    """
    statement = select(Usuario).where(Usuario.id == current_user.id).options(
        selectinload(Usuario.rol),
        selectinload(Usuario.actions)
    )
    result = await session.execute(statement)
    return result.scalar_one()

# ==========================================
# 0. DASHBOARD (Endpoint)
# El DTO vive en app/schemas/user.py
# ==========================================

@router.get("/dashboard", response_model=UserDashboardSchema)
async def read_dashboard_data(
    session: AsyncSession = Depends(get_session),
    current_user: Usuario = Depends(get_current_user)
):
    """
    Dashboard del usuario autenticado.

    Devuelve:
    - casos_activos: COUNT de casos con estado != ARCHIVADO.
    - documentos_recientes: hasta 5 documentos más recientes (solo si el usuario
      tiene la acción 'Gestión de documentos para la base de conocimiento').
    - sesiones_chat_30d: COUNT de ChatSession del usuario en los últimos 30 días.
    - ultimo_acceso: fecha_ultima_modificacion del usuario.
    """
    # 1. Cargar usuario con rol + acciones (para gating de documentos)
    statement = select(Usuario).where(Usuario.id == current_user.id).options(
        selectinload(Usuario.rol),
        selectinload(Usuario.actions),
    )
    result = await session.execute(statement)
    user_loaded = result.scalar_one()

    nombres_acciones = {a.nombre for a in user_loaded.actions}
    puede_ver_docs = ACCION_GESTION_DOCS in nombres_acciones

    # 2. Casos activos: COUNT en SQL filtrando por estado != ARCHIVADO
    stmt_casos = (
        select(func.count(Caso.id_caso))
        .where(Caso.usuario_id == user_loaded.id, Caso.estado != EstadoCaso.ARCHIVADO)
    )
    result = await session.execute(stmt_casos)
    casos_activos = result.scalar_one() or 0

    # 3. Documentos recientes: top 5 por fecha_creacion, solo si tiene la acción
    documentos_recientes: List[DocumentoRecienteSchema] = []
    if puede_ver_docs:
        stmt_docs = (
            select(DocumentoConocimiento)
            .where(DocumentoConocimiento.usuario_id == user_loaded.id)
            .order_by(DocumentoConocimiento.fecha_creacion.desc())
            .limit(5)
        )
        result = await session.execute(stmt_docs)
        documentos_recientes = [
            DocumentoRecienteSchema(
                id_documento=doc.id_documento,
                titulo=doc.titulo,
                categoria=doc.categoria.value if hasattr(doc.categoria, "value") else str(doc.categoria),
                fecha_creacion=doc.fecha_creacion,
            )
            for doc in result.scalars().all()
        ]

    # 4. Sesiones de chat en los últimos 30 días.
    # ChatSession se relaciona al usuario via Caso, así que hacemos JOIN.
    hace_30d = _bolivia_now() - timedelta(days=30)
    stmt_sesiones = (
        select(func.count(ChatSession.id_session))
        .join(Caso, ChatSession.caso_id == Caso.id_caso)
        .where(
            Caso.usuario_id == user_loaded.id,
            ChatSession.fecha_creacion >= hace_30d,
        )
    )
    result = await session.execute(stmt_sesiones)
    sesiones_chat_30d = result.scalar_one() or 0

    return UserDashboardSchema(
        id=user_loaded.id,
        nombres=user_loaded.nombres,
        apellido_paterno=user_loaded.apellido_paterno,
        apellido_materno=user_loaded.apellido_materno,
        email=user_loaded.email,
        rol=user_loaded.rol.nombre if user_loaded.rol else "Sin Rol",
        casos_activos=casos_activos,
        documentos_recientes=documentos_recientes,
        sesiones_chat_30d=sesiones_chat_30d,
        ultimo_acceso=user_loaded.fecha_ultima_modificacion,
    )

# --- COUNT ---
@router.get("/count")
async def count_users(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(func.count()).select_from(Usuario))
    total = result.scalar_one()
    return {"total": total}

# --- 1. CREATE (POST) ---
@router.post("/", response_model=Usuario, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UsuarioCreate, 
    session: AsyncSession = Depends(get_session)
):
    # 1. Encriptar la contraseña antes de guardar
    user_dict = user_data.model_dump()
    password_plana = user_dict.pop("password")
    hashed_password = get_password_hash(password_plana)
    user_dict["password"] = hashed_password
    # 2. Crear instancia con la password hasheada
    # exclude={"password"} evita que pasemos la plana, la asignamos manual
    new_user = Usuario.model_validate(user_dict)
    
    try:
        session.add(new_user)
        await session.commit()
        await session.refresh(new_user)
        return new_user
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail="Error creando usuario. Posible email, username duplicado o rol inexistente.")

# --- 2. READ ALL (GET) ---
@router.get("/", response_model=List[Usuario])
async def read_users(
    offset: int = Query(0, description="Registros a omitir"), 
    limit: int = Query(10, description="Número de registros"), 
    session: AsyncSession = Depends(get_session)
):
    # Usamos options(selectinload(...)) para traer los roles y acciones relacionados
    statement = select(Usuario).options(
        selectinload(Usuario.rol),
        selectinload(Usuario.actions)
    ).offset(offset).limit(limit)
    
    result = await session.execute(statement)
    return result.scalars().all()

# --- 3. READ ONE (GET by ID) ---
@router.get("/{user_id}", response_model=Usuario)
async def read_user(
    user_id: int, 
    session: AsyncSession = Depends(get_session)
):
    statement = select(Usuario).where(Usuario.id == user_id).options(
        selectinload(Usuario.rol),
        selectinload(Usuario.actions)
    )
    result = await session.execute(statement)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return user

# --- 4. UPDATE (PATCH - Actualización Parcial) ---
@router.patch("/{user_id}", response_model=Usuario)
async def update_user(
    user_id: int, 
    user_update: UsuarioUpdate, 
    session: AsyncSession = Depends(get_session)
):
    # Buscar usuario
    statement = select(Usuario).where(Usuario.id == user_id)
    result = await session.execute(statement)
    user_db = result.scalar_one_or_none()

    if not user_db:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # Preparar datos
    update_data = user_update.model_dump(exclude_unset=True)
    
    # Si viene password, hay que hashearla de nuevo
    if "password" in update_data and update_data["password"]:
        update_data["password"] = get_password_hash(update_data["password"])

    update_data["fecha_ultima_modificacion"]  = datetime.now(ZoneInfo("America/La_Paz")).replace(tzinfo=None)
    user_db.sqlmodel_update(update_data)
    
    session.add(user_db)
    await session.commit()
    await session.refresh(user_db)
    return user_db

# --- 5. SOFT DELETE (DELETE -> Inactive) ---
@router.delete("/{user_id}", response_model=Usuario)
async def delete_user(
    user_id: int, 
    session: AsyncSession = Depends(get_session)
):
    """
    Soft Delete: No borra el registro, solo cambia activo = 'inactive'
    """
    statement = select(Usuario).where(Usuario.id == user_id)
    result = await session.execute(statement)
    user_db = result.scalar_one_or_none()

    if not user_db:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # Cambio de estado
    user_db.activo = ActiveUserEnum.INACTIVE
    
    session.add(user_db)
    await session.commit()
    await session.refresh(user_db)
    return user_db

# ==========================================
# GESTIÓN DE ACCIONES (Many-to-Many)
# ==========================================

# --- A. LEER ACCIONES DE UN USUARIO ---
@router.get("/{user_id}/actions", response_model=List[Action])
async def read_user_actions(
    user_id: int, 
    session: AsyncSession = Depends(get_session)
):
    user = await read_user(user_id, session) # Reusamos la funcion de arriba
    return user.actions

# --- B. ASIGNAR ACCIÓN (Link) ---
@router.post("/{user_id}/actions/{action_id}")
async def assign_action_to_user(
    user_id: int, 
    action_id: int, 
    session: AsyncSession = Depends(get_session)
):
    """
    Crea el vínculo en la tabla intermedia usuario_action_link
    """
    # 1. Verificar que existan ambos
    user = await session.get(Usuario, user_id)
    action = await session.get(Action, action_id)
    
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrados")
    
    if not action:
        raise HTTPException(status_code=404, detail="Acción no encontrados")
    
    query_link = select(UsuarioActionLink).where(
        UsuarioActionLink.usuario_id == user_id,
        UsuarioActionLink.action_id == action_id
    )
    result = await session.execute(query_link)
    existing_link = result.first() # Usamos first() por si acaso ya hay duplicados previos

    if existing_link:
        # Si ya existe, devolvemos un error 409 (Conflict) o un mensaje de éxito falso.
        # Aquí lanzamos error para ser explícitos.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, 
            detail=f"El usuario '{user.nombre_de_usuario}' ya tiene asignada la acción '{action.nombre}'."
        )

    # 2. Crear el link manual
    # (SQLAlchemy a veces maneja esto auto con user.actions.append, 
    # pero en async es más seguro insertar en la tabla intermedia explícitamente)
    new_link = UsuarioActionLink(usuario_id=user_id, action_id=action_id)
    
    try:
        session.add(new_link)
        await session.commit()
        return {"message": f"Acción '{action.nombre}' asignada al usuario '{user.nombre_de_usuario}'"}
    except Exception:
        await session.rollback()
        raise HTTPException(status_code=400, detail="Esa acción ya está asignada a este usuario")

# --- C. REMOVER ACCIÓN (Unlink) ---
@router.delete("/{user_id}/actions/{action_id}")
async def remove_action_from_user(
    user_id: int, 
    action_id: int, 
    session: AsyncSession = Depends(get_session)
):
    """
    Elimina el vínculo físico de la tabla intermedia
    """
    statement = select(UsuarioActionLink).where(
        UsuarioActionLink.usuario_id == user_id,
        UsuarioActionLink.action_id == action_id
    )
    result = await session.execute(statement)
    link = result.scalar_one_or_none()
    
    if not link:
        raise HTTPException(status_code=404, detail="El usuario no tiene asignada esta acción")
        
    await session.delete(link)
    await session.commit()
    
    return {"message": "Acción removida correctamente"}