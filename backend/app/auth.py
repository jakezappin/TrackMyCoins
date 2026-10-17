from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, Response, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import User

settings = get_settings()
_hasher = PasswordHasher()
_serializer = URLSafeTimedSerializer(settings.session_secret, salt="coinapp-session")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def set_session(response: Response, user: User) -> None:
    token = _serializer.dumps({"uid": user.id})
    response.set_cookie(
        settings.session_cookie,
        token,
        max_age=settings.session_max_age,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(settings.session_cookie)


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Not logged in")
    token = request.cookies.get(settings.session_cookie)
    if not token:
        raise unauthorized
    try:
        data = _serializer.loads(token, max_age=settings.session_max_age)
    except (BadSignature, SignatureExpired):
        raise unauthorized
    user = db.get(User, data.get("uid"))
    if user is None:
        raise unauthorized
    return user
