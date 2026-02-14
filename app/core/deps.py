from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlmodel import Session
from db import get_session
from models.user import Usuario
# Importamos la configuración desde donde la tengas (security.py o config.py)
from app.core.security import SECRET_KEY, ALGORITHM

# Esto le dice a FastAPI: "El token viene en el Header 'Authorization'"
# y "Si no hay token, manda al usuario a la ruta /token" (aunque esto es más para docs)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def get_current_user(
    token: str = Depends(oauth2_scheme), 
    session: Session = Depends(get_session)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudieron validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # --- DEBUG PRINT ---
        print(f"Token recibido: {token[:10]}...") # Imprime el inicio del token
        
        # Intentamos decodificar
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        
        # --- DEBUG PRINT ---
        print(f"Payload decodificado: {payload}")
        
        user_id: str = payload.get("sub")
        if user_id is None:
            print("ERROR: El token no tiene 'sub' (User ID)")
            raise credentials_exception
            
    except JWTError as e:
        # --- AQUÍ ESTÁ LA CLAVE ---
        print(f"ERROR JWT: {e}") # <--- ¡ESTO NOS DIRÁ QUÉ PASA!
        raise credentials_exception

    user = await session.get(Usuario, int(user_id))
    
    if user is None:
        print(f"ERROR DB: Usuario con ID {user_id} no encontrado")
        raise credentials_exception
        
    return user