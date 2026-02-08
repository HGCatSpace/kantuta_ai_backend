import os
from sqlmodel import SQLModel, create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

# 1. Configuración de la URL (Igual que antes)
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL no está configurada")

# 2. Crear el Motor ASÍNCRONO
engine = create_async_engine(
    DATABASE_URL,
    echo=True, # False para produccion / genera mucho ruido al buscar las tablas
    future=True
)

# 3. Función para inicializar la DB (Crear tablas)
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

# 4. Dependencia para FastAPI (Get Session)
async def get_session(): #-> AsyncSession:
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        yield session