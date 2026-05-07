"""
Script de seed para poblar la base de datos con datos iniciales:
  - 3 Roles: Usuario, Experto, Administrador
  - 5 Acciones del sistema
  - 1 Usuario de prueba por cada rol con sus acciones asignadas

Uso: python seed.py
"""
import asyncio
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select
import os
from dotenv import load_dotenv

load_dotenv()

# Importar modelos (necesarios para que SQLModel registre las tablas)
from models.rol import Rol
from models.action import Action
from models.user import Usuario
from models.links import UsuarioActionLink
import models.casos                    # noqa: F401 - necesario para crear tablas
import models.documentos               # noqa: F401
import models.documento_conocimiento   # noqa: F401
import models.system_prompt            # noqa: F401
import models.chat_session             # noqa: F401

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL no está configurada en .env")

engine = create_async_engine(DATABASE_URL, echo=False, future=True)
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


# ──────────────────────────────────────────────
# DATOS A INSERTAR
# ──────────────────────────────────────────────

ROLES = [
    {"nombre": "Usuario",        "description": "Acceso a biblioteca, consulta y gestión de casos."},
    {"nombre": "Experto",        "description": "Gestión de prompts y base de conocimiento, más permisos de Usuario."},
    {"nombre": "Administrador",  "description": "Acceso completo a todas las funcionalidades del sistema."},
]

ACTIONS = [
    {"nombre": "Gestión de casos",                                   "descripcion": "Crear, editar y gestionar casos legales."},
    {"nombre": "Biblioteca y consulta",                              "descripcion": "Acceso a la biblioteca de documentos y consultas."},
    {"nombre": "Gestión de prompts",                                 "descripcion": "Crear y administrar prompts del sistema."},
    {"nombre": "Gestión de documentos para la base de conocimiento", "descripcion": "Subir y administrar documentos en la base de conocimiento."},
    {"nombre": "Gestión de usuarios",                                "descripcion": "Administrar usuarios del sistema."},
    {"nombre": "Informes y reportes",                                "descripcion": "Consultar el reporte global de actividad del sistema."},
]

# Acciones por rol (usando los nombres definidos arriba)
ROLE_ACTIONS = {
    "Usuario": [
        "Gestión de casos",
        "Biblioteca y consulta",
    ],
    "Experto": [
        "Gestión de casos",
        "Biblioteca y consulta",
        "Gestión de prompts",
        "Gestión de documentos para la base de conocimiento",
    ],
    "Administrador": [
        "Gestión de casos",
        "Biblioteca y consulta",
        "Gestión de prompts",
        "Gestión de documentos para la base de conocimiento",
        "Gestión de usuarios",
        "Informes y reportes",
    ],
}

# Usuarios de prueba: uno por rol
USERS = [
    {
        "nombre_de_usuario": "usuario_test",
        "email":             "usuario@kantuta.test",
        "nombre_completo":   "Usuario de Prueba",
        "password":          "usuario123",
        "rol_nombre":        "Usuario",
    },
    {
        "nombre_de_usuario": "experto_test",
        "email":             "experto@kantuta.test",
        "nombre_completo":   "Experto de Prueba",
        "password":          "experto123",
        "rol_nombre":        "Experto",
    },
    {
        "nombre_de_usuario": "admin_test",
        "email":             "admin@kantuta.test",
        "nombre_completo":   "Administrador de Prueba",
        "password":          "admin123",
        "rol_nombre":        "Administrador",
    },
]


# ──────────────────────────────────────────────
# LÓGICA DEL SEED
# ──────────────────────────────────────────────

