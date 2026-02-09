from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_session
from models.chat_session import ChatSession
from pydantic import BaseModel
from datetime import datetime
from zoneinfo import ZoneInfo
from langchain_core.messages import BaseMessage, message_to_dict
from langchain_core.documents import Document
# Importamos el BUILDER de tu agente
from ai.agents.conversational_assistant.agent import builder 

router = APIRouter(
    prefix="/chat-agent",
    tags=["Interacción con Agente IA"]
)

# --- Schema Local ---
class UserMessage(BaseModel):
    content: str

# --- Helper Fecha ---
def bolivia_now():
    return datetime.now(ZoneInfo("America/La_Paz")).replace(tzinfo=None)

@router.post("/{session_id}/message")
async def chat_with_agent(
    session_id: str,
    user_msg: UserMessage,
    request: Request, # Para acceder al checkpointer global
    db_session: AsyncSession = Depends(get_session)
):
    """
    Envía un mensaje al agente conversacional.
    Usa LangGraph Checkpointer para mantener el contexto.
    """
    
    # 1. VALIDACIÓN DE SEGURIDAD (SQLModel)
    # Verificamos que la sesión exista y esté activa en tu DB
    chat_db = await db_session.get(ChatSession, session_id)
    if not chat_db:
        raise HTTPException(status_code=404, detail="Sesión de chat no encontrada")
    
    if not chat_db.es_activo:
        raise HTTPException(status_code=400, detail="Este chat está archivado/cerrado.")

    # 2. RECUPERAR EL CHECKPOINTER (Postgres)
    # Este se inicializó en main.py (lifespan)
    checkpointer = request.app.state.checkpointer
    
    if not checkpointer:
        raise HTTPException(status_code=500, detail="Error: Checkpointer no inicializado")

    # 3. COMPILAR EL GRAFO CON MEMORIA
    # Aquí unimos el 'cerebro' (builder) con la 'memoria' (checkpointer)
    agent_with_memory = builder.compile(checkpointer=checkpointer)
    
    # 4. CONFIGURAR EL HILO (THREAD)
    # Usamos el mismo UUID que generaste en la tabla ChatSession
    config = {"configurable": {"thread_id": session_id}}
    
    # 5. INVOCAR AL AGENTE
    # Asumimos que tu RetrievalState tiene una clave 'question' o 'messages'.
    # Ajusta esto según cómo definiste tu RetrievalState.
    # Opción A: Si usas mensajes estándar
    # inputs = {"messages": [("user", user_msg.content)]} 
    
    # Opción B: Si usas un estado personalizado tipo RAG (question/answer)
    human_message = HumanMessage(content=user_msg.content)
    try:
        # Usamos ainvoke para no bloquear el server
        result = await agent_with_memory.ainvoke({"messages": human_message}, config=config)
        
            # 6. EXTRAER RESPUESTA
            # Depende de tu RetrievalState. Normalmente es 'answer', 'generation' o el último mensaje.
        #ai_response = result.get("answer") or result.get("generation") or "Error generando respuesta"
        
            # Si el resultado es una lista de mensajes, sacamos el último
        #if isinstance(ai_response, list):
        #    ai_response = ai_response[-1].content
            
    except Exception as e:
        print(f"Error en LangGraph: {e}")
        raise HTTPException(status_code=500, detail=f"Error del Agente: {str(e)}")

    # 7. ACTUALIZAR METADATA (Último Acceso)
    chat_db.ultimo_acceso = bolivia_now()
    db_session.add(chat_db)
    await db_session.commit()

    return {
        "response": result,
        "session_id": session_id
    }



@router.get("/{session_id}/state")
async def get_agent_state(
    session_id: str,
    request: Request,
    db_session: AsyncSession = Depends(get_session)
):
    """
    Recupera TODO el estado interno de la memoria del Agente para esta sesión.
    Incluye: Mensajes, Documentos recuperados, Variables internas, etc.
    """
    
    # 1. VALIDACIÓN (Opcional, pero recomendada)
    chat_db = await db_session.get(ChatSession, session_id)
    if not chat_db:
        raise HTTPException(status_code=404, detail="Sesión no encontrada en DB")

    # 2. RECUPERAR CHECKPOINTER
    checkpointer = request.app.state.checkpointer
    if not checkpointer:
        raise HTTPException(status_code=500, detail="Checkpointer no cargado")

    # 3. COMPILAR GRAFO (Solo lectura)
    # Necesitamos el grafo compilado para poder preguntarle su estado
    agent = builder.compile(checkpointer=checkpointer)
    
    # 4. OBTENER SNAPSHOT
    config = {"configurable": {"thread_id": session_id}}
    
    # aget_state devuelve un objeto StateSnapshot
    snapshot = await agent.aget_state(config)
    
    if not snapshot.values:
        return {
            "status": "empty", 
            "message": "No hay historial para esta sesión todavía.",
            "state": {}
        }

    # 5. SERIALIZACIÓN MANUAL (Crucial)
    # LangGraph guarda objetos Python (HumanMessage, Document), 
    # FastAPI no sabe convertirlos a JSON automáticamente.
    
    raw_state = snapshot.values
    clean_state = {}

    for key, value in raw_state.items():
        # A. Si es una lista de mensajes (HumanMessage, AIMessage)
        if isinstance(value, list) and value and isinstance(value[0], BaseMessage):
            clean_state[key] = [message_to_dict(msg) for msg in value]
        
        # B. Si es una lista de Documentos (RAG)
        elif isinstance(value, list) and value and isinstance(value[0], Document):
            clean_state[key] = [
                {"page_content": doc.page_content, "metadata": doc.metadata} 
                for doc in value
            ]
            
        # C. Si es un objeto simple (str, int, dict, bool) se pasa directo
        else:
            clean_state[key] = value

    return {
        "session_id": session_id,
        "created_at": snapshot.created_at, # Fecha del último paso
        "next_step": snapshot.next,        # Qué nodo seguía (si quedó pausado)
        "state": clean_state               # <--- AQUÍ ESTÁ TODA LA DATA
    }