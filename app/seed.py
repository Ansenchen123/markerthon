from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.init_db import init_db
from app.models import MerchantUser, Store
from app.security import hash_password


DEMO_STORES = [
    ("tea-shop", "青山茶飲", "tea_owner"),
    ("bento-shop", "晨光便當", "bento_owner"),
    ("cafe-shop", "巷口咖啡", "cafe_owner"),
]
DEMO_PASSWORD = "password123"


def seed_demo_data(db: Session) -> None:
    for code, name, username in DEMO_STORES:
        store = db.scalar(select(Store).where(Store.code == code))
        if store is None:
            store = Store(code=code, name=name)
            db.add(store)
            db.flush()

        user = db.scalar(select(MerchantUser).where(MerchantUser.username == username))
        if user is None:
            db.add(
                MerchantUser(
                    store_id=store.id,
                    username=username,
                    password_hash=hash_password(DEMO_PASSWORD),
                )
            )
    db.commit()


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        seed_demo_data(db)
    finally:
        db.close()
    print("Seeded demo stores and merchant users.")
    print("Password for all demo users: password123")


if __name__ == "__main__":
    main()
