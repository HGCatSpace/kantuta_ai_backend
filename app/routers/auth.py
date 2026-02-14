from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import select, Session
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session
from models.user import Usuario # Asegúrate de importar tu modelo Usuario
from app.core.security import verify_password, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES

router = APIRouter(tags=["Autenticación"])

@router.post("/token")
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_session)
):
    """
    Endpoint de Login.
    Recibe: username, password (en form-data)
    Retorna: access_token (JWT)
    """
    
    # 1. Buscar al usuario en la DB (por email O nombre de usuario)
    # Nota: OAuth2 siempre envía el campo como 'username', aunque sea un email
    statement = select(Usuario).where(
        (Usuario.email == form_data.username) |
        (Usuario.nombre_de_usuario == form_data.username)
    ).options(
        selectinload(Usuario.rol),
        selectinload(Usuario.actions)
    )
    result = await session.execute(statement)
    user = result.scalar_one_or_none()

    # 2. Verificar si existe y si la contraseña coincide
    if not user or not verify_password(form_data.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas (Usuario o contraseña inválidos)",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if user.activo == "inactive":
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail="Usuario inactivo"
        )

    # 3. Generar el Token JWT
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id), "rol": user.id_rol}, # Guardamos ID y Rol en el token
        expires_delta=access_token_expires
    )

    # 4. Retornar el token al Frontend
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_data": {
            "nombre": user.nombre_completo,
            "email": user.email,
            "rol_nombre": user.rol.nombre if user.rol else None,
            "activo": user.activo,
            "actions": [a.nombre for a in user.actions]
        }
    }