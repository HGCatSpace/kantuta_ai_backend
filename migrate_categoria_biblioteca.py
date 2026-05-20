"""
Migración: Cambiar EnumCategoriaBiblioteca al nuevo taxonomía del proyecto.

ANTES (valores almacenados como nombres en PostgreSQL):
  CONTRATOS, LITIGIOS, CORPORATIVO, LABORAL, OTROS

DESPUÉS:
  NORMATIVA_SUSTANTIVA, NORMATIVA_ADJETIVA, NORMATIVA_GENERAL, MATERIAL_REFERENCIA

Estrategia segura:
  1. Convertir columna `categoria` a TEXT (rompe dependencia con el enum viejo).
  2. UPDATE: mapear todos los valores viejos → MATERIAL_REFERENCIA
     (fallback neutro; usuario reclasificará vía UI cuando corresponda).
  3. DROP TYPE enumcategoriabiblioteca.
  4. CREATE TYPE con los 4 valores nuevos.
  5. ALTER COLUMN categoria al tipo nuevo + restaurar default.

Uso: uv run python migrate_categoria_biblioteca.py
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

ENUM_NAME = "enumcategoriabiblioteca"
TABLE = "documentos_conocimiento"
COLUMN = "categoria"

OLD_NAMES = {"CONTRATOS", "LITIGIOS", "CORPORATIVO", "LABORAL", "OTROS"}
NEW_NAMES = [
    "NORMATIVA_SUSTANTIVA",
    "NORMATIVA_ADJETIVA",
    "NORMATIVA_GENERAL",
    "MATERIAL_REFERENCIA",
]
FALLBACK = "MATERIAL_REFERENCIA"


async def _enum_labels(conn) -> set[str]:
    r = await conn.execute(text(
        "SELECT e.enumlabel FROM pg_type t "
        "JOIN pg_enum e ON t.oid = e.enumtypid "
        "WHERE t.typname = :name"
    ), {"name": ENUM_NAME})
    return {row[0] for row in r.fetchall()}


async def migrate() -> None:
    async with engine.begin() as conn:
        labels = await _enum_labels(conn)
        if not labels:
            print(f"⚠️  No se encontró el tipo enum '{ENUM_NAME}'. ¿Tabla recién creada?")
            return

        if labels == set(NEW_NAMES):
            print("Migración ya aplicada (los valores del enum coinciden con la nueva taxonomía).")
            return

        print(f"[1/5] Convirtiendo {TABLE}.{COLUMN} a TEXT temporalmente...")
        await conn.execute(text(
            f"ALTER TABLE {TABLE} ALTER COLUMN {COLUMN} DROP DEFAULT"
        ))
        await conn.execute(text(
            f"ALTER TABLE {TABLE} ALTER COLUMN {COLUMN} TYPE TEXT "
            f"USING {COLUMN}::TEXT"
        ))

        print(f"[2/5] Mapeando valores antiguos → '{FALLBACK}'...")
        r = await conn.execute(text(
            f"UPDATE {TABLE} SET {COLUMN} = :new "
            f"WHERE {COLUMN} = ANY(:olds)"
        ), {"new": FALLBACK, "olds": list(OLD_NAMES)})
        print(f"   Filas actualizadas: {r.rowcount}")

        # Cualquier otro valor extraño que haya quedado, también al fallback
        r2 = await conn.execute(text(
            f"UPDATE {TABLE} SET {COLUMN} = :new "
            f"WHERE {COLUMN} IS NOT NULL "
            f"AND {COLUMN} <> ALL(:news)"
        ), {"new": FALLBACK, "news": NEW_NAMES})
        if r2.rowcount:
            print(f"   Valores fuera de taxonomía mapeados al fallback: {r2.rowcount}")

        print(f"[3/5] DROP TYPE {ENUM_NAME}...")
        await conn.execute(text(f"DROP TYPE {ENUM_NAME}"))

        print(f"[4/5] CREATE TYPE {ENUM_NAME} con nuevos valores...")
        values_sql = ", ".join(f"'{n}'" for n in NEW_NAMES)
        await conn.execute(text(f"CREATE TYPE {ENUM_NAME} AS ENUM ({values_sql})"))

        print(f"[5/5] Restaurando {COLUMN} al tipo enum + default...")
        await conn.execute(text(
            f"ALTER TABLE {TABLE} ALTER COLUMN {COLUMN} TYPE {ENUM_NAME} "
            f"USING {COLUMN}::{ENUM_NAME}"
        ))
        await conn.execute(text(
            f"ALTER TABLE {TABLE} ALTER COLUMN {COLUMN} "
            f"SET DEFAULT '{FALLBACK}'::{ENUM_NAME}"
        ))

        # Verificación
        new_labels = await _enum_labels(conn)
        print(f"✅ Migración completa. Nuevos valores del enum: {sorted(new_labels)}")


if __name__ == "__main__":
    asyncio.run(migrate())
