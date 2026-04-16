import os
import io
import uuid
import json
import secrets
from dotenv import load_dotenv
from typing import Optional, List
from datetime import datetime, timedelta, timezone, date
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from database import engine, get_db, Base
from models import User, Website, Domain, WebVitals, SiteVisit, Notification, SupportTicket, ApiKey, Asset, FormSubmission
from schemas import (
    UserRegister, UserLogin, Token, UserOut, UserUpdate, PasswordChange,
    WebsiteCreate, WebsiteOut, WebsiteUpdate, DomainCreate, DomainOut,
    BillingStatus, PlanUpgrade,
    DashboardStats, DailyStats,
    NotificationOut, TicketCreate, TicketOut,
    ApiKeyCreate, ApiKeyOut,
    BlockIn, SiteContentIn, AssetOut, FormSubmissionIn,
)
from auth import hash_password, verify_password, create_access_token, decode_token
from fastapi.security import OAuth2PasswordBearer

load_dotenv()
Base.metadata.create_all(bind=engine)

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
API_BASE = os.getenv("API_BASE", "http://localhost:8000")
UPLOADS_DIR = "uploads"
os.makedirs(UPLOADS_DIR, exist_ok=True)

ALLOWED_BLOCK_TYPES: set[str] = set()  # populated after block registry stabilises; empty = accept-all in v1

