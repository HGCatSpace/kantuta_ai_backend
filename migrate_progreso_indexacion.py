"""
Migración: Agregar columnas chunks_procesados y chunks_totales a documentos_conocimiento

Permite reportar el progreso de embedding (chunks procesados / chunks totales) en
tiempo real durante la ingesta de documentos. Ambas columnas son nullable: los
documentos existentes quedan con NULL y la UI los trata como sin progreso reportado.

Uso: uv run python migrate_progreso_indexacion.py
"""
import asyncio
import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL no está configurada en .env")

engine = create_async_engine(DATABASE_URL, echo=False)

TABLE = "documentos_conocimiento"
NEW_COLUMNS = ("chunks_procesados", "chunks_totales")


async def migrate():
    async with engine.begin() as conn:
        # Verificar qué columnas faltan
        result = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            f"WHERE table_name = '{TABLE}' "
            f"AND column_name = ANY(:cols)"
        ), {"cols": list(NEW_COLUMNS)})
        existing = {row[0] for row in result.fetchall()}

        to_add = [c for c in NEW_COLUMNS if c not in existing]
        if not to_add:
            print(f"Ambas columnas {NEW_COLUMNS} ya existen. Migración no necesaria.")
            return

        for col in to_add:
            print(f"[+] Agregando columna '{col}' a {TABLE}...")
            await conn.execute(text(
                f"ALTER TABLE {TABLE} ADD COLUMN {col} INTEGER"
            ))

        print(f"OK. Columnas agregadas: {to_add}")


if __name__ == "__main__":
    asyncio.run(migrate())
