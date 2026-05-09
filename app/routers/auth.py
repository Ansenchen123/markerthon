from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import MerchantUser, Store
from app.schemas import LoginRequest, LoginResponse, MerchantRegisterRequest, StoreResponse
from app.security import create_access_token, hash_password, verify_password


router = APIRouter(tags=["auth"])


def _merchant_token(user: MerchantUser) -> str:
    return create_access_token(
        {
            "sub": user.username,
            "userId": user.id,
            "storeId": user.store_id,
            "role": "merchant",
        }
    )


def _login_response(user: MerchantUser) -> LoginResponse:
    return LoginResponse(
        accessToken=_merchant_token(user),
        tokenType="bearer",
        store=StoreResponse(id=user.store.id, code=user.store.code, name=user.store.name),
    )


@router.post("/auth/register", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
def register(payload: MerchantRegisterRequest, db: Session = Depends(get_db)) -> LoginResponse:
    existing_user = db.scalar(select(MerchantUser).where(MerchantUser.username == payload.username))
    if existing_user is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")

    existing_store = db.scalar(select(Store).where(Store.code == payload.store_code))
    if existing_store is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Store code already exists")

    store = Store(code=payload.store_code, name=payload.store_name)
    db.add(store)
    db.flush()

    user = MerchantUser(
        store_id=store.id,
        username=payload.username,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _login_response(user)


@router.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    user = db.scalar(select(MerchantUser).where(MerchantUser.username == payload.username))
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    return _login_response(user)
