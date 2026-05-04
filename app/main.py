from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware 
from psycopg_pool import AsyncConnectionPool 
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver 
from contextlib import asynccontextmanager
from db import init_db, DATABASE_URL

# Importar routers
from app.routers import rol, action, user, caso, chat_session, agent_chat, auth, documento_comocimiento, system_prompt, knowledge_search

# Modelos para registro
from models.documentos import Documento 
from models.chat_session import ChatSession
from models.casos import Caso
from models.documento_conocimiento import DocumentoConocimiento
from models.rol import Rol
from models.system_prompt import SystemPrompt
from models.links import PromptDocumentoLink


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

# --- CONFIGURACIÓN DE CORS ---
# Esto permite que el Frontend (React) hable con el Backend
origins = [
    "http://localhost:5173", # Puerto por defecto de Vite
    "http://localhost:3000", # Puerto alternativo
    "http://127.0.0.1:5173",
    "https://nonspecifiable-asuncion-semiproductively.ngrok-free.dev",
    "https://elude-sludge-modify.ngrok-free.dev"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Intercepta el preflight de Private Network Access ANTES de que CORSMiddleware lo maneje.
# Los browsers envían Access-Control-Request-Private-Network: true cuando una página pública
# (ngrok) accede a un servidor local; el servidor debe responder con
# Access-Control-Allow-Private-Network: true en el mismo preflight OPTIONS.
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

class PrivateNetworkAccessMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Interceptar preflight de private network antes de que CORSMiddleware lo absorba
        if (
            request.method == "OPTIONS"
            and request.headers.get("Access-Control-Request-Private-Network") == "true"
        ):
            origin = request.headers.get("Origin", "")
            response = Response(
                status_code=204,
                headers={
                    "Access-Control-Allow-Origin": origin,
                    "Access-Control-Allow-Credentials": "true",
                    "Access-Control-Allow-Methods": "*",
                    "Access-Control-Allow-Headers": "*",
                    "Access-Control-Allow-Private-Network": "true",
                },
            )
            return response

        response = await call_next(request)
        response.headers["Access-Control-Allow-Private-Network"] = "true"
        return response

# PrivateNetworkAccessMiddleware se añade DESPUÉS de CORSMiddleware para que corra PRIMERO
# (Starlette aplica middleware en orden LIFO: el último añadido es el más externo)
app.add_middleware(PrivateNetworkAccessMiddleware)

# Incluir routers
app.include_router(rol.router)
app.include_router(action.router)
app.include_router(user.router) 
app.include_router(caso.router) 
app.include_router(chat_session.router) 
app.include_router(agent_chat.router)
app.include_router(auth.router)
app.include_router(documento_comocimiento.router)
app.include_router(system_prompt.router)
app.include_router(knowledge_search.router)

@app.get("/")
async def root():
    return {"message": "API Activa"}