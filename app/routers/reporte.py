"""
Router del módulo de Informes y Reportes.

Expone GET /reportes/actividad con métricas globales del sistema,
gated por la acción 'ver_reporte_actividad' (asignada al rol Administrador).
"""
from datetime import datetime, timedelta
from typing import List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, distinct
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from app.core.deps import get_current_user
from db import get_session
from models.casos import Caso, EstadoCaso
from models.chat_session import ChatSession
from models.documento_conocimiento import DocumentoConocimiento, EnumEstadoIndexacion
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


class ItemConteo(BaseModel):
    nombre: str
    total: int


class CasoInactivoItem(BaseModel):
    id_caso: int
    titulo: str
    dias_inactivo: int
    ultima_actividad: Optional[datetime] = None


class ReporteActividadSchema(BaseModel):
    usuarios_por_rol: List[CategoriaConteo]
    casos_por_estado: List[CategoriaConteo]
    documentos_por_estado: List[CategoriaConteo]
    sesiones_chat_7d: int
    mensajes_humanos_30d: int
    # ── Comparativos del rango actual vs rango anterior (misma duración) ──
    casos_creados: int
    casos_creados_anterior: int
    sesiones_chat_creadas: int
    sesiones_chat_creadas_anterior: int
    usuarios_activos: int
    usuarios_activos_anterior: int
    documentos_subidos: int
    documentos_subidos_anterior: int
    # ── KPIs derivados del rango ──
    promedio_chats_por_caso: float
    tasa_exito_ingesta: float  # 0–100
    # ── Rankings del rango ──
    casos_por_usuario: List[ItemConteo]
    chats_por_caso: List[ItemConteo]
    chats_por_usuario: List[ItemConteo]
    # ── Casos abandonados (no depende del rango) ──
    casos_sin_actividad: List[CasoInactivoItem]
    dias_inactividad_umbral: int
    # ── Rango aplicado ──
    desde: datetime
    hasta: datetime
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
    desde: datetime | None = Query(None, description="Inicio del rango (ISO 8601)"),
    hasta: datetime | None = Query(None, description="Fin del rango (ISO 8601)"),
    dias_inactividad: int = Query(14, ge=1, le=365, description="Umbral en días para considerar un caso abierto como abandonado"),
    session: AsyncSession = Depends(get_session),
    current_user: Usuario = Depends(get_current_user),
):
    """
    Reporte global de actividad del sistema.

    Acepta parámetros opcionales `desde` y `hasta` para filtrar las métricas
    comparativas. Por defecto: últimos 7 días.
    """
    await _verificar_permiso(session, current_user)

    ahora = bolivia_now()

    # Rango por defecto: últimos 7 días
    if hasta is None:
        hasta = ahora
    if desde is None:
        desde = hasta - timedelta(days=7)

    duracion_rango = hasta - desde
    periodo_anterior_desde = desde - duracion_rango
    periodo_anterior_hasta = desde

    hace_7d = ahora - timedelta(days=7)
    hace_30d = ahora - timedelta(days=30)

    # ── Métricas globales (sin filtro de fecha) ──

    # 1. Usuarios agrupados por rol
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

    # 4. Sesiones de chat en los últimos 7 días
    stmt_sesiones = (
        select(func.count(ChatSession.id_session))
        .where(ChatSession.fecha_creacion >= hace_7d)
    )
    result = await session.execute(stmt_sesiones)
    sesiones_chat_7d = result.scalar_one() or 0

    # 5. Proxy de mensajes humanos en los últimos 30 días
    stmt_msg = (
        select(func.count(ChatSession.id_session))
        .where(ChatSession.ultimo_acceso >= hace_30d)
    )
    result = await session.execute(stmt_msg)
    mensajes_humanos_30d = result.scalar_one() or 0

    # ── Métricas comparativas (filtradas por rango desde/hasta) ──

    # Helper: cuenta filas dentro de un rango sobre un campo de fecha
    async def _count_in_range(modelo, campo_fecha, ini, fin) -> int:
        r = await session.execute(
            select(func.count()).select_from(modelo).where(campo_fecha >= ini, campo_fecha < fin)
        )
        return r.scalar_one() or 0

    # 6. Casos creados
    casos_creados = await _count_in_range(Caso, Caso.fecha_creacion, desde, hasta)
    casos_creados_anterior = await _count_in_range(
        Caso, Caso.fecha_creacion, periodo_anterior_desde, periodo_anterior_hasta
    )

    # 7. Sesiones de chat creadas
    sesiones_chat_creadas = await _count_in_range(
        ChatSession, ChatSession.fecha_creacion, desde, hasta
    )
    sesiones_chat_creadas_anterior = await _count_in_range(
        ChatSession, ChatSession.fecha_creacion, periodo_anterior_desde, periodo_anterior_hasta
    )

    # 8. Usuarios activos (distinct: que crearon caso o chat dentro del rango)
    async def _usuarios_activos(ini, fin) -> int:
        r1 = await session.execute(
            select(distinct(Caso.usuario_id))
            .where(Caso.fecha_creacion >= ini, Caso.fecha_creacion < fin)
        )
        ids_casos = {row[0] for row in r1.all()}

        r2 = await session.execute(
            select(distinct(Caso.usuario_id))
            .join(ChatSession, ChatSession.caso_id == Caso.id_caso)
            .where(ChatSession.fecha_creacion >= ini, ChatSession.fecha_creacion < fin)
        )
        ids_chats = {row[0] for row in r2.all()}

        return len(ids_casos | ids_chats)

    usuarios_activos = await _usuarios_activos(desde, hasta)
    usuarios_activos_anterior = await _usuarios_activos(
        periodo_anterior_desde, periodo_anterior_hasta
    )

    # 9. Documentos subidos a la Base de Conocimiento
    documentos_subidos = await _count_in_range(
        DocumentoConocimiento, DocumentoConocimiento.fecha_creacion, desde, hasta
    )
    documentos_subidos_anterior = await _count_in_range(
        DocumentoConocimiento,
        DocumentoConocimiento.fecha_creacion,
        periodo_anterior_desde,
        periodo_anterior_hasta,
    )

    # 10. Promedio de chats por caso (sobre casos que tuvieron al menos un chat en el rango)
    result = await session.execute(
        select(ChatSession.caso_id, func.count(ChatSession.id_session))
        .where(ChatSession.fecha_creacion >= desde, ChatSession.fecha_creacion <= hasta)
        .group_by(ChatSession.caso_id)
    )
    filas_chat_caso = result.all()
    total_chats_rango = sum(r[1] for r in filas_chat_caso)
    casos_con_chats = len(filas_chat_caso)
    promedio_chats_por_caso = (
        round(total_chats_rango / casos_con_chats, 2) if casos_con_chats > 0 else 0.0
    )

    # 11. Tasa de éxito de ingesta (% docs COMPLETADO del total subido en el rango)
    result = await session.execute(
        select(
            DocumentoConocimiento.estado_indexacion,
            func.count(DocumentoConocimiento.id_documento),
        )
        .where(
            DocumentoConocimiento.fecha_creacion >= desde,
            DocumentoConocimiento.fecha_creacion <= hasta,
        )
        .group_by(DocumentoConocimiento.estado_indexacion)
    )
    counts_estado = {_enum_value(row[0]): row[1] for row in result.all()}
    total_docs_rango = sum(counts_estado.values())
    docs_completados = counts_estado.get("COMPLETADO", 0)
    tasa_exito_ingesta = (
        round((docs_completados / total_docs_rango) * 100, 1) if total_docs_rango > 0 else 0.0
    )

    # 12. Casos por usuario en el rango
    stmt_casos_usuario = (
        select(Usuario.nombres, Usuario.apellido_paterno, func.count(Caso.id_caso))
        .join(Caso, Caso.usuario_id == Usuario.id)
        .where(Caso.fecha_creacion >= desde, Caso.fecha_creacion <= hasta)
        .group_by(Usuario.id, Usuario.nombres, Usuario.apellido_paterno)
        .order_by(func.count(Caso.id_caso).desc())
    )
    result = await session.execute(stmt_casos_usuario)
    casos_por_usuario = [
        ItemConteo(nombre=f"{row[0]} {row[1]}", total=row[2])
        for row in result.all()
    ]

    # 13. Chats por caso en el rango
    stmt_chats_caso = (
        select(Caso.titulo, func.count(ChatSession.id_session))
        .join(ChatSession, ChatSession.caso_id == Caso.id_caso)
        .where(ChatSession.fecha_creacion >= desde, ChatSession.fecha_creacion <= hasta)
        .group_by(Caso.id_caso, Caso.titulo)
        .order_by(func.count(ChatSession.id_session).desc())
    )
    result = await session.execute(stmt_chats_caso)
    chats_por_caso = [
        ItemConteo(nombre=row[0], total=row[1])
        for row in result.all()
    ]

    # 14. Chats por usuario en el rango
    stmt_chats_usuario = (
        select(Usuario.nombres, Usuario.apellido_paterno, func.count(ChatSession.id_session))
        .join(Caso, Caso.usuario_id == Usuario.id)
        .join(ChatSession, ChatSession.caso_id == Caso.id_caso)
        .where(ChatSession.fecha_creacion >= desde, ChatSession.fecha_creacion <= hasta)
        .group_by(Usuario.id, Usuario.nombres, Usuario.apellido_paterno)
        .order_by(func.count(ChatSession.id_session).desc())
    )
    result = await session.execute(stmt_chats_usuario)
    chats_por_usuario = [
        ItemConteo(nombre=f"{row[0]} {row[1]}", total=row[2])
        for row in result.all()
    ]

    # 15. Casos abandonados: ABIERTOS cuya última actividad (chat o caso) está por debajo del umbral
    umbral = ahora - timedelta(days=dias_inactividad)
    ult_actividad = func.coalesce(
        func.max(ChatSession.ultimo_acceso), Caso.fecha_actualizacion
    ).label("ult_actividad")
    stmt_inactivos = (
        select(Caso.id_caso, Caso.titulo, ult_actividad)
        .outerjoin(ChatSession, ChatSession.caso_id == Caso.id_caso)
        .where(Caso.estado == EstadoCaso.ABIERTO)
        .group_by(Caso.id_caso, Caso.titulo, Caso.fecha_actualizacion)
        .having(
            func.coalesce(
                func.max(ChatSession.ultimo_acceso), Caso.fecha_actualizacion
            )
            < umbral
        )
        .order_by(ult_actividad.asc())
        .limit(10)
    )
    result = await session.execute(stmt_inactivos)
    casos_sin_actividad = [
        CasoInactivoItem(
            id_caso=row[0],
            titulo=row[1],
            ultima_actividad=row[2],
            dias_inactivo=(ahora - row[2]).days if row[2] else dias_inactividad,
        )
        for row in result.all()
    ]

    return ReporteActividadSchema(
        usuarios_por_rol=usuarios_por_rol,
        casos_por_estado=casos_por_estado,
        documentos_por_estado=documentos_por_estado,
        sesiones_chat_7d=sesiones_chat_7d,
        mensajes_humanos_30d=mensajes_humanos_30d,
        casos_creados=casos_creados,
        casos_creados_anterior=casos_creados_anterior,
        sesiones_chat_creadas=sesiones_chat_creadas,
        sesiones_chat_creadas_anterior=sesiones_chat_creadas_anterior,
        usuarios_activos=usuarios_activos,
        usuarios_activos_anterior=usuarios_activos_anterior,
        documentos_subidos=documentos_subidos,
        documentos_subidos_anterior=documentos_subidos_anterior,
        promedio_chats_por_caso=promedio_chats_por_caso,
        tasa_exito_ingesta=tasa_exito_ingesta,
        casos_por_usuario=casos_por_usuario,
        chats_por_caso=chats_por_caso,
        chats_por_usuario=chats_por_usuario,
        casos_sin_actividad=casos_sin_actividad,
        dias_inactividad_umbral=dias_inactividad,
        desde=desde,
        hasta=hasta,
        generado_en=ahora,
    )
