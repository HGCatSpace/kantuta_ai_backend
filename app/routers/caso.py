from io import BytesIO
from typing import List, Optional
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, status, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlmodel import select, SQLModel
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session
from models.casos import Caso, CasoCreate, CasoUpdate, EstadoCaso
from models.documentos import Documento
from models.chat_session import ChatSession
from models.user import Usuario
from app.core.deps import get_current_user
from ai.agents.conversational_assistant.agent import builder as conversational_builder

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    PageBreak,
    HRFlowable,
)


# --- DTO para detalle de caso (NO toca el modelo de BD) ---
class CasoDetail(SQLModel):
    id_caso: int
    titulo: str
    descripcion: Optional[str] = None
    estado: EstadoCaso
    fecha_creacion: datetime
    fecha_actualizacion: datetime
    usuario_id: int
    total_documentos: int

router = APIRouter(
    prefix="/casos",
    tags=["Casos Legales"]
)

# --- HELPER (Reutilizamos la lógica de hora boliviana) ---
def get_bolivia_now():
    return datetime.now(ZoneInfo("America/La_Paz")).replace(tzinfo=None)

# --- 1. CREAR CASO (POST) ---
@router.post("/", response_model=Caso, status_code=status.HTTP_201_CREATED)
async def create_caso(
    caso_data: CasoCreate, 
    session: AsyncSession = Depends(get_session)
):
    """
    Crea un nuevo caso legal.
    """
    # 1. Validar que el usuario (abogado) exista
    usuario = await session.get(Usuario, caso_data.usuario_id)
    if not usuario:
        raise HTTPException(status_code=404, detail="El usuario especificado no existe")

    # 2. Crear instancia
    # Nota: Las fechas se crean solas gracias al default_factory del modelo,
    # pero si quisieras forzarlas, podrías hacerlo aquí.
    new_caso = Caso.model_validate(caso_data)
    
    try:
        session.add(new_caso)
        await session.commit()
        await session.refresh(new_caso)
        return new_caso
    except Exception as e:
        await session.rollback()
        print(f"Error creando caso: {e}")
        raise HTTPException(status_code=500, detail="Error interno al crear el caso")

# --- 2. LEER TODOS LOS CASOS (GET) ---
@router.get("/", response_model=List[Caso])
async def read_casos(
    offset: int = Query(0, description="Casos a omitir"), 
    limit: int = Query(10, description="Número de casos"), 
    session: AsyncSession = Depends(get_session),
    current_user: Usuario = Depends(get_current_user)
):
    """
    Lista todos los casos del sistema (Paginado).
    """
    statement = select(Caso).where(Caso.usuario_id == current_user.id).offset(offset).limit(limit)
    result = await session.execute(statement)
    return result.scalars().all()

# --- 2.1 ÚLTIMOS 5 CASOS MODIFICADOS (GET) ---
@router.get("/recent", response_model=List[Caso])
async def read_recent_casos(
    session: AsyncSession = Depends(get_session),
    current_user: Usuario = Depends(get_current_user)
):
    """
    Retorna los 5 casos más recientemente actualizados del usuario autenticado.
    """
    statement = select(Caso).where(Caso.usuario_id == current_user.id, Caso.estado == EstadoCaso.ABIERTO).order_by(Caso.fecha_actualizacion.desc()).limit(5)
    result = await session.execute(statement)
    return result.scalars().all()

# --- 2.2 DETALLE DE UN CASO (GET) ---
@router.get("/{id_caso}/detail", response_model=CasoDetail)
async def read_caso_detail(
    id_caso: int,
    session: AsyncSession = Depends(get_session)
):
    """
    Retorna el caso con el conteo total de documentos vinculados.
    """
    caso = await session.get(Caso, id_caso)
    if not caso:
        raise HTTPException(status_code=404, detail="Caso no encontrado")

    # Contar documentos vinculados al caso
    count_stmt = select(func.count()).select_from(Documento).where(Documento.caso_id == id_caso)
    count_result = await session.execute(count_stmt)
    total_docs = count_result.scalar_one()

    return CasoDetail(
        id_caso=caso.id_caso,
        titulo=caso.titulo,
        descripcion=caso.descripcion,
        estado=caso.estado,
        fecha_creacion=caso.fecha_creacion,
        fecha_actualizacion=caso.fecha_actualizacion,
        usuario_id=caso.usuario_id,
        total_documentos=total_docs,
    )

