from sqlalchemy import Column, Integer, String, Boolean, Text, Float, ForeignKey, DateTime, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from database import Base

class UserRole(enum.Enum):
    resident = "resident"
    volunteer = "volunteer"
    inspector = "inspector"
    director = "director"

class UserStatus(enum.Enum):
    pending = "pending"
    active = "active"
    blocked = "blocked"

class ApplicationStatus(enum.Enum):
    new = "new"
    needs_materials = "needs_materials" # <--- НОВЫЙ СТАТУС ДЛЯ СБОРА МАТЕРИАЛОВ
    approved = "approved"
    in_progress = "in_progress"
    review = "review"
    completed = "completed"
    rejected = "rejected"

class TaskStatus(enum.Enum):
    accepted = "accepted"
    submitted = "submitted"
    verified = "verified"
    rejected = "rejected"

class District(Base):
    __tablename__ = "districts"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), index=True)
    users = relationship("User", back_populates="district")
    applications = relationship("Application", back_populates="district")

class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    message = Column(Text)
    link = Column(String(255), nullable=True)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="notifications")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(255))
    phone = Column(String(20), unique=True, index=True)
    password_hash = Column(String(255))
    role = Column(Enum(UserRole), default=UserRole.resident)
    district_id = Column(Integer, ForeignKey("districts.id"), nullable=True)
    status = Column(Enum(UserStatus), default=UserStatus.active)
    rating = Column(Float, default=0.0)
    volunteer_hours = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    district = relationship("District", back_populates="users")
    applications = relationship("Application", back_populates="user")
    assignments = relationship("TaskAssignment", back_populates="volunteer")
    messages = relationship("TaskMessage", back_populates="sender")
    certificates = relationship("Certificate", back_populates="user")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")

class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(100))
    icon = Column(String(50))
    applications = relationship("Application", back_populates="category")

class Application(Base):
    __tablename__ = "applications"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    uin = Column(String(20), unique=True, index=True)
    applicant_name = Column(String(255))
    phone = Column(String(20))
    is_third_party = Column(Boolean, default=False)
    third_party_info = Column(Text, nullable=True)
    benefit_category = Column(String(100))
    district_id = Column(Integer, ForeignKey("districts.id"))
    address = Column(Text)
    category_id = Column(Integer, ForeignKey("categories.id"))
    description = Column(Text)
    audio_url = Column(String(255), nullable=True)
    is_emergency = Column(Boolean, default=False)
    status = Column(Enum(ApplicationStatus), default=ApplicationStatus.new)
    required_volunteers = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="applications")
    district = relationship("District", back_populates="applications")
    category = relationship("Category", back_populates="applications")
    assignments = relationship("TaskAssignment", back_populates="application")
    messages = relationship("TaskMessage", back_populates="application")

class TaskAssignment(Base):
    __tablename__ = "task_assignments"
    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("applications.id"))
    volunteer_id = Column(Integer, ForeignKey("users.id"))
    status = Column(Enum(TaskStatus), default=TaskStatus.accepted)
    photo_before_url = Column(String(255), nullable=True)
    photo_after_url = Column(String(255), nullable=True)
    volunteer_comment = Column(Text, nullable=True)
    resident_rating = Column(Integer, nullable=True)
    resident_review = Column(Text, nullable=True)
    resident_behavior_rating = Column(Integer, nullable=True) 
    assigned_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    application = relationship("Application", back_populates="assignments")
    volunteer = relationship("User", back_populates="assignments")

class TaskMessage(Base):
    __tablename__ = "task_messages"
    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("applications.id"))
    sender_id = Column(Integer, ForeignKey("users.id"))
    message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    application = relationship("Application", back_populates="messages")
    sender = relationship("User", back_populates="messages")

class Certificate(Base):
    __tablename__ = "certificates"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String(255))
    description = Column(Text)
    issued_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="certificates")