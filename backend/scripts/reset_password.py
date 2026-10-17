"""Set a new password for an account, from the command line.

Run from backend/:  .venv/bin/python -m scripts.reset_password you@example.com
With no email, lists the accounts in the database.
"""

import getpass
import sys

from sqlalchemy import func, select

from app.auth import hash_password
from app.db import SessionLocal
from app.models import User


def main() -> int:
    with SessionLocal() as db:
        if len(sys.argv) < 2:
            users = db.scalars(select(User).order_by(User.id)).all()
            if not users:
                print("No accounts yet. Create one at http://localhost:5173/signup")
                return 1
            print("Accounts:")
            for u in users:
                print(f"  {u.email}  ({u.first_name} {u.last_name})")
            print("\nRun again with the email: .venv/bin/python -m scripts.reset_password <email>")
            return 0

        email = sys.argv[1].strip().lower()
        user = db.scalar(select(User).where(func.lower(User.email) == email))
        if user is None:
            print(f"No account with email {email}. Run without an email to list accounts.")
            return 1

        pw = getpass.getpass("New password (at least 10 characters): ")
        if len(pw) < 10:
            print("Too short. Nothing changed.")
            return 1
        if getpass.getpass("Confirm new password: ") != pw:
            print("Passwords don't match. Nothing changed.")
            return 1

        user.password_hash = hash_password(pw)
        db.commit()
        print(f"Password updated for {user.email}. Log in at http://localhost:5173/login")
        return 0


if __name__ == "__main__":
    sys.exit(main())
