from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Используем SQLite для локальной разработки (как указано в ТЗ)
SQLALCHEMY_DATABASE_URL = "sqlite:///./zabota.db"

# connect_args={"check_same_thread": False} нужен только для SQLite в FastAPI
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Зависимость (Dependency) для получения сессии БД в маршрутах
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
