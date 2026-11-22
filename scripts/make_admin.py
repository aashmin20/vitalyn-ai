"""
Promote a staff account to administrator (the first admin has to be created this way).

    python3 scripts/make_admin.py you@example.com      # promote
    python3 scripts/make_admin.py --list               # show all staff accounts

Steps: 1) open the app and create your account on the Sign up page (it starts as "pending");
2) sign in once so VITALYN records it; 3) run this script. It uses the database in backend/.env
and never prints secrets.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from sqlmodel import Session, select  # noqa: E402

import database  # noqa: E402
from models import User  # noqa: E402


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 1
    with Session(database.engine) as session:
        if args[0] == "--list":
            for u in session.exec(select(User).order_by(User.created_at)).all():
                print(f"{u.email:40s} {u.role:13s} {u.status}")
            return 0
        email = args[0].strip().lower()
        user = session.exec(select(User).where(User.email == email)).first()
        if user is None:
            print(f"No account with email {email}.")
            print("Create it on the Sign up page and sign in once, then run this again.")
            return 1
        user.role, user.status = "admin", "active"
        session.add(user)
        session.commit()
        print(f"{email} is now an active administrator. Sign in again to use the Admin pages.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