app = FastAPI(title="LandIt API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    if not token:
        raise HTTPException(status_code=401, detail="No autenticado")
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")
    user = db.query(User).filter(User.id == int(payload["sub"])).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return user


def seed_initial_data(user: User, db: Session):
    """Crea datos iniciales cuando un usuario se registra."""
    # Notificaciones de bienvenida
    welcome_notifs = [
        Notification(user_id=user.id, icon="rocket", icon_bg="rgba(0,87,255,.12)", icon_color="var(--accent)",
                     title="¡Bienvenido a LandIt! Tu prueba de 15 días ha comenzado.", is_read=False),
        Notification(user_id=user.id, icon="book", icon_bg="rgba(0,168,107,.12)", icon_color="var(--success)",
                     title="Explora el editor de plantillas para crear tu primera landing page.", is_read=False),
        Notification(user_id=user.id, icon="lightbulb", icon_bg="rgba(255,153,0,.12)", icon_color="var(--warning)",
                     title="Consejo: Conecta tu dominio personalizado en 'Mi Sitio Web'.", is_read=True),
    ]
    db.add_all(welcome_notifs)
    db.commit()


# ── HEALTH ────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


# ── AUTH ──────────────────────────────────────────────────────────────────

@app.post("/auth/register", response_model=Token, status_code=201)
def register(body: UserRegister, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=409, detail="El correo ya está registrado.")
    user = User(
        name=body.name, email=body.email,
        hashed_password=hash_password(body.password),
        plan="trial", subscription_status="trial",
        trial_ends_at=datetime.now(timezone.utc) + timedelta(days=15),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    seed_initial_data(user, db)
    token = create_access_token({"sub": str(user.id), "email": user.email})
    return Token(access_token=token, token_type="bearer", user=UserOut.model_validate(user))


@app.post("/auth/login", response_model=Token)
def login(body: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Correo o contraseña incorrectos.")
    token = create_access_token({"sub": str(user.id), "email": user.email})
    return Token(access_token=token, token_type="bearer", user=UserOut.model_validate(user))


@app.get("/auth/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user


@app.put("/auth/me", response_model=UserOut)
def update_profile(body: UserUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if body.name:
        current_user.name = body.name
    if body.email:
        existing = db.query(User).filter(User.email == body.email, User.id != current_user.id).first()
        if existing:
            raise HTTPException(status_code=409, detail="El correo ya está en uso.")
        current_user.email = body.email
    db.commit()
    db.refresh(current_user)
    return current_user


@app.post("/auth/change-password")
def change_password(body: PasswordChange, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Contraseña actual incorrecta.")
    current_user.hashed_password = hash_password(body.new_password)
    db.commit()
    return {"message": "Contraseña actualizada correctamente."}


# ── BILLING ───────────────────────────────────────────────────────────────

@app.get("/billing/status", response_model=BillingStatus)
def billing_status(current_user: User = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    is_trial = current_user.subscription_status == "trial"
    days_left = None
    is_expired = False
    if is_trial and current_user.trial_ends_at:
        trial_end = current_user.trial_ends_at
        if trial_end.tzinfo is None:
            trial_end = trial_end.replace(tzinfo=timezone.utc)
        delta = trial_end - now
        days_left = max(0, delta.days)
        is_expired = days_left == 0
    else:
        is_expired = current_user.subscription_status == "expired"
    return BillingStatus(
        plan=current_user.plan, subscription_status=current_user.subscription_status,
        trial_ends_at=current_user.trial_ends_at, days_left=days_left,
        is_trial=is_trial, is_expired=is_expired,
    )


@app.post("/billing/upgrade", response_model=BillingStatus)
def billing_upgrade(body: PlanUpgrade, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if body.plan not in {"starter", "growth", "scale", "custom"}:
        raise HTTPException(status_code=400, detail="Plan inválido.")
    current_user.plan = body.plan
    current_user.subscription_status = "active"
    current_user.trial_ends_at = None
    db.commit()
    db.refresh(current_user)
    # Notificación de upgrade
    db.add(Notification(
        user_id=current_user.id, icon="billing",
        icon_bg="rgba(0,168,107,.12)", icon_color="var(--success)",
        title=f"¡Plan {body.plan.capitalize()} activado correctamente! Bienvenido.",
        is_read=False,
    ))
    db.commit()
    return BillingStatus(plan=current_user.plan, subscription_status="active",
                         trial_ends_at=None, days_left=None, is_trial=False, is_expired=False)


# ── WEBSITES ──────────────────────────────────────────────────────────────

@app.get("/websites/me", response_model=Optional[WebsiteOut])
def get_my_website(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(Website).filter(Website.user_id == current_user.id).order_by(Website.created_at.desc()).first()


@app.post("/websites", response_model=WebsiteOut, status_code=201)
def create_website(body: WebsiteCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    new_site = Website(
        user_id=current_user.id, template_id=body.template_id,
        slug=body.slug, content=body.content,
        seo_score=94, speed_score=82, accessibility_score=90,
    )
    db.add(new_site)
    db.commit()
    db.refresh(new_site)
    # Vitals iniciales
    db.add(WebVitals(website_id=new_site.id, lcp="1.8s", fid="85ms", cls="0.05"))
    # Visitas de los últimos 7 días (datos iniciales realistas)
    today = date.today()
    import random
    base_visits = [120, 145, 98, 167, 203, 178, 215]
    for i in range(7):
        d = today - timedelta(days=6 - i)
        v = base_visits[i] + random.randint(-10, 10)
        db.add(SiteVisit(
            website_id=new_site.id,
            date=d.isoformat(),
            visits=v,
            conversions=max(1, int(v * 0.032)),
            bounce_rate=round(35 + random.uniform(-5, 10), 1),
            avg_time_seconds=random.randint(100, 180),
        ))
    db.commit()
    # Notificación
    db.add(Notification(
        user_id=current_user.id, icon="rocket",
        icon_bg="rgba(0,87,255,.12)", icon_color="var(--accent)",
        title=f"Tu sitio '{body.slug}' fue creado exitosamente.", is_read=False,
    ))
    db.commit()
    db.refresh(new_site)
    return new_site


@app.put("/websites/{website_id}", response_model=WebsiteOut)
def update_website(website_id: int, body: WebsiteUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    website = db.query(Website).filter(Website.id == website_id, Website.user_id == current_user.id).first()
    if not website:
        raise HTTPException(status_code=404, detail="Sitio no encontrado")
    if body.content is not None:
        website.content = body.content
    if body.template_id is not None:
        website.template_id = body.template_id
    db.commit()
    db.refresh(website)
    return website


@app.delete("/websites/{website_id}")
def delete_website(website_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    website = db.query(Website).filter(Website.id == website_id, Website.user_id == current_user.id).first()
    if not website:
        raise HTTPException(status_code=404, detail="Sitio no encontrado")
    db.delete(website)
    db.commit()
    return {"message": "Sitio eliminado"}


@app.post("/websites/{website_id}/domains", response_model=DomainOut)
def add_domain(website_id: int, body: DomainCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    website = db.query(Website).filter(Website.id == website_id, Website.user_id == current_user.id).first()
    if not website:
        raise HTTPException(status_code=404, detail="Sitio no encontrado")
    if db.query(Domain).filter(Domain.name == body.name).first():
        raise HTTPException(status_code=400, detail="El dominio ya está registrado")
    new_domain = Domain(website_id=website.id, name=body.name, type=body.type)
    db.add(new_domain)
    db.commit()
    db.refresh(new_domain)
    return new_domain


@app.delete("/domains/{domain_id}")
def delete_domain(domain_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    domain = db.query(Domain).join(Website).filter(Domain.id == domain_id, Website.user_id == current_user.id).first()
    if not domain:
        raise HTTPException(status_code=404, detail="Dominio no encontrado")
    db.delete(domain)
    db.commit()
    return {"message": "Dominio eliminado"}


# ── BLOCK BUILDER ─────────────────────────────────────────────────────────

@app.put("/websites/{website_id}/blocks")
def save_blocks(website_id: int, body: SiteContentIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if body.schema_version != 2:
        raise HTTPException(status_code=422, detail="schema_version must be 2")
    if len(body.blocks) > 80:
        raise HTTPException(status_code=422, detail="Demasiados bloques (máximo 80)")
    if ALLOWED_BLOCK_TYPES:
        invalid = [b.type for b in body.blocks if b.type not in ALLOWED_BLOCK_TYPES]
        if invalid:
            raise HTTPException(status_code=422, detail=f"Tipos de bloque no válidos: {invalid}")
    payload_bytes = len(json.dumps(body.model_dump()).encode())
    if payload_bytes > 256 * 1024:
        raise HTTPException(status_code=413, detail="Payload demasiado grande (máximo 256 KB)")
    site = db.query(Website).filter(Website.id == website_id, Website.user_id == current_user.id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Sitio no encontrado")
    site.content = body.model_dump()
    db.commit()
    return {"message": "Bloques guardados"}


@app.post("/websites/{website_id}/assets", response_model=AssetOut)
async def upload_asset(website_id: int, file: UploadFile = File(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from PIL import Image as PilImage
    site = db.query(Website).filter(Website.id == website_id, Website.user_id == current_user.id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Sitio no encontrado")
    ALLOWED_MIME = {"image/png", "image/jpeg", "image/webp", "image/svg+xml"}
    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(status_code=422, detail="Tipo de archivo no soportado (png, jpg, webp, svg)")
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Archivo demasiado grande (máximo 5 MB)")
    ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename and "." in file.filename else "bin"
    file_uuid = str(uuid.uuid4())
    site_dir = os.path.join(UPLOADS_DIR, str(website_id))
    os.makedirs(site_dir, exist_ok=True)
    rel_path = f"{website_id}/{file_uuid}.{ext}"
    abs_path = os.path.join(UPLOADS_DIR, rel_path)
    with open(abs_path, "wb") as f:
        f.write(content)
    width, height = None, None
    if file.content_type != "image/svg+xml":
        img = PilImage.open(io.BytesIO(content))
        width, height = img.size
    asset_url = f"{API_BASE}/uploads/{rel_path}"
    asset = Asset(
        website_id=website_id,
        filename=file.filename or f"{file_uuid}.{ext}",
        url=asset_url,
        mime_type=file.content_type,
        size_bytes=len(content),
        width=width,
        height=height,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


@app.get("/websites/{website_id}/assets", response_model=List[AssetOut])
def list_assets(website_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    site = db.query(Website).filter(Website.id == website_id, Website.user_id == current_user.id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Sitio no encontrado")
    return db.query(Asset).filter(Asset.website_id == website_id).order_by(Asset.created_at.desc()).all()


@app.delete("/websites/{website_id}/assets/{asset_id}")
def delete_asset(website_id: int, asset_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    site = db.query(Website).filter(Website.id == website_id, Website.user_id == current_user.id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Sitio no encontrado")
    asset = db.query(Asset).filter(Asset.id == asset_id, Asset.website_id == website_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Recurso no encontrado")
    file_path = os.path.join(UPLOADS_DIR, str(website_id), os.path.basename(asset.url))
    if os.path.exists(file_path):
        os.remove(file_path)
    db.delete(asset)
    db.commit()
    return {"message": "Recurso eliminado"}


@app.get("/public/sites/{slug}")
def get_public_site(slug: str, db: Session = Depends(get_db)):
    site = db.query(Website).filter(Website.slug == slug).first()
    if not site:
        raise HTTPException(status_code=404, detail="Sitio no encontrado")
    return {"content": site.content, "slug": site.slug}


@app.post("/public/sites/{slug}/submit")
def submit_form(slug: str, body: FormSubmissionIn, db: Session = Depends(get_db)):
    site = db.query(Website).filter(Website.slug == slug).first()
    if not site:
        raise HTTPException(status_code=404, detail="Sitio no encontrado")
    submission = FormSubmission(website_id=site.id, block_id=body.block_id, payload=body.fields)
    db.add(submission)
    db.commit()
    return {"message": "Formulario enviado correctamente"}


# ── ANALYTICS / DASHBOARD STATS ───────────────────────────────────────────

@app.get("/analytics/stats", response_model=DashboardStats)
def get_analytics(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    website = db.query(Website).filter(Website.user_id == current_user.id).order_by(Website.created_at.desc()).first()
    if not website:
        # Sin sitio: devolver ceros
        empty = [DailyStats(date=(date.today() - timedelta(days=6-i)).isoformat(),
                            visits=0, conversions=0, bounce_rate=0, avg_time_seconds=0) for i in range(7)]
        return DashboardStats(total_visits=0, visits_trend=0, conversion_rate=0, conversion_trend=0,
                              avg_time_seconds=0, time_trend=0, bounce_rate=0, bounce_trend=0,
                              weekly_visits=empty, weekly_conversions=empty)

    today = date.today()
    # Últimos 7 días
    week_dates = [(today - timedelta(days=6-i)).isoformat() for i in range(7)]
    visits_rows = {v.date: v for v in db.query(SiteVisit).filter(
        SiteVisit.website_id == website.id,
        SiteVisit.date.in_(week_dates)
    ).all()}

    weekly: List[DailyStats] = []
    total_visits = 0
    total_conversions = 0
    total_time = 0
    total_bounce = 0.0

    for d in week_dates:
        row = visits_rows.get(d)
        v = row.visits if row else 0
        c = row.conversions if row else 0
        b = row.bounce_rate if row else 40.0
        t = row.avg_time_seconds if row else 120
        weekly.append(DailyStats(date=d, visits=v, conversions=c, bounce_rate=b, avg_time_seconds=t))
        total_visits += v
        total_conversions += c
        total_time += t
        total_bounce += b

    # Semana anterior para calcular tendencia
    prev_dates = [(today - timedelta(days=13-i)).isoformat() for i in range(7)]
    prev_rows = db.query(SiteVisit).filter(
        SiteVisit.website_id == website.id,
        SiteVisit.date.in_(prev_dates)
    ).all()
    prev_visits = sum(r.visits for r in prev_rows) or 1

    conv_rate = round((total_conversions / total_visits * 100), 2) if total_visits > 0 else 0
    avg_time = total_time // 7
    avg_bounce = round(total_bounce / 7, 1)
    visits_trend = round((total_visits - prev_visits) / prev_visits * 100, 1)

    return DashboardStats(
        total_visits=total_visits,
        visits_trend=visits_trend,
        conversion_rate=conv_rate,
        conversion_trend=0.8,
        avg_time_seconds=avg_time,
        time_trend=0.0,
        bounce_rate=avg_bounce,
        bounce_trend=-5.1,
        weekly_visits=weekly,
        weekly_conversions=weekly,
    )


# ── NOTIFICATIONS ─────────────────────────────────────────────────────────

@app.get("/notifications", response_model=List[NotificationOut])
def get_notifications(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(Notification).filter(Notification.user_id == current_user.id).order_by(Notification.created_at.desc()).all()


@app.patch("/notifications/{notif_id}/read")
def mark_read(notif_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    notif = db.query(Notification).filter(Notification.id == notif_id, Notification.user_id == current_user.id).first()
    if not notif:
        raise HTTPException(status_code=404, detail="Notificación no encontrada")
    notif.is_read = True
    db.commit()
    return {"message": "ok"}


@app.patch("/notifications/read-all")
def mark_all_read(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db.query(Notification).filter(Notification.user_id == current_user.id, Notification.is_read == False).update({"is_read": True})
    db.commit()
    return {"message": "ok"}


# ── SUPPORT ───────────────────────────────────────────────────────────────

@app.get("/support/tickets", response_model=List[TicketOut])
def get_tickets(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(SupportTicket).filter(SupportTicket.user_id == current_user.id).order_by(SupportTicket.created_at.desc()).all()


@app.post("/support/tickets", response_model=TicketOut, status_code=201)
def create_ticket(body: TicketCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    ticket = SupportTicket(
        user_id=current_user.id, title=body.title,
        category=body.category, description=body.description,
        status="Pendiente",
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    # Notificación automática
    db.add(Notification(
        user_id=current_user.id, icon="chat",
        icon_bg="rgba(255,153,0,.12)", icon_color="var(--warning)",
        title=f"Ticket #{ticket.id} creado: '{body.title}'. Te responderemos pronto.",
        is_read=False,
    ))
    db.commit()
    return ticket


# ── API KEYS ──────────────────────────────────────────────────────────────

@app.get("/settings/api-keys", response_model=List[ApiKeyOut])
def get_api_keys(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(ApiKey).filter(ApiKey.user_id == current_user.id, ApiKey.is_active == True).all()


@app.post("/settings/api-keys", response_model=ApiKeyOut, status_code=201)
def create_api_key(body: ApiKeyCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    key = ApiKey(
        user_id=current_user.id,
        name=body.name,
        key_value=f"sk_live_{secrets.token_hex(16)}",
    )
    db.add(key)
    db.commit()
    db.refresh(key)
    return key


@app.delete("/settings/api-keys/{key_id}")
def revoke_api_key(key_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    key = db.query(ApiKey).filter(ApiKey.id == key_id, ApiKey.user_id == current_user.id).first()
    if not key:
        raise HTTPException(status_code=404, detail="API key no encontrada")
    key.is_active = False
    db.commit()
    return {"message": "API key revocada"}
