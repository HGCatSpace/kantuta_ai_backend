import sys
import os

# --- AGREGA ESTO AL PRINCIPIO ---
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from sqlmodel import text
from db import engine # Importamos el motor que ya configuramos en db.py

async def test_connection():
    print("⏳ Intentando conectar a PostgreSQL...")
    
    try:
        # Intentamos obtener una conexión directa del motor
        async with engine.connect() as conn:
            # Ejecutamos una consulta SQL pura para ver si responde
            result = await conn.execute(text("SELECT version();"))
            version = result.scalar()
            
            print("\n✅ ¡CONEXIÓN EXITOSA!")
            print(f"🐘 Base de Datos: {version}")
            print("🚀 El motor de SQLModel está listo para trabajar.")
            
    except Exception as e:
        print("\n❌ ERROR DE CONEXIÓN:")
        print(f"   {e}")
        print("\n💡 SUGERENCIAS:")
        print("   1. Revisa que tu contenedor Docker esté corriendo ('docker ps').")
        print("   2. Verifica que las credenciales en '.env' coincidan con 'docker-compose.yml'.")
        print("   3. Asegúrate de tener instalado el driver: 'uv add asyncpg'.")

if __name__ == "__main__":
    # Ejecutamos la función asíncrona
    asyncio.run(test_connection())