# --- 3. LEER CASOS POR USUARIO (GET) ---
@router.get("/usuario/{usuario_id}", response_model=List[Caso])
async def read_casos_by_user(
    usuario_id: int,
    offset: int = Query(0, description="Casos a omitir"), 
    limit: int = Query(10, description="Número de casos"), 
    session: AsyncSession = Depends(get_session)
):
    """
    Obtiene todos los casos asignados a un usuario específico.
    """

    statement = select(Usuario).where(Usuario.id == usuario_id).offset(offset).limit(limit)
    result = await session.execute(statement)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")


    statement = select(Caso).where(Caso.usuario_id == usuario_id)
    result = await session.execute(statement)
    casos = result.scalars().all()
    
    # Retornamos lista vacía si no tiene casos, no es un error 404
    return casos

# --- 4. LEER UN CASO ESPECÍFICO (GET ID) ---
@router.get("/{id_caso}", response_model=Caso)
async def read_caso(
    id_caso: int,
    session: AsyncSession = Depends(get_session)
):
    caso = await session.get(Caso, id_caso)
    if not caso:
        raise HTTPException(status_code=404, detail="Caso no encontrado")
    return caso

# --- 5. ACTUALIZAR CASO (PATCH) ---
@router.patch("/{id_caso}", response_model=Caso)
async def update_caso(
    id_caso: int,
    caso_update: CasoUpdate,
    session: AsyncSession = Depends(get_session)
):
    """
    Actualiza título, descripción o estado.
    Actualiza automáticamente la fecha_actualizacion.
    """
    # 1. Buscar
    caso_db = await session.get(Caso, id_caso)
    if not caso_db:
        raise HTTPException(status_code=404, detail="Caso no encontrado")

    # 2. Procesar datos
    update_data = caso_update.model_dump(exclude_unset=True)
    
    # 3. Forzar actualización de fecha (Hora Bolivia)
    update_data["fecha_actualizacion"] = get_bolivia_now()

    # 4. Aplicar cambios
    caso_db.sqlmodel_update(update_data)
    
    session.add(caso_db)
    await session.commit()
    await session.refresh(caso_db)
    return caso_db

