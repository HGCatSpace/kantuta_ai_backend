"""
Migración: Atomizar nombre_completo → nombres, apellido_paterno, apellido_materno

Divide el campo único 'nombre_completo' de la tabla 'usuarios' en tres campos
atómicos, distribuyendo las palabras del nombre así:
  - Si hay 3+ palabras: primera(s) → nombres, penúltima → apellido_paterno, última → apellido_materno
  - Si hay 2 palabras: primera → nombres, segunda → apellido_paterno, apellido_materno = '-'
  - Si hay 1 palabra:  esa palabra → nombres, apellido_paterno = '-', apellido_materno = '-'

Uso: python migrate_nombre_completo.py
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


async def migrate():
    async with engine.begin() as conn:
        # 1. Verificar que la columna nombre_completo todavía existe
        result = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'usuarios' AND column_name = 'nombre_completo'"
        ))
        if not result.fetchone():
            print("La columna 'nombre_completo' ya no existe. La migración ya fue aplicada.")
            return

        # 2. Agregar las nuevas columnas (permitiendo NULL temporalmente)
        print("[1/4] Agregando columnas nuevas...")
        for col in ("nombres", "apellido_paterno", "apellido_materno"):
            # Verificar si ya existe (ejecución parcial previa)
            exists = await conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'usuarios' AND column_name = :col"
            ), {"col": col})
            if not exists.fetchone():
                await conn.execute(text(f"ALTER TABLE usuarios ADD COLUMN {col} VARCHAR"))
                print(f"  + columna '{col}' agregada")
            else:
                print(f"  ~ columna '{col}' ya existe, omitiendo")

        # 3. Migrar datos: dividir nombre_completo en los 3 campos
        print("[2/4] Migrando datos existentes...")
        rows = await conn.execute(text("SELECT id, nombre_completo FROM usuarios"))
        count = 0
        for row in rows.fetchall():
            user_id, nombre_completo = row
            parts = (nombre_completo or "").strip().split()

            if len(parts) >= 3:
                # Ej: "Juan Carlos Pérez Mamani" → nombres="Juan Carlos", ap="Pérez", am="Mamani"
                nombres = " ".join(parts[:-2])
                apellido_paterno = parts[-2]
                apellido_materno = parts[-1]
            elif len(parts) == 2:
                nombres = parts[0]
                apellido_paterno = parts[1]
                apellido_materno = "-"
            elif len(parts) == 1:
                nombres = parts[0]
                apellido_paterno = "-"
                apellido_materno = "-"
            else:
                nombres = "-"
                apellido_paterno = "-"
                apellido_materno = "-"

            await conn.execute(text(
                "UPDATE usuarios SET nombres = :n, apellido_paterno = :ap, apellido_materno = :am "
                "WHERE id = :id"
            ), {"n": nombres, "ap": apellido_paterno, "am": apellido_materno, "id": user_id})
            count += 1

        print(f"  {count} usuario(s) migrado(s)")

        # 4. Hacer las columnas NOT NULL
        print("[3/4] Aplicando restricciones NOT NULL...")
        for col in ("nombres", "apellido_paterno", "apellido_materno"):
            await conn.execute(text(
                f"ALTER TABLE usuarios ALTER COLUMN {col} SET NOT NULL"
            ))

        # 5. Eliminar la columna vieja
        print("[4/4] Eliminando columna 'nombre_completo'...")
        await conn.execute(text("ALTER TABLE usuarios DROP COLUMN nombre_completo"))

    print("\n✅ Migración completada exitosamente.")


if __name__ == "__main__":
    asyncio.run(migrate())
