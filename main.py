import os, uuid, shutil, random
from fastapi import FastAPI, Request, Depends, Form, UploadFile, File, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import engine, SessionLocal, get_db
import models, auth

os.makedirs("static/audio", exist_ok=True)
os.makedirs("static/photos", exist_ok=True)

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="АИС Забота", version="1.0.0")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- Инициализация стартовых данных с защитой от сбоев ---
@app.on_event("startup")
def startup_event():
    # Удаляем поврежденную базу при каждом холодном старте на Render, 
    # чтобы таблица всегда создавалась с актуальной структурой
    # (для реальных проектов используют Alembic, но для облачного демо это идеальное решение)
    db_path = "zabota.db"
    
    db = SessionLocal()
    try:
        # Проверяем, созданы ли таблицы
        if not db.query(models.District).first():
            districts = ["Центр", "Южный", "Восток", "Горный", "Спутник", "МЖК", "Правый берег", "ЛДО", "ПДО", "Вавилинский затон", "Сукпак", "Каа-Хем", "Другое (указать вручную)"]
            for d in districts: db.add(models.District(name=d))
                
        if not db.query(models.Category).first():
            categories = [("Уборка снега / двора", "snowflake"), ("Доставка продуктов / лекарств", "basket"), ("Мелкий бытовой ремонт", "wrench"), ("Колка дров / Переноска угля", "fire"), ("Сопровождение в больницу", "truck-medical"), ("Помощь с документами", "file-signature"), ("Социальное общение", "mug-hot"), ("Другое (описать)", "circle-question")]
            for title, icon in categories: db.add(models.Category(title=title, icon=icon))
                
        if not db.query(models.User).filter(models.User.phone == "+79991234567").first():
            db.add(models.User(full_name="Иванов Иван (Волонтер)", phone="+79991234567", password_hash=auth.get_password_hash("12345"), role=models.UserRole.volunteer, district_id=1, status=models.UserStatus.active))
            db.add(models.User(full_name="Смирнова Анна (Инспектор)", phone="+70000000000", password_hash=auth.get_password_hash("admin"), role=models.UserRole.inspector, status=models.UserStatus.active))
            db.add(models.User(full_name="Петров Петр (Житель)", phone="+71111111111", password_hash=auth.get_password_hash("11111"), role=models.UserRole.resident, status=models.UserStatus.active))
        db.commit()
    except Exception as e:
        print(f"Ошибка инициализации БД (пересоздаем): {e}")
        db.rollback()
        # Если структура поменялась кардинально, сбрасываем файл базы
        db.close()
        if os.path.exists(db_path):
            os.remove(db_path)
        models.Base.metadata.create_all(bind=engine)
        startup_event() # Рекурсивно заполняем заново
        return
    finally:
        db.close()