async def seed():
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Crear tablas si no existen
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with async_session() as session:

        # ── 0. Migración inline: renombrar acciones antiguas ──
        # 'ver_reporte_actividad' (snake_case) → 'Informes y reportes'
        result = await session.execute(
            select(Action).where(Action.nombre == "ver_reporte_actividad")
        )
        legacy_action = result.scalar_one_or_none()
        if legacy_action:
            # Borrar links de usuarios a la acción antigua (se reasignarán en paso 4)
            await session.execute(
                UsuarioActionLink.__table__.delete().where(
                    UsuarioActionLink.action_id == legacy_action.id_action
                )
            )
            await session.delete(legacy_action)
            await session.commit()
            print("  🔄 Acción legacy 'ver_reporte_actividad' eliminada (será reemplazada por 'Informes y reportes').")

        # ── 1. Roles ──────────────────────────────
        print("\n[1/4] Creando roles...")
        rol_map: dict[str, Rol] = {}
        for r in ROLES:
            result = await session.execute(select(Rol).where(Rol.nombre == r["nombre"]))
            existing = result.scalar_one_or_none()
            if existing:
                print(f"  ⚠  Rol '{r['nombre']}' ya existe, omitiendo.")
                rol_map[r["nombre"]] = existing
            else:
                new_rol = Rol(nombre=r["nombre"], description=r["description"])
                session.add(new_rol)
                await session.flush()   # obtener id antes del commit
                rol_map[r["nombre"]] = new_rol
                print(f"  ✓  Rol '{r['nombre']}' creado (id={new_rol.id_rol}).")
        await session.commit()

        # ── 2. Acciones ───────────────────────────
        print("\n[2/4] Creando acciones...")
        action_map: dict[str, Action] = {}
        for a in ACTIONS:
            result = await session.execute(select(Action).where(Action.nombre == a["nombre"]))
            existing = result.scalar_one_or_none()
            if existing:
                print(f"  ⚠  Acción '{a['nombre']}' ya existe, omitiendo.")
                action_map[a["nombre"]] = existing
            else:
                new_action = Action(nombre=a["nombre"], descripcion=a["descripcion"])
                session.add(new_action)
                await session.flush()
                action_map[a["nombre"]] = new_action
                print(f"  ✓  Acción '{a['nombre']}' creada (id={new_action.id_action}).")
        await session.commit()

        # ── 3. Usuarios ───────────────────────────
        print("\n[3/4] Creando usuarios...")
        user_map: dict[str, Usuario] = {}
        for u in USERS:
            result = await session.execute(
                select(Usuario).where(Usuario.nombre_de_usuario == u["nombre_de_usuario"])
            )
            existing = result.scalar_one_or_none()
            if existing:
                print(f"  ⚠  Usuario '{u['nombre_de_usuario']}' ya existe, omitiendo.")
                user_map[u["nombre_de_usuario"]] = existing
            else:
                rol = rol_map[u["rol_nombre"]]
                new_user = Usuario(
                    nombre_de_usuario=u["nombre_de_usuario"],
                    email=u["email"],
                    nombre_completo=u["nombre_completo"],
                    password=hash_password(u["password"]),
                    id_rol=rol.id_rol,
                )
                session.add(new_user)
                await session.flush()
                user_map[u["nombre_de_usuario"]] = new_user
                print(f"  ✓  Usuario '{u['nombre_de_usuario']}' creado (id={new_user.id}, rol={u['rol_nombre']}).")
        await session.commit()

        # ── 4. Asignar acciones a usuarios ────────
        print("\n[4/4] Asignando acciones a usuarios...")
        for u in USERS:
            user = user_map[u["nombre_de_usuario"]]
            actions_for_role = ROLE_ACTIONS[u["rol_nombre"]]
            for action_name in actions_for_role:
                action = action_map[action_name]
                result = await session.execute(
                    select(UsuarioActionLink).where(
                        UsuarioActionLink.usuario_id == user.id,
                        UsuarioActionLink.action_id == action.id_action,
                    )
                )
                if result.first():
                    print(f"  ⚠  '{u['nombre_de_usuario']}' → '{action_name}' ya asignado.")
                else:
                    link = UsuarioActionLink(usuario_id=user.id, action_id=action.id_action)
                    session.add(link)
                    print(f"  ✓  '{u['nombre_de_usuario']}' → '{action_name}'")
        await session.commit()

    print("\n✅ Seed completado con éxito.\n")
    print("Credenciales de prueba:")
    print("  usuario_test   / usuario123  (Rol: Usuario)")
    print("  experto_test   / experto123  (Rol: Experto)")
    print("  admin_test     / admin123    (Rol: Administrador)")


if __name__ == "__main__":
    asyncio.run(seed())
