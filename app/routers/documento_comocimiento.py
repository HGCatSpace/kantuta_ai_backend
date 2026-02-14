import os
import shutil
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, status, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlmodel import select, col
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from db import get_session
from models.user import Usuario
from models.documento_conocimiento import (
    DocumentoConocimiento,
    DocumentoConocimientoUpdate,
    DocumentoConocimientoPublic,
    EnumCategoriaBiblioteca,
    EnumIconoArchivo,
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
    categoria: EnumCategoriaBiblioteca = Form(EnumCategoriaBiblioteca.OTROS),
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

    # 3. Crear registro en BD
    new_doc = DocumentoConocimiento(
        titulo=titulo,
        categoria=categoria,
        icono=icono,
        descripcion=descripcion or None,
        etiquetas=etiquetas or None,
        ruta=str(file_path),
        nombre_archivo=original_name,
        usuario_id=current_user.id,
    )

    try:
        session.add(new_doc)
        await session.commit()
        await session.refresh(new_doc)
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
        filename=doc.nombre_archivo or file_path.name,
        media_type="application/octet-stream",
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

    # Eliminar archivo físico
    file_path = Path(doc_db.ruta)
    if file_path.exists():
        file_path.unlink()

    await session.delete(doc_db)
    await session.commit()
    return None
