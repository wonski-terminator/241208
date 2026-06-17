# auth_azure.py — wersja Azure z JWT_SECRET_KEY z env
import os
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from models_azure import get_db, User

SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "fallback-tylko-dev-nie-uzywac-na-produkcji")
ALGORITHM  = "HS256"
TOKEN_EXPIRE_MINUTES = 60

pwd_context   = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_token(user: User) -> str:
    payload = {
        "sub":       str(user.user_id),
        "username":  user.username,
        "tenant_id": user.tenant_id,
        "role":      user.role,
        "exp":       datetime.utcnow() + timedelta(minutes=TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

class TokenData:
    def __init__(self, user_id, tenant_id, role, username):
        self.user_id = user_id; self.tenant_id = tenant_id
        self.role = role; self.username = username

def decode_token(token: str) -> TokenData:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return TokenData(int(payload["sub"]), payload["tenant_id"], payload["role"], payload["username"])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token", headers={"WWW-Authenticate": "Bearer"})

def get_current_user(token: str = Depends(oauth2_scheme)) -> TokenData:
    return decode_token(token)

def require_admin(current_user: TokenData = Depends(get_current_user)) -> TokenData:
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return current_user

def require_fan(current_user: TokenData = Depends(get_current_user)) -> TokenData:
    return current_user
