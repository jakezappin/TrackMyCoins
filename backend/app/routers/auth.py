from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import clear_session, current_user, hash_password, set_session, verify_password
from ..db import get_db
from ..models import User
from ..schemas import LoginIn, PasswordChange, ProfileUpdate, SignupIn, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def signup(body: SignupIn, response: Response, db: Session = Depends(get_db)):
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
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    if user is None or not verify_password(user.password_hash, body.password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
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
