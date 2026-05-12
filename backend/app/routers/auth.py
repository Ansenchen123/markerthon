import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import MerchantUser, Store
from app.schemas import (
    LoginRequest,
    LoginResponse,
    MerchantRegisterRequest,
    StoreRegionLookupResponse,
    StoreResponse,
)
from app.security import create_access_token, hash_password, verify_password


router = APIRouter(tags=["auth"])


def _merchant_token(user: MerchantUser) -> str:
    return create_access_token(
        {
            "sub": user.user_email,
            "userId": user.id,
            "storeId": user.store_id,
            "role": "merchant",
        }
    )


def _login_response(user: MerchantUser) -> LoginResponse:
    return LoginResponse(
        accessToken=_merchant_token(user),
        tokenType="bearer",
        store=StoreResponse(id=user.store.id, code=user.store.code, name=user.store.name, region=user.store.region),
    )


def _generate_store_code(db: Session) -> str:
    for _ in range(10):
        code = f"store-{secrets.token_hex(4)}"
        exists = db.scalar(select(Store.id).where(Store.code == code))
        if exists is None:
            return code
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to generate store code")


@router.get("/auth/stores/region", response_model=StoreRegionLookupResponse)
def get_store_region(
    store_name: str = Query(..., alias="storeName", min_length=1),
    db: Session = Depends(get_db),
) -> StoreRegionLookupResponse:
    store = db.scalar(select(Store).where(Store.name == store_name.strip()))
    if store is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Store not found")

    return StoreRegionLookupResponse(storeName=store.name, region=store.region)


@router.post("/auth/register", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
def register(payload: MerchantRegisterRequest, db: Session = Depends(get_db)) -> LoginResponse:
    existing_user = db.scalar(select(MerchantUser).where(MerchantUser.user_email == payload.user_email))
    if existing_user is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User email already exists")

    store = db.scalar(select(Store).where(Store.name == payload.store_name))
    if store is None:
        store = Store(code=_generate_store_code(db), name=payload.store_name, region=payload.region)
        db.add(store)
        db.flush()
    elif store.region == "未設定" and payload.region != "未設定":
        store.region = payload.region

    user = MerchantUser(
        store_id=store.id,
        username=payload.user_email,
        user_email=payload.user_email,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _login_response(user)


@router.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    user = db.scalar(select(MerchantUser).where(MerchantUser.user_email == payload.user_email))
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email 或密碼錯誤")

    return _login_response(user)
