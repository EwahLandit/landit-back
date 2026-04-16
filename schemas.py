from pydantic import BaseModel, EmailStr
from typing import List, Optional, Dict, Any
from datetime import datetime


# ── AUTH ──────────────────────────────────────────────────────────────────

class UserRegister(BaseModel):
    name: str
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserOut(BaseModel):
    id: int
    name: str
    email: str
    is_active: bool
    plan: str
    subscription_status: str
    trial_ends_at: Optional[datetime] = None
    class Config:
        from_attributes = True

class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserOut

# ── BILLING ───────────────────────────────────────────────────────────────

class BillingStatus(BaseModel):
    plan: str
    subscription_status: str
    trial_ends_at: Optional[datetime] = None
    days_left: Optional[int] = None
    is_trial: bool
    is_expired: bool

class PlanUpgrade(BaseModel):
    plan: str

# ── WEBSITE ───────────────────────────────────────────────────────────────

class DomainBase(BaseModel):
    name: str
    type: str = "subdomain"

class DomainCreate(DomainBase):
    pass

class DomainOut(DomainBase):
    id: int
    website_id: int
    class Config:
        from_attributes = True

class WebVitalsOut(BaseModel):
    lcp: str
    fid: str
    cls: str
    timestamp: datetime
    class Config:
        from_attributes = True

class WebsiteBase(BaseModel):
    template_id: str
    slug: str
    content: Dict[str, Any]

class WebsiteCreate(WebsiteBase):
    pass

class WebsiteUpdate(BaseModel):
    content: Optional[Dict[str, Any]] = None
    template_id: Optional[str] = None

class WebsiteOut(WebsiteBase):
    id: int
    user_id: int
    seo_score: int
    speed_score: int
    accessibility_score: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    domains: List[DomainOut] = []
    vitals: List[WebVitalsOut] = []
    class Config:
        from_attributes = True

# ── ANALYTICS ─────────────────────────────────────────────────────────────

class DailyStats(BaseModel):
    date: str
    visits: int
    conversions: int
    bounce_rate: float
    avg_time_seconds: int

class DashboardStats(BaseModel):
    total_visits: int
    visits_trend: float        # % cambio vs semana anterior
    conversion_rate: float
    conversion_trend: float
    avg_time_seconds: int
    time_trend: float
    bounce_rate: float
    bounce_trend: float
    weekly_visits: List[DailyStats]
    weekly_conversions: List[DailyStats]

# ── NOTIFICATIONS ─────────────────────────────────────────────────────────

class NotificationOut(BaseModel):
    id: int
    icon: str
    icon_bg: str
    icon_color: str
    title: str
    is_read: bool
    created_at: datetime
    class Config:
        from_attributes = True

# ── SUPPORT ───────────────────────────────────────────────────────────────

class TicketCreate(BaseModel):
    title: str
    category: str
    description: str

class TicketOut(BaseModel):
    id: int
    title: str
    category: str
    description: str
    status: str
    reply: Optional[str] = None
    created_at: datetime
    class Config:
        from_attributes = True

# ── BLOCK BUILDER ─────────────────────────────────────────────────────────

class BlockIn(BaseModel):
    id: str
    type: str
    visible: bool
    config: Dict[str, Any]
    mobile_config: Optional[Dict[str, Any]] = None

class SiteContentIn(BaseModel):
    schema_version: int
    site: Dict[str, Any]
    theme: Dict[str, Any]
    blocks: List[BlockIn]

class AssetOut(BaseModel):
    id: int
    filename: str
    url: str
    mime_type: str
    size_bytes: int
    width: Optional[int] = None
    height: Optional[int] = None
    created_at: datetime
    class Config:
        from_attributes = True

class FormSubmissionIn(BaseModel):
    block_id: str
    fields: Dict[str, Any]

# ── API KEYS ──────────────────────────────────────────────────────────────

class ApiKeyCreate(BaseModel):
    name: str

class ApiKeyOut(BaseModel):
    id: int
    name: str
    key_value: str
    created_at: datetime
    is_active: bool
    class Config:
        from_attributes = True
