"""Auto-provisioned local operator account for appliance deployments.

When LOCAL_MODE is enabled (a trusted-LAN, self-hosted install — e.g. a
Proxmox VM), the console must work without a login step. This bootstrap
idempotently creates one active admin account whose password is random and
never disclosed: nobody can sign in to it with credentials. Instead,
POST /api/v1/auth/session (app/api/auth.py) issues a normal short-lived JWT
for this account, so every downstream authorization path — owner scoping,
role checks, SSE streams — keeps working unchanged.
"""

import secrets

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionFactory
from app.core.security import hash_password
from app.models.entities import Role, User


async def ensure_local_operator() -> None:
    """Idempotently create the local operator; safe to run on every startup."""
    settings = get_settings()
    async with SessionFactory() as session:
        email = str(settings.local_operator_email)
        user = await session.scalar(select(User).where(User.email == email))
        if user is None:
            session.add(
                User(
                    email=email,
                    display_name="Local Operator",
                    # Random throwaway: /auth/token can never match it, so the
                    # only way into this account is the local /auth/session.
                    password_hash=hash_password(secrets.token_urlsafe(32)),
                    role=Role.admin,
                )
            )
            await session.commit()