# --- 5.5 EXPORTAR HISTORIAL DEL CASO A PDF ---
@router.get("/{id_caso}/exportar")
async def exportar_historial_caso(
    id_caso: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: Usuario = Depends(get_current_user),
):
    """
    Exporta el historial conversacional completo de un caso a PDF.

    Recorre todas las ChatSession del caso, recupera el estado del agente desde
    el checkpointer de LangGraph y serializa los pares pregunta-respuesta junto
    con las citas normativas extraídas del contexto RAG.
    """
    # 1. Validar caso y propiedad
    caso = await session.get(Caso, id_caso)
    if not caso:
        raise HTTPException(status_code=404, detail="Caso no encontrado")
    if caso.usuario_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a este caso.",
        )

    # 2. Sesiones de chat del caso
    stmt = (
        select(ChatSession)
        .where(ChatSession.caso_id == id_caso)
        .order_by(ChatSession.fecha_creacion.asc())
    )
    result = await session.execute(stmt)
    sesiones = result.scalars().all()

    # 3. Checkpointer + agente compilado
    checkpointer = request.app.state.checkpointer
    if not checkpointer:
        raise HTTPException(status_code=500, detail="Checkpointer no inicializado")
    agent = conversational_builder.compile(checkpointer=checkpointer)

    # 4. Recolectar conversación por sesión
    sesiones_data = []
    for sesion in sesiones:
        config = {"configurable": {"thread_id": sesion.id_session}}
        try:
            snapshot = await agent.aget_state(config)
        except Exception:
            snapshot = None

        mensajes = []
        contexto_global = []
        if snapshot and snapshot.values:
            raw_messages = snapshot.values.get("messages", [])
            raw_context = snapshot.values.get("context", [])

            # Citas normativas (source_filename + page_label) deduplicadas
            seen = set()
            for item in raw_context:
                # context puede venir como Document o (Document, score)
                doc = item[0] if isinstance(item, (list, tuple)) else item
                meta = getattr(doc, "metadata", {}) or {}
                src = meta.get("source_filename") or meta.get("source") or "fuente desconocida"
                page = meta.get("page_label") or meta.get("page", "")
                clave = (src, str(page))
                if clave in seen:
                    continue
                seen.add(clave)
                contexto_global.append({"source": src, "page": str(page)})

            # Pares Q/A
            for msg in raw_messages:
                tipo = getattr(msg, "type", None)
                contenido = getattr(msg, "content", "")
                if isinstance(contenido, list):
                    contenido = "".join(
                        c.get("text", "") if isinstance(c, dict) else str(c) for c in contenido
                    )
                if tipo in ("human", "ai"):
                    mensajes.append({"rol": tipo, "texto": str(contenido)})

        sesiones_data.append({
            "titulo": sesion.titulo,
            "fecha_creacion": sesion.fecha_creacion,
            "mensajes": mensajes,
            "citas": contexto_global,
        })

    # 5. Generar PDF en memoria
    pdf_bytes = _construir_pdf_caso(caso, sesiones_data, current_user)

    nombre_archivo = f"caso_{caso.id_caso}_historial.pdf"
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nombre_archivo}"'},
    )


def _escapar_html(texto: str) -> str:
    """Escapa caracteres conflictivos para reportlab Paragraph (mini HTML)."""
    return (
        texto.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace("\n", "<br/>")
    )


