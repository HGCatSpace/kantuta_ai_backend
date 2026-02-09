from fastapi import FastAPI
from psycopg_pool import AsyncConnectionPool 
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver 
from contextlib import asynccontextmanager
from db import init_db, DATABASE_URL

# Importar routers
from app.routers import rol, action, user, caso, chat_session, agent_chat

# Modelos para registro
from models.documentos import Documento 
from models.chat_session import ChatSession
from models.casos import Caso

DB_URI_LANGGRAPH = DATABASE_URL.replace("+asyncpg", "")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Iniciar DB SQLModel
    print("🔄 Iniciando base de datos...")
    await init_db()

    # 2. Configurar el Checkpointer (ANTES del yield)
    print("🧠 Conectando memoria de LangGraph...")
    
    # Mantenemos el pool abierto MIENTRAS la app vive
    async with AsyncConnectionPool(
        conninfo=DB_URI_LANGGRAPH,
        max_size=20,
        kwargs={"autocommit": True}
    ) as pool:
        checkpointer = AsyncPostgresSaver(pool)
        
        # Crear tablas internas si no existen
        await checkpointer.setup()
        
        # Guardar en el estado para usarlo en los endpoints
        app.state.checkpointer = checkpointer
        
        print("✅ Sistema listo. Checkpointer cargado.")
        
        # --- AQUÍ EMPIEZA A CORRER TU APP ---
        yield 
        # --- AQUÍ TERMINA TU APP (Shutdown) ---
        
        print("🛑 Cerrando conexiones...")

app = FastAPI(lifespan=lifespan, title="Kantuta AI API")

# Incluir routers
app.include_router(rol.router)
app.include_router(action.router)
# app.include_router(action.router) <--- Tenías duplicada esta línea, borrada.
app.include_router(user.router) 
app.include_router(caso.router) 
app.include_router(chat_session.router) 
app.include_router(agent_chat.router)

@app.get("/")
async def root():
    return {"message": "API Activa"}