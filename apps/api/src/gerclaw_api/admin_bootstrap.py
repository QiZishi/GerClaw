"""Explicit, local-only first-administrator bootstrap command."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import uuid

from gerclaw_api.config import get_settings
from gerclaw_api.database.session import Database
from gerclaw_api.encryption import configure_field_encryption
from gerclaw_api.modules.identity.passwords import hash_password
from gerclaw_api.repositories.account import AccountConflictError, SqlAlchemyAccountRepository
from gerclaw_api.security import audit_hmac_digest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create one GerClaw administrator account")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", help="omit to enter securely without echo")
    return parser


async def _run(username: str, password: str) -> None:
    settings = get_settings()
    configure_field_encryption(
        key_id=settings.data_encryption_key_id,
        key_base64=settings.data_encryption_key.get_secret_value(),
    )
    if not (3 <= len(username) <= 48):
        raise SystemExit("username must be 3-48 characters")
    if len(password) < 12:
        raise SystemExit("password must be at least 12 characters")
    fingerprint = audit_hmac_digest(
        settings.auth_jwt_secret.get_secret_value().encode(),
        f"local-account-name:v1:{username.strip().casefold()}".encode(),
    )
    database = Database(settings)
    try:
        async with database.session() as session:
            repository = SqlAlchemyAccountRepository(session)
            actor_id = f"usr_account_{uuid.uuid4().hex}"
            try:
                user = await repository.create(
                    tenant_id="tenant_public0001",
                    actor_id=actor_id,
                    role="admin",
                    username_fingerprint=fingerprint,
                    username=username.strip(),
                    password_hash=hash_password(password),
                )
            except AccountConflictError as error:
                raise SystemExit("username is unavailable") from error
            await repository.record_security_event(
                tenant_id="tenant_public0001",
                subject_fingerprint=fingerprint,
                event_type="bootstrap",
                outcome="succeeded",
                actor_id=actor_id,
                role="admin",
            )
            await session.commit()
            print(f"administrator created: {user.external_id}")
    finally:
        await database.dispose()


def main() -> None:
    args = _parser().parse_args()
    password = args.password or getpass.getpass("Administrator password: ")
    asyncio.run(_run(args.username, password))


if __name__ == "__main__":  # pragma: no cover
    main()
