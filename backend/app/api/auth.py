from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import CurrentUser, create_session_token, verify_password
from app.db import get_db
from app.models import User
from app.schemas import LoginRequest, UserResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", status_code=status.HTTP_204_NO_CONTENT)
def login(payload: LoginRequest, response: Response, db: Annotated[Session, Depends(get_db)]) -> None:
    user = db.scalar(select(User).where(User.username == payload.username))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

    response.set_cookie(
        key="zhiliu_session",
        value=create_session_token(user.id),
        httponly=True,
        secure=get_settings().cookie_secure,
        samesite="lax",
        max_age=14 * 24 * 60 * 60,
        path="/",
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    response.delete_cookie("zhiliu_session", path="/")


@router.get("/me", response_model=UserResponse)
def me(user: CurrentUser) -> User:
    return user

