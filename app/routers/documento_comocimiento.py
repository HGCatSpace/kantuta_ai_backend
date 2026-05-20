import os
import shutil
import asyncio
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, status, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlmodel import select, col
from sqlalchemy.orm import selectinload, sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from db import get_session, engine
from models.user import Usuario
from models.documento_conocimiento import (
    DocumentoConocimiento,
    DocumentoConocimientoUpdate,
    DocumentoConocimientoPublic,
    EnumCategoriaBiblioteca,
    EnumIconoArchivo,
    EnumEstadoIndexacion,
    bolivia_now,
)

# Directorio de almacenamiento de archivos
UPLOAD_DIR = Path(__file__).resolve().parents[2] / "data" / "loaded"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter(
    prefix="/conocimiento",
    tags=["Biblioteca de Conocimiento"]
)


def _detect_icono(filename: str) -> EnumIconoArchivo:
    """Detecta el tipo de icono basado en la extensión del archivo."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == "pdf":
        return EnumIconoArchivo.PDF
    if ext in ("doc", "docx"):
        return EnumIconoArchivo.DOC
    return EnumIconoArchivo.OTHER


# ==========================================
# 1. UPLOAD (POST) — Archivo + metadatos
# ==========================================
@router.post("/", response_model=DocumentoConocimientoPublic, status_code=status.HTTP_201_CREATED)
async def create_documento(
    archivo: UploadFile = File(...),
    titulo: str = Form(...),
    categoria: EnumCategoriaBiblioteca = Form(EnumCategoriaBiblioteca.MATERIAL_REFERENCIA),
    descripcion: Optional[str] = Form(None),
    etiquetas: Optional[str] = Form(None),
    session: AsyncSession = Depends(get_session),
    current_user: Usuario = Depends(get_current_user),
):
    """Sube un archivo y crea el registro en la base de datos."""

    # 1. Guardar archivo en disco
    original_name = archivo.filename or "sin_nombre"
    safe_name = f"{int(bolivia_now().timestamp())}_{original_name}"
    file_path = UPLOAD_DIR / safe_name

    try:
        with open(file_path, "wb") as f:
            shutil.copyfileobj(archivo.file, f)
    finally:
        await archivo.close()

    # 2. Detectar icono por extensión
    icono = _detect_icono(original_name)

    # 3. Crear registro en BD (estado = PROCESANDO)
    new_doc = DocumentoConocimiento(
        titulo=titulo,
        categoria=categoria,
        icono=icono,
        descripcion=descripcion or None,
        etiquetas=etiquetas or None,
        ruta=str(file_path),
        nombre_archivo=original_name,
        usuario_id=current_user.id,
        estado_indexacion=EnumEstadoIndexacion.PROCESANDO,
    )

    try:
        session.add(new_doc)
        await session.commit()
        await session.refresh(new_doc)

        # 4. Ingestar en ChromaDB (background para no bloquear la respuesta)
        from app.services.ingestion import ingest_file

        extra_meta = {
            "titulo": titulo,
            "categoria": str(categoria.value) if categoria else "Otros",
            "documento_id": new_doc.id_documento,
        }

        doc_id = new_doc.id_documento

        async def _run_ingest():
            """Background task: ingesta + actualización de estado y progreso."""
            async_session = sessionmaker(
                engine, class_=AsyncSession, expire_on_commit=False
            )
            async with async_session() as bg_session:

                async def _update_progress(procesados: int, totales: int) -> None:
                    """Persiste el progreso de embeddings en la BD."""
                    doc_db = await bg_session.get(DocumentoConocimiento, doc_id)
                    if doc_db:
                        doc_db.chunks_procesados = procesados
                        doc_db.chunks_totales = totales
                        bg_session.add(doc_db)
                        await bg_session.commit()

                try:
                    count = await ingest_file(
                        str(file_path),
                        original_name,
                        extra_meta,
                        progress_callback=_update_progress,
                    )
                    print(f"✅ [UPLOAD] {count} chunks indexados para '{original_name}'")
                    # Marcar como COMPLETADO
                    doc_db = await bg_session.get(DocumentoConocimiento, doc_id)
                    if doc_db:
                        doc_db.estado_indexacion = EnumEstadoIndexacion.COMPLETADO
                        # Asegurar que el progreso quede en 100%
                        if doc_db.chunks_totales:
                            doc_db.chunks_procesados = doc_db.chunks_totales
                        bg_session.add(doc_db)
                        await bg_session.commit()
                except Exception as ie:
                    print(f"⚠️ [UPLOAD] Error indexando '{original_name}': {ie}")
                    # Marcar como ERROR
                    try:
                        doc_db = await bg_session.get(DocumentoConocimiento, doc_id)
                        if doc_db:
                            doc_db.estado_indexacion = EnumEstadoIndexacion.ERROR
                            bg_session.add(doc_db)
                            await bg_session.commit()
                    except Exception:
                        pass

        asyncio.create_task(_run_ingest())

        return new_doc
    except Exception as e:
        # Limpiar archivo si falla el guardado en BD
        if file_path.exists():
            file_path.unlink()
        await session.rollback()
        raise HTTPException(status_code=400, detail=f"Error creando documento: {str(e)}")


# ==========================================
# 2. READ ALL (GET) - Con Filtros
# ==========================================
@router.get("/", response_model=List[DocumentoConocimientoPublic])
async def read_documentos(
    offset: int = Query(0, ge=0),
    limit: int = Query(10),
    search: Optional[str] = Query(None, description="Búsqueda por título, descripción o etiquetas"),
    categoria: Optional[EnumCategoriaBiblioteca] = Query(None, description="Filtrar por categoría"),
    session: AsyncSession = Depends(get_session),
):
    query = select(DocumentoConocimiento)

    if search:
        query = query.where(
            (col(DocumentoConocimiento.titulo).ilike(f"%{search}%")) |
            (col(DocumentoConocimiento.descripcion).ilike(f"%{search}%")) |
            (col(DocumentoConocimiento.etiquetas).ilike(f"%{search}%"))
        )

    if categoria:
        query = query.where(DocumentoConocimiento.categoria == categoria)

    query = query.order_by(DocumentoConocimiento.fecha_creacion.desc())
    query = query.offset(offset).limit(limit)

    result = await session.execute(query)
    docs = result.scalars().all()

    return docs


# ==========================================
# 2b. COUNT (GET) - Para paginación
# ==========================================
@router.get("/count")
async def count_documentos(
    search: Optional[str] = Query(None, description="Búsqueda por título, descripción o etiquetas"),
    categoria: Optional[EnumCategoriaBiblioteca] = Query(None, description="Filtrar por categoría"),
    session: AsyncSession = Depends(get_session),
    current_user: Usuario = Depends(get_current_user),
):
    from sqlalchemy import func
    query = select(func.count()).select_from(DocumentoConocimiento)

    if search:
        query = query.where(
            (col(DocumentoConocimiento.titulo).ilike(f"%{search}%")) |
            (col(DocumentoConocimiento.descripcion).ilike(f"%{search}%")) |
            (col(DocumentoConocimiento.etiquetas).ilike(f"%{search}%"))
        )

    if categoria:
        query = query.where(DocumentoConocimiento.categoria == categoria)

    result = await session.execute(query)
    total = result.scalar_one()
    return {"total": total}


# ==========================================
# 3. READ ONE (GET by ID)
# ==========================================
@router.get("/{doc_id}", response_model=DocumentoConocimientoPublic)
async def read_documento(
    doc_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: Usuario = Depends(get_current_user),
):
    doc = await session.get(DocumentoConocimiento, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    return doc


# ==========================================
# 3b. DOWNLOAD (GET archivo)
# ==========================================
@router.get("/{doc_id}/download")
async def download_documento(
    doc_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: Usuario = Depends(get_current_user),
):
    doc = await session.get(DocumentoConocimiento, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    file_path = Path(doc.ruta)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Archivo no encontrado en el servidor")

    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
    )


# ==========================================
# 4. UPDATE (PATCH)
# ==========================================
@router.patch("/{doc_id}", response_model=DocumentoConocimientoPublic)
async def update_documento(
    doc_id: int,
    doc_update: DocumentoConocimientoUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: Usuario = Depends(get_current_user),
):
    doc_db = await session.get(DocumentoConocimiento, doc_id)
    if not doc_db:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    update_data = doc_update.model_dump(exclude_unset=True)
    update_data["ultima_modificacion"] = bolivia_now()

    doc_db.sqlmodel_update(update_data)

    session.add(doc_db)
    await session.commit()
    await session.refresh(doc_db)
    return doc_db


# ==========================================
# 5. DELETE (Eliminación permanente + archivo)
# ==========================================
@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_documento(
    doc_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: Usuario = Depends(get_current_user),
):
    doc_db = await session.get(DocumentoConocimiento, doc_id)
    if not doc_db:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    # Eliminar chunks de ChromaDB
    source_filename = doc_db.ruta
    if source_filename:
        from app.services.ingestion import delete_file_chunks
        try:
            deleted = await delete_file_chunks(source_filename)
            print(f"🗑️  [DELETE] {deleted} chunks eliminados de ChromaDB para '{source_filename}'")
        except Exception as e:
            print(f"⚠️ [DELETE] Error eliminando chunks: {e}")

    # Eliminar archivo físico
    file_path = Path(doc_db.ruta)
    if file_path.exists():
        file_path.unlink()
        print(f"🗑️  [DELETE] Archivo eliminado: {file_path}")

    await session.delete(doc_db)
    await session.commit()
    return None
