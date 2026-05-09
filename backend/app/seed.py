from sqlalchemy import select
from sqlalchemy.orm import Session

from app.daily_reports import rebuild_daily_report_csvs
from app.database import SessionLocal
from app.init_db import init_db
from app.models import GovernmentUser, MerchantUser, Store
from app.security import hash_password


DEMO_STORES = [
    ("tea-shop", "青山茶飲", "台北市大安區", "tea.owner@example.com"),
    ("bento-shop", "晨光便當", "台北市中山區", "bento.owner@example.com"),
    ("cafe-shop", "巷口咖啡", "新北市板橋區", "cafe.owner@example.com"),
    ("tea-shop", "青山茶飲", "台北市大安區", "tea.staff@example.com"),
]
DEMO_PASSWORD = "password123"
DEMO_GOVERNMENT_USERS = [
    ("gov.admin@example.com", "password123"),
]


def seed_demo_data(db: Session) -> None:
    legacy_email_map = {
        "tea_owner": "tea.owner@example.com",
        "bento_owner": "bento.owner@example.com",
        "cafe_owner": "cafe.owner@example.com",
        "gov_admin": "gov.admin@example.com",
    }
    for legacy_username, user_email in legacy_email_map.items():
        existing_merchant_email = db.scalar(select(MerchantUser).where(MerchantUser.user_email == user_email))
        merchant_user = db.scalar(select(MerchantUser).where(MerchantUser.username == legacy_username))
        if merchant_user is not None and (existing_merchant_email is None or existing_merchant_email.id == merchant_user.id):
            merchant_user.username = user_email
            merchant_user.user_email = user_email
        existing_government_email = db.scalar(select(GovernmentUser).where(GovernmentUser.user_email == user_email))
        government_user = db.scalar(select(GovernmentUser).where(GovernmentUser.username == legacy_username))
        if government_user is not None and (existing_government_email is None or existing_government_email.id == government_user.id):
            government_user.username = user_email
            government_user.user_email = user_email
    db.flush()

    for code, name, region, user_email in DEMO_STORES:
        store = db.scalar(select(Store).where(Store.code == code))
        if store is None:
            store = Store(code=code, name=name, region=region)
            db.add(store)
            db.flush()
        else:
            store.region = region

        user = db.scalar(select(MerchantUser).where(MerchantUser.user_email == user_email))
        if user is None:
            db.add(
                MerchantUser(
                    store_id=store.id,
                    username=user_email,
                    user_email=user_email,
                    password_hash=hash_password(DEMO_PASSWORD),
                )
            )

    for user_email, password in DEMO_GOVERNMENT_USERS:
        user = db.scalar(select(GovernmentUser).where(GovernmentUser.user_email == user_email))
        if user is None:
            db.add(GovernmentUser(username=user_email, user_email=user_email, password_hash=hash_password(password)))
    db.commit()
    rebuild_daily_report_csvs(db)


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        seed_demo_data(db)
    finally:
        db.close()
    print("Seeded demo stores, merchant users, and government users.")
    print("Password for all demo users: password123")


if __name__ == "__main__":
    main()
