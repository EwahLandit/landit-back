# Back — see /service/CLAUDE.md for full project reference

## Quick ref

```bash
# Run (from this folder)
venv\Scripts\uvicorn.exe main:app --reload

# MySQL
"C:/Program Files/MySQL/MySQL Server 8.0/bin/mysql.exe" -u root -proot bd_landit -e "SHOW TABLES;"

# Python in venv
venv\Scripts\python.exe
```

## Files
- `main.py` — ALL routes. Do not split.
- `auth.py` — bcrypt hash + JWT (HS256, SECRET_KEY from .env)
- `models.py` — 7 SQLAlchemy models
- `schemas.py` — Pydantic v2 (from_attributes = True on all Out schemas)
- `database.py` — engine + get_db() dependency
- `.env` — DB creds + SECRET_KEY

## Password hashing
bcrypt (cost 12), one-way — cannot be decrypted. To reset a user password:
```python
from auth import hash_password
print(hash_password("newpassword"))
# then: UPDATE users SET hashed_password='<output>' WHERE id=1;
```