# --- СИСТЕМА УВЕДОМЛЕНИЙ (НОВОЕ) ---
@app.get("/api/notifications")
async def get_notifications(db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    if not user: return {"notifications": [], "unread_count": 0}
    nots = db.query(models.Notification).filter(models.Notification.user_id == user.id).order_by(models.Notification.created_at.desc()).limit(15).all()
    unread = sum(1 for n in nots if not n.is_read)
    return {
        "unread_count": unread,
        "notifications": [{"id": n.id, "message": n.message, "link": n.link, "is_read": n.is_read, "time": n.created_at.strftime("%H:%M")} for n in nots]
    }

@app.post("/api/notifications/read")
async def read_notifications(db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    if user:
        db.query(models.Notification).filter(models.Notification.user_id == user.id, models.Notification.is_read == False).update({"is_read": True})
        db.commit()
    return {"status": "success"}

# --- ФАЙЛЫ ДЛЯ МОБИЛЬНОГО ПРИЛОЖЕНИЯ (PWA) ---
@app.get("/sw.js")
async def get_sw():
    return FileResponse("static/sw.js", media_type="application/javascript")

@app.get("/manifest.json")
async def get_manifest():
    return FileResponse("static/manifest.json", media_type="application/json")

# --- ПУБЛИЧНЫЕ РОУТЫ ---
@app.get("/")
async def home(request: Request, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    top_volunteers = db.query(models.User).filter(models.User.role == models.UserRole.volunteer, models.User.status == models.UserStatus.active, models.User.volunteer_hours > 0).order_by(models.User.volunteer_hours.desc(), models.User.rating.desc()).limit(5).all()
    stats = {"completed": db.query(models.Application).filter(models.Application.status == models.ApplicationStatus.completed).count(), "volunteers": db.query(models.User).filter(models.User.role == models.UserRole.volunteer, models.User.status == models.UserStatus.active).count()}
    # Получаем заявки, ожидающие материалы
    materials_apps = db.query(models.Application).filter(models.Application.status == models.ApplicationStatus.needs_materials).all()
    
    return templates.TemplateResponse("index.html", {"request": request, "user": user, "top_volunteers": top_volunteers, "stats": stats, "materials_apps": materials_apps})
    
    # Статистика для главной страницы
    stats = {
        "completed": db.query(models.Application).filter(models.Application.status == models.ApplicationStatus.completed).count(),
        "volunteers": db.query(models.User).filter(models.User.role == models.UserRole.volunteer, models.User.status == models.UserStatus.active).count()
    }
    
    return templates.TemplateResponse("index.html", {
        "request": request, "user": user, "top_volunteers": top_volunteers, "stats": stats
    })

@app.get("/request/new")
async def new_request_page(request: Request, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    if not user or user.role.name != 'resident': return RedirectResponse(url="/login")
    return templates.TemplateResponse("new_request.html", {"request": request, "districts": db.query(models.District).all(), "categories": db.query(models.Category).all(), "user": user})

@app.post("/request/new")
async def create_request(
    applicant_name: str = Form(...), phone: str = Form(...), is_third_party: bool = Form(False), third_party_info: str = Form(""), benefit_category: str = Form(...), district_id: int = Form(...), address: str = Form(...), category_id: int = Form(...), description: str = Form(...), custom_district: str = Form(""), custom_category: str = Form(""), is_emergency: bool = Form(False), audio: UploadFile = File(None), db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)
):
    if not user or user.role.name != 'resident': return {"status": "error"}
    audio_url = None
    if audio and audio.filename:
        filename = f"{uuid.uuid4()}.{audio.filename.split('.')[-1] if '.' in audio.filename else 'webm'}"
        filepath = f"static/audio/{filename}"
        with open(filepath, "wb") as buffer: shutil.copyfileobj(audio.file, buffer)
        audio_url = f"/{filepath}"

    final_address = f"[{custom_district}] {address}" if custom_district else address
    final_description = f"Категория: {custom_category}\n\n{description}" if custom_category else description

    uin = f"KZ-2026-{random.randint(1000, 9999)}"
    new_app = models.Application(
        user_id=user.id, uin=uin, applicant_name=applicant_name, phone=phone, is_third_party=is_third_party,
        third_party_info=third_party_info, benefit_category=benefit_category, district_id=district_id,
        address=final_address, category_id=category_id, description=final_description, 
        audio_url=audio_url, is_emergency=is_emergency, status=models.ApplicationStatus.new
    )
    db.add(new_app)
    
    # Уведомляем инспекторов о новой заявке
    inspectors = db.query(models.User).filter(models.User.role.in_([models.UserRole.inspector, models.UserRole.director])).all()
    for insp in inspectors:
        db.add(models.Notification(user_id=insp.id, message=f"Новая заявка {uin} ожидает модерации!", link="/admin/dashboard"))
        
    db.commit()
    return {"status": "success", "uin": uin}

# --- АВТОРИЗАЦИЯ И РЕГИСТРАЦИЯ ---
@app.get("/register")
async def register_page(request: Request, user: models.User = Depends(auth.get_current_user)):
    return templates.TemplateResponse("register.html", {"request": request, "user": user})

@app.post("/register")
async def register_action(request: Request, full_name: str = Form(...), phone: str = Form(...), password: str = Form(...), role_type: str = Form(...), db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.phone == phone).first():
        return templates.TemplateResponse("register.html", {"request": request, "error": "Номер уже зарегистрирован"})
    user_role = models.UserRole.resident if role_type == "resident" else models.UserRole.volunteer
    user_status = models.UserStatus.active if role_type == "resident" else models.UserStatus.pending
    db.add(models.User(full_name=full_name, phone=phone, password_hash=auth.get_password_hash(password), role=user_role, status=user_status))
    db.commit()
    return RedirectResponse(url="/login?registered=1", status_code=status.HTTP_302_FOUND)

@app.get("/login")
async def login_page(request: Request, user: models.User = Depends(auth.get_current_user)):
    return templates.TemplateResponse("login.html", {"request": request, "user": user})

@app.post("/login")
async def login_action(request: Request, phone: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.phone == phone).first()
    if not user or not auth.verify_password(password, user.password_hash):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Неверный логин или пароль"})
    access_token = auth.create_access_token(data={"sub": str(user.id)})
    url = "/admin/dashboard" if user.role.name in ['inspector', 'director'] else ("/resident/dashboard" if user.role.name == 'resident' else "/volunteer/feed")
    response = RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="access_token", value=f"Bearer {access_token}", httponly=True, max_age=auth.ACCESS_TOKEN_EXPIRE_MINUTES * 60, samesite="lax")
    return response

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.delete_cookie("access_token")
    return response

# --- ЗОНА ВОЛОНТЕРА ---
@app.get("/volunteer/feed")
async def volunteer_feed(request: Request, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    if not user or user.role.name != 'volunteer': return RedirectResponse(url="/login")
    if user.status.name == 'pending': return templates.TemplateResponse("volunteer_feed.html", {"request": request, "tasks": [], "active_assignments": [], "user": user, "is_pending": True})
    tasks = db.query(models.Application).filter(models.Application.status == models.ApplicationStatus.approved).order_by(models.Application.is_emergency.desc(), models.Application.created_at.desc()).all()
    active_assignments = db.query(models.TaskAssignment).filter(models.TaskAssignment.volunteer_id == user.id, models.TaskAssignment.status.in_([models.TaskStatus.accepted, models.TaskStatus.rejected])).all()
    return templates.TemplateResponse("volunteer_feed.html", {"request": request, "tasks": tasks, "active_assignments": active_assignments, "districts": db.query(models.District).all(), "user": user, "is_pending": False})

@app.post("/volunteer/api/task/{app_id}/take")
async def take_task(app_id: int, request: Request, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    if not user or user.role.name != 'volunteer' or user.status.name != 'active': return {"status": "error"}
    app_obj = db.query(models.Application).filter(models.Application.id == app_id).first()
    if app_obj and app_obj.status == models.ApplicationStatus.approved:
        app_obj.status = models.ApplicationStatus.in_progress
        db.add(models.TaskAssignment(application_id=app_obj.id, volunteer_id=user.id, status=models.TaskStatus.accepted))
        # Уведомление жителю
        db.add(models.Notification(user_id=app_obj.user_id, message=f"Волонтер взял вашу заявку {app_obj.uin} в работу!", link="/resident/dashboard"))
        db.commit()
        return {"status": "success", "redirect_url": f"/volunteer/task/{app_obj.id}"}
    return {"status": "error"}

@app.post("/volunteer/api/task/{app_id}/sos")
async def trigger_sos(app_id: int, request: Request, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    """Обработка экстренного сигнала SOS от волонтера"""
    if not user or user.role.name != 'volunteer': return {"status": "error"}
    
    app_obj = db.query(models.Application).filter(models.Application.id == app_id).first()
    if not app_obj: return {"status": "error"}
    
    # 1. Отправляем красное системное сообщение прямо в чат
    db.add(models.TaskMessage(
        application_id=app_id, sender_id=user.id, 
        message=f"🆘 [ЭКСТРЕННЫЙ ВЫЗОВ SOS] Волонтер {user.full_name} сообщает об опасности по адресу: {app_obj.address}! Требуется немедленная связь или вызов полиции!"
    ))
    
    # 2. Отправляем Push-уведомление (Toast) всем Инспекторам
    inspectors = db.query(models.User).filter(models.User.role.in_([models.UserRole.inspector, models.UserRole.director])).all()
    for insp in inspectors:
        db.add(models.Notification(
            user_id=insp.id, 
            message=f"🚨 SOS! Волонтер в опасности на задаче {app_obj.uin}!", 
            link=f"/admin/chat/{app_id}"
        ))
        
    db.commit()
    return {"status": "success"}

@app.get("/volunteer/task/{app_id}")
async def volunteer_task_page(app_id: int, request: Request, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    if not user or user.role.name != 'volunteer': return RedirectResponse(url="/login")
    app_obj = db.query(models.Application).filter(models.Application.id == app_id).first()
    return templates.TemplateResponse("volunteer_task.html", {"request": request, "app": app_obj, "user": user})

@app.post("/volunteer/api/task/{app_id}/report")
async def submit_task_report(
    app_id: int, 
    volunteer_comment: str = Form(""), 
    resident_behavior_rating: int = Form(5), # <-- Новое поле оценки
    photo_before: UploadFile = File(None), 
    photo_after: UploadFile = File(...), 
    db: Session = Depends(get_db), 
    user: models.User = Depends(auth.get_current_user)
):
    if not user or user.role.name != 'volunteer': return {"status": "error"}
    assignment = db.query(models.TaskAssignment).filter(models.TaskAssignment.application_id == app_id, models.TaskAssignment.volunteer_id == user.id, models.TaskAssignment.status.in_([models.TaskStatus.accepted, models.TaskStatus.rejected])).first()
    if not assignment: return {"status": "error", "message": "Назначение не найдено"}
    
    def save_photo(upload_file):
        if upload_file and upload_file.filename:
            filepath = f"static/photos/photo_{uuid.uuid4()}.{upload_file.filename.split('.')[-1]}"
            with open(filepath, "wb") as b: shutil.copyfileobj(upload_file.file, b)
            return f"/{filepath}"
        return None
        
    assignment.photo_before_url = save_photo(photo_before)
    assignment.photo_after_url = save_photo(photo_after)
    assignment.volunteer_comment = volunteer_comment
    assignment.resident_behavior_rating = resident_behavior_rating # <-- Сохраняем скрытую оценку
    assignment.status = models.TaskStatus.submitted
    
    app_obj = db.query(models.Application).filter(models.Application.id == app_id).first()
    app_obj.status = models.ApplicationStatus.review
    
    inspectors = db.query(models.User).filter(models.User.role.in_([models.UserRole.inspector, models.UserRole.director])).all()
    for insp in inspectors:
        db.add(models.Notification(user_id=insp.id, message=f"Загружен фотоотчет по заявке {app_obj.uin}. Требуется проверка.", link=f"/admin/verify/{app_obj.id}"))
        
    db.commit()
    return {"status": "success"}

@app.get("/volunteer/profile")
async def volunteer_profile(request: Request, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    if not user or user.role.name != 'volunteer': return RedirectResponse(url="/login")
    completed = db.query(models.TaskAssignment).filter(models.TaskAssignment.volunteer_id == user.id, models.TaskAssignment.status == models.TaskStatus.verified).all()
    return templates.TemplateResponse("volunteer_profile.html", {"request": request, "volunteer": user, "completed": completed, "user": user})

# --- ЗОНА ЖИТЕЛЯ ---
@app.get("/resident/dashboard")
async def resident_dashboard(request: Request, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    if not user or user.role.name != 'resident': return RedirectResponse(url="/login")
    applications = db.query(models.Application).filter(models.Application.user_id == user.id).order_by(models.Application.created_at.desc()).all()
    return templates.TemplateResponse("resident_dashboard.html", {"request": request, "user": user, "applications": applications})

@app.post("/resident/api/review/{assignment_id}")
async def submit_resident_review(assignment_id: int, request: Request, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    if not user or user.role.name != 'resident': return {"status": "error"}
    data = await request.json()
    assignment = db.query(models.TaskAssignment).filter(models.TaskAssignment.id == assignment_id).first()
    if assignment and assignment.application.user_id == user.id:
        assignment.resident_rating = int(data.get("rating", 5))
        assignment.resident_review = data.get("review", "")
        volunteer = assignment.volunteer
        all_reviews = db.query(models.TaskAssignment).filter(models.TaskAssignment.volunteer_id == volunteer.id, models.TaskAssignment.resident_rating.isnot(None)).all()
        volunteer.rating = round(sum(r.resident_rating for r in all_reviews) / len(all_reviews), 1) if all_reviews else 5.0
        
        # Уведомление волонтеру об отзыве
        db.add(models.Notification(user_id=volunteer.id, message=f"Вы получили новый отзыв ({assignment.resident_rating} звезд)!", link="/volunteer/profile"))
        db.commit()
        return {"status": "success"}
    return {"status": "error"}

# --- ЗОНА ИНСПЕКТОРА ---
@app.get("/admin/dashboard")
async def admin_dashboard(request: Request, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    if not user or user.role.name not in ['inspector', 'director']: 
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    try:
        total_apps_count = db.query(models.Application).count()
        all_apps = db.query(models.Application).all()

        kanban_data = {"new": [], "needs_materials": [], "approved": [], "in_progress": [], "review": [], "completed": [], "rejected": []}
        
        for app_obj in all_apps:
            st = app_obj.status
            status_str = st.name if hasattr(st, 'name') else str(st.value if hasattr(st, 'value') else st)
            if status_str in kanban_data:
                kanban_data[status_str].append(app_obj)
            else:
                kanban_data["new"].append(app_obj)
                
        return templates.TemplateResponse("admin_dashboard.html", {
            "request": request, "kanban": kanban_data, "user": user, "total_apps_count": total_apps_count
        })
    except Exception as e:
        print(f"Ошибка Канбан-доски: {e}")
        kanban_data = {"new": [], "needs_materials": [], "approved": [], "in_progress": [], "review": [], "completed": [], "rejected": []}
        return templates.TemplateResponse("admin_dashboard.html", {
            "request": request, "kanban": kanban_data, "user": user, "total_apps_count": 0
        })

# НОВОЕ: Страница чата для жителя (Вставь прямо сюда)
@app.get("/resident/chat/{app_id}")
async def resident_chat_page(app_id: int, request: Request, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    if not user or user.role.name != 'resident': return RedirectResponse(url="/login")
    app_obj = db.query(models.Application).filter(models.Application.id == app_id, models.Application.user_id == user.id).first()
    if not app_obj: return RedirectResponse(url="/resident/dashboard")
    return templates.TemplateResponse("resident_chat.html", {"request": request, "app": app_obj, "user": user})

@app.post("/admin/api/application/{app_id}/moderate")

@app.get("/admin/verify/{app_id}")
async def verify_report_page(app_id: int, request: Request, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    if not user or user.role.name not in ['inspector', 'director']: return RedirectResponse(url="/login")
    app_obj = db.query(models.Application).filter(models.Application.id == app_id).first()
    assignment = db.query(models.TaskAssignment).filter(models.TaskAssignment.application_id == app_id, models.TaskAssignment.status == models.TaskStatus.submitted).first()
    return templates.TemplateResponse("admin_verify.html", {"request": request, "app": app_obj, "assignment": assignment, "user": user})

@app.post("/admin/api/verify/{app_id}")
async def verify_report_action(app_id: int, request: Request, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    if not user or user.role.name not in ['inspector', 'director']: return {"status": "error"}
    data = await request.json()
    action, reason = data.get("action"), data.get("reason", "")
    app_obj = db.query(models.Application).filter(models.Application.id == app_id).first()
    assignment = db.query(models.TaskAssignment).filter(models.TaskAssignment.application_id == app_id, models.TaskAssignment.status == models.TaskStatus.submitted).first()
    
    if action == "approve":
        app_obj.status = models.ApplicationStatus.completed
        assignment.status = models.TaskStatus.verified
        volunteer = db.query(models.User).filter(models.User.id == assignment.volunteer_id).first()
        if volunteer:
            volunteer.volunteer_hours += 2
            volunteer.rating += 5.0
        db.add(models.Notification(user_id=app_obj.user_id, message=f"Заявка {app_obj.uin} выполнена! Оставьте отзыв волонтеру.", link="/resident/dashboard"))
        db.add(models.Notification(user_id=assignment.volunteer_id, message=f"Отчет по {app_obj.uin} утвержден! Начислено 2 часа.", link="/volunteer/profile"))
    elif action == "reject":
        app_obj.status = models.ApplicationStatus.in_progress
        assignment.status = models.TaskStatus.rejected
        db.add(models.TaskMessage(application_id=app_id, sender_id=user.id, message=f"🔴 [СИСТЕМНОЕ СООБЩЕНИЕ] Отчет не принят. Доработка!\nКомментарий: {reason}"))
        db.add(models.Notification(user_id=assignment.volunteer_id, message=f"Отчет по {app_obj.uin} отправлен на доработку!", link=f"/volunteer/task/{app_id}"))
    db.commit()
    return {"status": "success"}

@app.get("/admin/volunteers")
async def admin_volunteers_page(request: Request, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    if not user or user.role.name not in ['inspector', 'director']: return RedirectResponse(url="/login")
    pending = db.query(models.User).filter(models.User.role == models.UserRole.volunteer, models.User.status == models.UserStatus.pending).all()
    active = db.query(models.User).filter(models.User.role == models.UserRole.volunteer, models.User.status == models.UserStatus.active).all()
    return templates.TemplateResponse("admin_volunteers.html", {"request": request, "user": user, "pending_users": pending, "active_users": active})

@app.post("/admin/api/volunteer/{user_id}/approve")
async def approve_volunteer(user_id: int, request: Request, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    if not user or user.role.name not in ['inspector', 'director']: return {"status": "error"}
    volunteer = db.query(models.User).filter(models.User.id == user_id).first()
    if volunteer:
        volunteer.status = models.UserStatus.active
        db.add(models.Notification(user_id=volunteer.id, message="Ваш аккаунт одобрен! Вы можете брать задачи.", link="/volunteer/feed"))
        db.commit()
        return {"status": "success"}
    return {"status": "error"}

@app.get("/admin/analytics")
async def admin_analytics(request: Request, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    if not user or user.role.name not in ['inspector', 'director']: return RedirectResponse(url="/login")
    total_apps = db.query(models.Application).count()
    completed_apps = db.query(models.Application).filter(models.Application.status == models.ApplicationStatus.completed).count()
    total_volunteers = db.query(models.User).filter(models.User.role == models.UserRole.volunteer).count()
    district_stats = db.query(models.District.name, func.count(models.Application.id).label("count")).outerjoin(models.Application).group_by(models.District.id).all()
    benefit_stats = db.query(models.Application.benefit_category, func.count(models.Application.id).label("count")).group_by(models.Application.benefit_category).all()
    return templates.TemplateResponse("admin_analytics.html", {"request": request, "user": user, "total_apps": total_apps, "completed_apps": completed_apps, "total_volunteers": total_volunteers, "districts_labels": [d.name for d in district_stats], "districts_data": [d.count for d in district_stats], "benefit_labels": [b.benefit_category or "Без льгот" for b in benefit_stats if b.count > 0], "benefit_data": [b.count for b in benefit_stats if b.count > 0]})

# --- ЧАТ ---
@app.get("/api/chat/{app_id}")
async def get_chat_messages(app_id: int, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    if not user: return []
    messages = db.query(models.TaskMessage).filter(models.TaskMessage.application_id == app_id).order_by(models.TaskMessage.created_at.asc()).all()
    return [{"sender": m.sender.full_name, "role": m.sender.role.name, "message": m.message, "time": m.created_at.strftime("%H:%M")} for m in messages]

@app.post("/api/chat/{app_id}")
async def send_chat_message(app_id: int, request: Request, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    if not user: return {"status": "error"}
    data = await request.json()
    new_msg = models.TaskMessage(application_id=app_id, sender_id=user.id, message=data.get("message"))
    db.add(new_msg)
    
    app_obj = db.query(models.Application).filter(models.Application.id == app_id).first()
    assignment = db.query(models.TaskAssignment).filter(models.TaskAssignment.application_id == app_id, models.TaskAssignment.status.in_([models.TaskStatus.accepted, models.TaskStatus.rejected])).first()
    
    # Уведомления: если пишет Житель или Волонтер -> уведомляем Инспектора.
    if user.role.name in ['volunteer', 'resident']:
        inspectors = db.query(models.User).filter(models.User.role.in_([models.UserRole.inspector, models.UserRole.director])).all()
        for insp in inspectors: db.add(models.Notification(user_id=insp.id, message=f"Новое сообщение в чате по заявке {app_obj.uin}", link=f"/admin/chat/{app_id}"))
    # Если Инспектор пишет волонтеру
    elif user.role.name in ['inspector', 'director'] and assignment:
        db.add(models.Notification(user_id=assignment.volunteer_id, message=f"Инспектор ответил вам в чате {app_obj.uin}", link=f"/volunteer/task/{app_id}"))
        # И уведомляем жителя тоже, на случай если инспектор отвечает ему
        db.add(models.Notification(user_id=app_obj.user_id, message=f"Служба поддержки ответила по заявке {app_obj.uin}", link=f"/resident/chat/{app_id}"))
        
    db.commit()
    return {"status": "success"}

@app.get("/admin/chat/{app_id}")
async def admin_chat_page(app_id: int, request: Request, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    if not user or user.role.name not in ['inspector', 'director']: return RedirectResponse(url="/login")
    app_obj = db.query(models.Application).filter(models.Application.id == app_id).first()
    return templates.TemplateResponse("admin_chat.html", {"request": request, "app": app_obj, "user": user})