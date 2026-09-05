"""
Authentication via Google Identity Platform / Firebase Authentication.

The frontend signs the user in with Firebase Auth (email/password, Google
sign-in, etc.) and sends the resulting ID token on every request as:

    Authorization: Bearer <firebase_id_token>

This module verifies that token server-side using the Firebase Admin SDK,
which validates the signature against Google's public keys -- no secrets
are shared with the client and tokens cannot be forged.
"""

from fastapi import Header, HTTPException, status, Depends
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db, User

_firebase_app = None


def _get_firebase_app():
    global _firebase_app
    if _firebase_app is None:
        import firebase_admin
        from firebase_admin import credentials

        cred = credentials.ApplicationDefault()
        _firebase_app = firebase_admin.initialize_app(
            cred, {"projectId": settings.FIREBASE_PROJECT_ID}
        )
    return _firebase_app


def _verify_token(id_token: str) -> dict:
    from firebase_admin import auth as firebase_auth

    _get_firebase_app()
    return firebase_auth.verify_id_token(id_token)


def get_current_user(
    authorization: str = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    """
    Resolves the authenticated User row for the incoming request.

    In local development (DISABLE_AUTH_FOR_LOCAL_DEV=true) this falls
    back to a fixed demo user so the API can be exercised without a
    live Identity Platform project.
    """
    if settings.DISABLE_AUTH_FOR_LOCAL_DEV:
        return _get_or_create_user(db, firebase_uid="local-dev-user", email="dev@example.com")

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
        )

    id_token = authorization.split(" ", 1)[1]
    try:
        decoded = _verify_token(id_token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
        )

    return _get_or_create_user(
        db, firebase_uid=decoded["uid"], email=decoded.get("email")
    )


def _get_or_create_user(db: Session, firebase_uid: str, email: str) -> User:
    user = db.query(User).filter(User.firebase_uid == firebase_uid).first()
    if user:
        return user
    user = User(firebase_uid=firebase_uid, email=email)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
