"""
Router del módulo de Informes y Reportes.

Expone GET /reportes/actividad con métricas globales del sistema,
gated por la acción 'ver_reporte_actividad' (asignada al rol Administrador).
"""
from datetime import datetime, timedelta
from typing import List
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from app.core.deps import get_current_user
from db import get_session
from models.casos import Caso
from models.chat_session import ChatSession
from models.documento_conocimiento import DocumentoConocimiento
from models.rol import Rol
from models.user import Usuario

router = APIRouter(prefix="/reportes", tags=["Reportes"])

ACCION_REPORTE = "Informes y reportes"


def bolivia_now() -> datetime:
    return datetime.now(ZoneInfo("America/La_Paz")).replace(tzinfo=None)


# ──────────────── Schemas (DTOs) ────────────────

class CategoriaConteo(BaseModel):
    categoria: str
    total: int


class ReporteActividadSchema(BaseModel):
    usuarios_por_rol: List[CategoriaConteo]
    casos_por_estado: List[CategoriaConteo]
    documentos_por_estado: List[CategoriaConteo]
    sesiones_chat_7d: int
    mensajes_humanos_30d: int
    generado_en: datetime


# ──────────────── Helpers ────────────────

async def _verificar_permiso(session: AsyncSession, current_user: Usuario) -> None:
    """Lanza 403 si el usuario no tiene la acción 'ver_reporte_actividad'."""
    statement = (
        select(Usuario)
        .where(Usuario.id == current_user.id)
        .options(selectinload(Usuario.actions))
    )
    result = await session.execute(statement)
    user_loaded = result.scalar_one()

    nombres_acciones = {a.nombre for a in user_loaded.actions}
    if ACCION_REPORTE not in nombres_acciones:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Tu rol no tiene la acción '{ACCION_REPORTE}'.",
        )


def _enum_value(value) -> str:
    """Convierte un valor (Enum o str) en string para serializar."""
    return value.value if hasattr(value, "value") else str(value)


# ──────────────── Endpoint ────────────────

@router.get("/actividad", response_model=ReporteActividadSchema)
async def get_reporte_actividad(
    session: AsyncSession = Depends(get_session),
    current_user: Usuario = Depends(get_current_user),
):
    """
    Reporte global de actividad del sistema.

    Solo accesible para usuarios con la acción 'ver_reporte_actividad'
    (rol Administrador por defecto). Devuelve métricas para el módulo
    de Informes y Reportes del frontend.
    """
    await _verificar_permiso(session, current_user)

    ahora = bolivia_now()
    hace_7d = ahora - timedelta(days=7)
    hace_30d = ahora - timedelta(days=30)

    # 1. Usuarios agrupados por rol (usamos LEFT OUTER JOIN por si hay usuarios sin rol)
    stmt_usuarios = (
        select(Rol.nombre, func.count(Usuario.id))
        .select_from(Usuario)
        .join(Rol, Usuario.id_rol == Rol.id_rol, isouter=True)
        .group_by(Rol.nombre)
    )
    result = await session.execute(stmt_usuarios)
    usuarios_por_rol = [
        CategoriaConteo(categoria=row[0] or "Sin rol", total=row[1])
        for row in result.all()
    ]

    # 2. Casos agrupados por estado
    stmt_casos = (
        select(Caso.estado, func.count(Caso.id_caso))
        .group_by(Caso.estado)
    )
    result = await session.execute(stmt_casos)
    casos_por_estado = [
        CategoriaConteo(categoria=_enum_value(row[0]), total=row[1])
        for row in result.all()
    ]

    # 3. Documentos por estado de indexación
    stmt_docs = (
        select(
            DocumentoConocimiento.estado_indexacion,
            func.count(DocumentoConocimiento.id_documento),
        )
        .group_by(DocumentoConocimiento.estado_indexacion)
    )
    result = await session.execute(stmt_docs)
    documentos_por_estado = [
        CategoriaConteo(categoria=_enum_value(row[0]), total=row[1])
        for row in result.all()
    ]

    # 4. Sesiones de chat creadas en los últimos 7 días
    stmt_sesiones = (
        select(func.count(ChatSession.id_session))
        .where(ChatSession.fecha_creacion >= hace_7d)
    )
    result = await session.execute(stmt_sesiones)
    sesiones_chat_7d = result.scalar_one() or 0

    # 5. Proxy de mensajes humanos en los últimos 30 días.
    # El conteo exacto vive en checkpoints de LangGraph (esquema interno).
    # Usamos como proxy: sesiones con actividad reciente (ultimo_acceso >= hace 30 días).
    stmt_msg = (
        select(func.count(ChatSession.id_session))
        .where(ChatSession.ultimo_acceso >= hace_30d)
    )
    result = await session.execute(stmt_msg)
    mensajes_humanos_30d = result.scalar_one() or 0

    return ReporteActividadSchema(
        usuarios_por_rol=usuarios_por_rol,
        casos_por_estado=casos_por_estado,
        documentos_por_estado=documentos_por_estado,
        sesiones_chat_7d=sesiones_chat_7d,
        mensajes_humanos_30d=mensajes_humanos_30d,
        generado_en=ahora,
    )
