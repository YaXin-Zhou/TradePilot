"""Authentication API endpoints"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from auth.schemas import RegisterRequest, LoginRequest, TokenResponse, UserResponse
from auth.utils import hash_password, verify_password, create_access_token
from auth.deps import get_current_user, get_current_user_optional
from db.database import get_session
from db.models import User as UserModel

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _validate_password(password: str) -> str | None:
    """校验密码强度。返回 None 表示通过，否则返回错误消息。"""
    if len(password) < 8:
        return "Password must be at least 8 characters"
    if not any(c.isdigit() for c in password):
        return "Password must contain at least one digit"
    if not any(c.isalpha() for c in password):
        return "Password must contain at least one letter"
    return None


@router.post("/register", response_model=TokenResponse)
async def register(
    req: RegisterRequest,
    session=Depends(get_session),
    current_user: dict | None = Depends(get_current_user_optional),
):
    # 密码强度校验
    err = _validate_password(req.password)
    if err:
        raise HTTPException(status_code=400, detail=err)

    existing = await session.execute(select(UserModel).where(UserModel.name == req.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username already exists")

    # v2.0: 关闭开放注册 — 首个用户自动成为管理员，后续需管理员邀请
    user_count = await session.scalar(select(func.count(UserModel.id))) or 0
    if user_count > 0 and not (current_user and current_user.get("is_admin")):
        raise HTTPException(status_code=403, detail="注册已关闭，需管理员邀请")

    is_admin = user_count == 0
    user = UserModel(
        name=req.username,
        email=req.email or None,
        hashed_password=hash_password(req.password),
        is_admin=is_admin,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    token = create_access_token({"sub": user.id, "name": user.name, "is_admin": user.is_admin})
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, session=Depends(get_session)):
    result = await session.execute(select(UserModel).where(UserModel.name == req.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({"sub": user.id, "name": user.name, "is_admin": user.is_admin})
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user), session=Depends(get_session)):
    result = await session.execute(select(UserModel).where(UserModel.id == current_user["id"]))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(id=user.id, username=user.name, email=user.email or "", is_admin=user.is_admin)
