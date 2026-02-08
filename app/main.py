from fastapi import FastAPI
from contextlib import asynccontextmanager
from db import init_db
# 1. Importar el router
from app.routers import rol, action, user


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(lifespan=lifespan, title="Kantuta AI API")

# 2. Incluir el router en la app
app.include_router(rol.router)
app.include_router(action.router)
app.include_router(action.router)
app.include_router(user.router) 

@app.get("/")
async def root():
    return {"message": "API Activa"}