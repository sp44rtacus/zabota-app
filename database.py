import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Получаем ссылку на базу из переменных окружения (Render сам её подставит)
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    # Исправление для Render (иногда они передают префикс postgres://, а SQLAlchemy нужен postgresql://)
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    engine = create_engine(DATABASE_URL)
else:
    # Локально на компьютере используем SQLite
    SQLALCHEMY_DATABASE_URL = "sqlite:///./zabota.db"
    engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()