"""DTOs (Schemas) del dominio de usuarios."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class DocumentoRecienteSchema(BaseModel):
    """Resumen de un documento de conocimiento para el dashboard del usuario."""
    id_documento: int
    titulo: str
    categoria: str
    fecha_creacion: datetime


class UserDashboardSchema(BaseModel):
    """Payload del endpoint GET /users/dashboard."""
    id: int
    nombre_completo: str
    email: str
    rol: Optional[str] = None
    casos_activos: int = 0
    documentos_recientes: List[DocumentoRecienteSchema] = []
    sesiones_chat_30d: int = 0
    ultimo_acceso: datetime
