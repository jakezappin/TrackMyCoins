import hmac

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import clear_session, current_user, hash_password, set_session, verify_password
from ..config import get_settings
from ..db import get_db
from ..models import User
from ..schemas import LoginIn, PasswordChange, ProfileUpdate, SignupIn, UserOut
from ..services.ratelimit import FailureLimiter

router = APIRouter(prefix="/api/auth", tags=["auth"])
settings = get_settings()
login_limiter = FailureLimiter(settings.login_max_failures, settings.login_window_seconds)


def _client_ip(request: Request) -> str:
    # Behind Fly's proxy, uvicorn --proxy-headers puts the real client address here.
    return request.client.host if request.client else "unknown"


@router.get("/config")
def auth_config():
    """What the sign-up page needs to know."""
    return {"signup": settings.signup_mode}


@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def signup(body: SignupIn, response: Response, db: Session = Depends(get_db)):
    if settings.signup_mode == "closed":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "New accounts aren't being accepted right now")
    if settings.signup_mode == "invite":
        given = (body.invite_code or "").strip()
        if not settings.invite_code or not hmac.compare_digest(given, settings.invite_code):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "That invite code isn't valid")
    email = body.email.lower()
    if db.scalar(select(User).where(func.lower(User.email) == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with that email already exists")
    user = User(
        email=email,
        first_name=body.first_name.strip(),
        last_name=body.last_name.strip(),
        password_hash=hash_password(body.password),
    )
    db.add(user)
    db.commit()
    set_session(response, user)
    return user


@router.post("/login", response_model=UserOut)
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    keys = (f"email:{body.email.lower()}", f"ip:{_client_ip(request)}")
    if login_limiter.blocked(*keys):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many failed attempts. Try again in 15 minutes.")
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    if user is None or not verify_password(user.password_hash, body.password):
        login_limiter.fail(*keys)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    login_limiter.reset(f"email:{body.email.lower()}")
    set_session(response, user)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response):
    clear_session(response)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


@router.put("/me", response_model=UserOut)
def update_profile(body: ProfileUpdate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    email = body.email.lower()
    if email != user.email.lower():
        if not body.current_password or not verify_password(user.password_hash, body.current_password):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Enter your current password to change your email")
        taken = db.scalar(select(User).where(func.lower(User.email) == email, User.id != user.id))
        if taken:
            raise HTTPException(status.HTTP_409_CONFLICT, "An account with that email already exists")
        user.email = email
    user.first_name = body.first_name.strip()
    user.last_name = body.last_name.strip()
    db.commit()
    return user


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(body: PasswordChange, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if not verify_password(user.password_hash, body.current_password):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    db.commit()
