import sys
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.passwords import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    hash_password,
    verify_password,
)
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models import User
from app.models.enums import Classification, Role

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "seed_users.yaml"


def load_seed_users(path: Path = DEFAULT_PATH) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)["users"]


def seed_users(db: Session, entries: list[dict], password: str) -> dict[str, int]:
    """Create or update the demo users. Safe to run repeatedly."""
    counts = {"created": 0, "updated": 0, "unchanged": 0}
    for entry in entries:
        email = entry["email"].strip().lower()
        wanted = {
            "full_name": entry.get("full_name", ""),
            "role": Role(entry["role"]),
            "department": entry.get("department"),
            "clearance": Classification(entry["clearance"]),
            "is_active": entry.get("is_active", True),
        }
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            db.add(User(email=email, password_hash=hash_password(password), **wanted))
            counts["created"] += 1
            continue

        changed = False
        for field, value in wanted.items():
            if getattr(user, field) != value:
                setattr(user, field, value)
                changed = True
        if not verify_password(password, user.password_hash):
            user.password_hash = hash_password(password)
            changed = True
        counts["updated" if changed else "unchanged"] += 1

    db.commit()
    return counts


def main() -> int:
    password = get_settings().seed_user_password.get_secret_value()
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        print(
            f"SEED_USER_PASSWORD in .env must be {MIN_PASSWORD_LENGTH} to "
            f"{MAX_PASSWORD_LENGTH} characters long",
            file=sys.stderr,
        )
        return 1
    with SessionLocal() as db:
        counts = seed_users(db, load_seed_users(), password)
    print(f"seeded users: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
