from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, Request
from sqlalchemy.orm import Session
from database import get_db
import models

# Секретный ключ для подписи токенов (в реальных проектах его прячут в .env файл)
SECRET_KEY = "super_secret_zabota_key_2026"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # Токен живет 7 дней

# Настройка алгоритма хеширования паролей (bcrypt)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    """Проверяет, совпадает ли введенный пароль с хешем из БД"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    """Превращает пароль в нечитаемый хеш"""
    return pwd_context.hash(password)

def create_access_token(data: dict):
    """Создает JWT-токен для пользователя"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(request: Request, db: Session = Depends(get_db)):
    """
    Зависимость. Вытаскивает токен из куки браузера, расшифровывает его
    и возвращает объект пользователя из БД. Если не авторизован - вернет None.
    """
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        # Убираем приставку "Bearer ", если она есть
        if token.startswith("Bearer "):
            token = token.split(" ")[1]
            
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            return None
    except JWTError:
        return None
        
    user = db.query(models.User).filter(models.User.id == int(user_id)).first()
    return user