def _construir_pdf_caso(caso: Caso, sesiones_data: list, current_user: Usuario) -> bytes:
    """Arma el PDF del historial conversacional usando reportlab."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=f"Historial Caso {caso.id_caso}",
        author=f"{current_user.nombres} {current_user.apellido_paterno} {current_user.apellido_materno}",
    )

    styles = getSampleStyleSheet()
    estilo_titulo = ParagraphStyle(
        "TituloCaso", parent=styles["Title"], fontSize=18, textColor=colors.HexColor("#8B0F2C"),
        spaceAfter=14, alignment=TA_LEFT,
    )
    estilo_h2 = ParagraphStyle(
        "H2Sesion", parent=styles["Heading2"], fontSize=13, textColor=colors.HexColor("#1f2937"),
        spaceBefore=12, spaceAfter=6,
    )
    estilo_meta = ParagraphStyle(
        "Meta", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#6b7280"),
        spaceAfter=6,
    )
    estilo_pregunta = ParagraphStyle(
        "Pregunta", parent=styles["Normal"], fontSize=10, leftIndent=10,
        textColor=colors.HexColor("#0f172a"), spaceBefore=8, spaceAfter=4,
        alignment=TA_JUSTIFY,
    )
    estilo_respuesta = ParagraphStyle(
        "Respuesta", parent=styles["Normal"], fontSize=10, leftIndent=10,
        textColor=colors.HexColor("#1f2937"), spaceAfter=4, alignment=TA_JUSTIFY,
    )
    estilo_citas_titulo = ParagraphStyle(
        "CitasTitulo", parent=styles["Normal"], fontSize=10, fontName="Helvetica-Bold",
        textColor=colors.HexColor("#8B0F2C"), spaceBefore=8, spaceAfter=4,
    )
    estilo_cita = ParagraphStyle(
        "Cita", parent=styles["Normal"], fontSize=9, leftIndent=14,
        textColor=colors.HexColor("#374151"),
    )
    estilo_pie = ParagraphStyle(
        "Pie", parent=styles["Normal"], fontSize=8, alignment=TA_LEFT,
        textColor=colors.HexColor("#6b7280"),
    )

    story = []

    # ── Cabecera ──
    story.append(Paragraph(f"Caso N° {caso.id_caso}: {_escapar_html(caso.titulo)}", estilo_titulo))
    if caso.descripcion:
        story.append(Paragraph(_escapar_html(caso.descripcion), estilo_meta))
    story.append(Paragraph(
        f"Estado: <b>{caso.estado.value if hasattr(caso.estado, 'value') else caso.estado}</b> · "
        f"Creado: {caso.fecha_creacion.strftime('%d/%m/%Y %H:%M')} · "
        f"Actualizado: {caso.fecha_actualizacion.strftime('%d/%m/%Y %H:%M')}",
        estilo_meta,
    ))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e2e8f0")))
    story.append(Spacer(1, 0.3 * cm))

    # ── Sesiones ──
    if not sesiones_data:
        story.append(Paragraph("Este caso aún no tiene sesiones de chat.", estilo_meta))
    else:
        for idx, sesion in enumerate(sesiones_data, start=1):
            story.append(Paragraph(
                f"Sesión {idx} — {_escapar_html(sesion['titulo'])}",
                estilo_h2,
            ))
            story.append(Paragraph(
                f"Inicio: {sesion['fecha_creacion'].strftime('%d/%m/%Y %H:%M')}",
                estilo_meta,
            ))

            if not sesion["mensajes"]:
                story.append(Paragraph("(Sin mensajes registrados.)", estilo_meta))
            else:
                for msg in sesion["mensajes"]:
                    if msg["rol"] == "human":
                        story.append(Paragraph(
                            f"<b>Pregunta:</b> {_escapar_html(msg['texto'])}",
                            estilo_pregunta,
                        ))
                    else:
                        story.append(Paragraph(
                            f"<b>Respuesta:</b> {_escapar_html(msg['texto'])}",
                            estilo_respuesta,
                        ))

            # Citas normativas a nivel de sesión
            if sesion["citas"]:
                story.append(Paragraph("Citas normativas consultadas:", estilo_citas_titulo))
                for cita in sesion["citas"]:
                    story.append(Paragraph(
                        f"• {_escapar_html(cita['source'])} (pág. {_escapar_html(cita['page'])})",
                        estilo_cita,
                    ))

            if idx < len(sesiones_data):
                story.append(Spacer(1, 0.3 * cm))
                story.append(HRFlowable(width="100%", thickness=0.3, color=colors.HexColor("#e5e7eb")))

    # ── Pie ──
    story.append(Spacer(1, 0.6 * cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e2e8f0")))
    fecha_export = datetime.now(ZoneInfo("America/La_Paz")).strftime("%d/%m/%Y %H:%M")
    story.append(Paragraph(
        f"Exportado el {fecha_export} por {_escapar_html(f'{current_user.nombres} {current_user.apellido_paterno} {current_user.apellido_materno}')} · Kantuta AI",
        estilo_pie,
    ))

    doc.build(story)
    return buffer.getvalue()


# --- 6. BORRAR (SOFT DELETE / ARCHIVAR) ---
@router.delete("/{id_caso}", response_model=Caso)
async def archive_caso(
    id_caso: int,
    session: AsyncSession = Depends(get_session)
):
    """
    No borra el registro de la DB.
    Cambia el estado a 'ARCHIVADO' y actualiza la fecha.
    """
    caso_db = await session.get(Caso, id_caso)
    if not caso_db:
        raise HTTPException(status_code=404, detail="Caso no encontrado")

    # Lógica de Soft Delete
    caso_db.estado = EstadoCaso.ARCHIVADO
    caso_db.fecha_actualizacion = get_bolivia_now()
    
    session.add(caso_db)
    await session.commit()
    await session.refresh(caso_db)
    
    return caso_db