from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, JSON, Float, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Suscripción
    plan = Column(String(20), default="trial")
    subscription_status = Column(String(20), default="trial")
    trial_ends_at = Column(DateTime(timezone=True), nullable=True)

    # Relaciones
    websites = relationship("Website", back_populates="owner", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")
    tickets = relationship("SupportTicket", back_populates="user", cascade="all, delete-orphan")
    api_keys = relationship("ApiKey", back_populates="user", cascade="all, delete-orphan")


class Website(Base):
    __tablename__ = "websites"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    template_id = Column(String(50), nullable=False)
    slug = Column(String(100), unique=True, index=True, nullable=False)
    content = Column(JSON, nullable=False)
    seo_score = Column(Integer, default=90)
    speed_score = Column(Integer, default=85)
    accessibility_score = Column(Integer, default=95)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    owner = relationship("User", back_populates="websites")
    domains = relationship("Domain", back_populates="website", cascade="all, delete-orphan")
    vitals = relationship("WebVitals", back_populates="website", cascade="all, delete-orphan")
    visits = relationship("SiteVisit", back_populates="website", cascade="all, delete-orphan")


class Domain(Base):
    __tablename__ = "domains"

    id = Column(Integer, primary_key=True, index=True)
    website_id = Column(Integer, ForeignKey("websites.id"), nullable=False)
    name = Column(String(255), unique=True, nullable=False)
    type = Column(String(20), default="subdomain")
    website = relationship("Website", back_populates="domains")


class WebVitals(Base):
    __tablename__ = "web_vitals"

    id = Column(Integer, primary_key=True, index=True)
    website_id = Column(Integer, ForeignKey("websites.id"), nullable=False)
    lcp = Column(String(20), default="1.2s")
    fid = Column(String(20), default="10ms")
    cls = Column(String(20), default="0.01")
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    website = relationship("Website", back_populates="vitals")


class SiteVisit(Base):
    """Visitas diarias por sitio — se incrementa con cada visita real o se siembra al crear el sitio."""
    __tablename__ = "site_visits"

    id = Column(Integer, primary_key=True, index=True)
    website_id = Column(Integer, ForeignKey("websites.id"), nullable=False)
    date = Column(String(10), nullable=False)   # YYYY-MM-DD
    visits = Column(Integer, default=0)
    conversions = Column(Integer, default=0)
    bounce_rate = Column(Float, default=40.0)   # porcentaje
    avg_time_seconds = Column(Integer, default=120)  # segundos

    website = relationship("Website", back_populates="visits")


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    icon = Column(String(20), default="bell")
    icon_bg = Column(String(50), default="rgba(0,87,255,.12)")
    icon_color = Column(String(50), default="var(--accent)")
    title = Column(String(255), nullable=False)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="notifications")


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(255), nullable=False)
    category = Column(String(100), default="Soporte técnico")
    description = Column(Text, nullable=False)
    status = Column(String(20), default="Pendiente")  # Activo | Pendiente | Cerrado
    reply = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="tickets")


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(100), nullable=False)
    key_value = Column(String(64), unique=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, default=True)

    user = relationship("User", back_populates="api_keys")
