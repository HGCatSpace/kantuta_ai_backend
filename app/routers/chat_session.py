import uuid
from typing import List
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, status, HTTPException
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session
from models.chat_session import ChatSession, ChatSessionCreate, ChatSessionUpdate
from models.casos import Caso
from models.user import Usuario

router = APIRouter(
    prefix="/chats",
    tags=["Sesiones de Chat"]
)

# --- HELPER HORA BOLIVIA ---
def get_bolivia_now():
    return datetime.now(ZoneInfo("America/La_Paz")).replace(tzinfo=None)

# --- 1. CREAR CHAT (POST) ---
@router.post("/", response_model=ChatSession, status_code=status.HTTP_201_CREATED)
async def create_chat_session(
    chat_data: ChatSessionCreate, 
    session: AsyncSession = Depends(get_session)
):
    """
    Crea una nueva sesión. Genera un UUID automático para LangGraph.
    """
    # 1. Validar Caso
    caso = await session.get(Usuario, chat_data.caso_id)
    if not caso:
        raise HTTPException(status_code=404, detail="Caso no encontrado")

    # 3. Generar UUID y Crear Objeto
    # LangGraph usa strings como thread_id, así que usamos uuid4
    new_uuid = str(uuid.uuid4())
    
    new_chat = ChatSession(
        id_session=new_uuid, # <--- ID generado aquí
        titulo=chat_data.titulo,
        caso_id=chat_data.caso_id,
        es_activo=True
    )
    
    try:
        session.add(new_chat)
        await session.commit()
        await session.refresh(new_chat)
        return new_chat
    except Exception as e:
        await session.rollback()
        print(f"Error creando chat: {e}")
        raise HTTPException(status_code=500, detail="Error interno al crear el chat")

# --- 2. LEER CHAT POR ID (GET) ---
@router.get("/{session_id}", response_model=ChatSession)
async def read_chat(
    session_id: str, 
    session: AsyncSession = Depends(get_session)
):
    """
    Obtiene la metadata de un chat específico.
    (No trae los mensajes, solo título, fecha, etc.)
    """
    chat = await session.get(ChatSession, session_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat no encontrado")
    return chat

# --- 3. LEER CHATS POR CASO (GET) ---
@router.get("/caso/{caso_id}", response_model=List[ChatSession])
async def read_chats_by_caso(
    caso_id: int,
    session: AsyncSession = Depends(get_session)
):
    """
    Lista todos los chats activos asociados a un caso legal.
    """
    # Verificamos que el caso exista primero (opcional pero recomendado)
    caso = await session.get(Caso, caso_id)
    if not caso:
        raise HTTPException(status_code=404, detail="Caso legal no encontrado")

    # Buscamos chats de ese caso QUE ESTÉN ACTIVOS
    statement = select(ChatSession).where(
        ChatSession.caso_id == caso_id,
        ChatSession.es_activo == True # Filtramos los archivados
    ).order_by(ChatSession.ultimo_acceso.desc()) # Los más recientes primero
    
    result = await session.execute(statement)
    return result.scalars().all()

# --- 4. LEER CHATS POR USUARIO (GET - Extra útil) ---
@router.get("/usuario/{usuario_id}", response_model=List[ChatSession])
async def read_chats_by_user(
    usuario_id: int,
    session: AsyncSession = Depends(get_session)
):
    """
    Lista todos los chats de un usuario (incluyendo los que no tienen caso).
    """
    statement = select(ChatSession).join(Caso).where(
        Caso.usuario_id == usuario_id,
        ChatSession.es_activo == True
    ).order_by(ChatSession.ultimo_acceso.desc())
    
    result = await session.execute(statement)
    return result.scalars().all()

# --- 5. ACTUALIZAR CHAT (PATCH) ---
@router.patch("/{session_id}", response_model=ChatSession)
async def update_chat(
    session_id: str,
    chat_update: ChatSessionUpdate,
    session: AsyncSession = Depends(get_session)
):
    """
    Actualiza el título o fecha de acceso.
    """
    chat_db = await session.get(ChatSession, session_id)
    if not chat_db:
        raise HTTPException(status_code=404, detail="Chat no encontrado")

    update_data = chat_update.model_dump(exclude_unset=True)
    # Actualizamos el objeto
    chat_db.sqlmodel_update(update_data)
    
    # Si queremos forzar que se note actividad reciente (opcional):
    chat_db.ultimo_acceso = get_bolivia_now()

    session.add(chat_db)
    await session.commit()
    await session.refresh(chat_db)
    return chat_db

# --- 6. BORRAR / ARCHIVAR CHAT (DELETE) ---
@router.delete("/{session_id}", response_model=ChatSession)
async def archive_chat(
    session_id: str,
    session: AsyncSession = Depends(get_session)
):
    """
    Soft Delete: Marca el chat como inactivo (es_activo = False).
    No borra el historial de LangGraph.
    """
    chat_db = await session.get(ChatSession, session_id)
    if not chat_db:
        raise HTTPException(status_code=404, detail="Chat no encontrado")

    # Lógica de archivado
    chat_db.es_activo = False
    # Opcional: Podríamos agregar un sufijo al título tipo "[ARCHIVADO]"
    
    session.add(chat_db)
    await session.commit()
    await session.refresh(chat_db)
    
    return chat_db