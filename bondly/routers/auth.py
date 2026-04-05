from fastapi import APIRouter, Depends, HTTPException, status
import aiosqlite

from bondly.database import get_db
from bondly.models.user import LoginRequest, RegisterRequest, TokenResponse
from bondly.services import user_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=201)
async def register(body: RegisterRequest, db: aiosqlite.Connection = Depends(get_db)):
    """
    Create a new homeowner account.

    Your SA ID number is stored as a one-way hash and is never retrievable.
    It is used only to verify ownership of properties in Lightstone queries.
    """
    existing = await user_service.get_user_by_email(db, body.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    try:
        await user_service.create_user(
            db,
            email=body.email,
            password=body.password,
            full_name=body.full_name,
            id_number=body.id_number,
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Registration failed — email may already exist")

    return {
        "message": "Account created. Subscribe at /subscribe to activate your access.",
        "email": body.email,
    }


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: aiosqlite.Connection = Depends(get_db)):
    user = await user_service.get_user_by_email(db, body.email)
    if user is None or not user_service.verify_password(body.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    token = user_service.create_token(user["id"], user["email"])
    return TokenResponse(
        access_token=token,
        account_active=bool(user["active"]),
        message=None if user["active"] else "Account not yet activated — visit /subscribe to pay.",
    )
