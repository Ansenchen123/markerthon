from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import MerchantUser
from app.schemas import LoginRequest, LoginResponse, StoreResponse
from app.security import create_access_token, verify_password


router = APIRouter(tags=["auth"])


@router.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    user = db.scalar(select(MerchantUser).where(MerchantUser.username == payload.username))
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    token = create_access_token(
        {
            "sub": user.username,
            "userId": user.id,
            "storeId": user.store_id,
        }
    )
    return LoginResponse(
        accessToken=token,
        tokenType="bearer",
        store=StoreResponse(id=user.store.id, code=user.store.code, name=user.store.name),
    )
