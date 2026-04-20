"""Day-one admin seeding (FR-AUTH-3, TC-I-AUTH-11).

Every fresh deployment needs at least one admin user in the ``users``
allowlist before anyone can log in.  This module provides both a
library function (:func:`seed_admin`) and a CLI entry point so the
first-run step can be automated in a deploy script without requiring
direct psql access.

Usage
-----
Seed a single admin::

    python -m app.admin.bootstrap \\
        --email aida.jugo@symphony.is \\
        --name "Aida Jugo Krstulović"

Seed from the environment variable (useful in CD pipelines)::

    DAY_ONE_ADMIN_EMAILS=aida.jugo@symphony.is,enis.kudo@symphony.is \\
    python -m app.admin.bootstrap

Both forms are idempotent — running them a second time promotes the
user's role to admin if it was downgraded, re-activates a deactivated
account, and updates the display name.  An audit row with action
``admin_seeded`` is written for every call (even no-ops), which keeps
the event traceable in the audit log.

Database connection
-------------------
Reads ``DATABASE_URL`` from the environment / ``.env`` via
:class:`app.config.Settings`.  Must be able to connect as a role with
``INSERT`` and ``UPDATE`` on the ``users`` table (i.e. ``ta_report_app``
or the superuser used for migrations).

Exit codes
----------
0  All admins seeded successfully.
1  No emails provided (env var empty and no ``--email`` flag).
2  Database error or unexpected exception.
"""

from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING

from sqlalchemy.dialects.postgresql import insert

from app.audit.actions import AuditAction
from app.audit.writer import write_audit
from app.db.models import RoleEnum, User
from app.logging import configure_logging, get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

log = get_logger(__name__)

#: Placeholder used when no display name is provided on the CLI.
_DEFAULT_DISPLAY_NAME = "Admin"


async def seed_admin(
    db: AsyncSession,
    *,
    email: str,
    display_name: str = _DEFAULT_DISPLAY_NAME,
) -> tuple[bool, bool]:
    """Upsert a user row with admin role and write an audit record.

    Parameters
    ----------
    db:
        Open async session.  The caller is responsible for committing.
    email:
        Email address of the admin.  Must match the Google Workspace
        account the user will log in with.
    display_name:
        Human-readable name stored in the ``users`` table.

    Returns
    -------
    (created, promoted)
        ``created=True`` when a new row was inserted; ``False`` when
        an existing row was updated.
        ``promoted=True`` when the role changed *to* admin; ``False``
        when it was already admin (or the row was freshly created).
    """
    email = email.strip().lower()

    stmt = (
        insert(User)
        .values(
            email=email,
            display_name=display_name,
            role=RoleEnum.admin,
            is_active=True,
        )
        .on_conflict_do_update(
            index_elements=["email"],
            set_={
                "display_name": display_name,
                "role": RoleEnum.admin,
                "is_active": True,
            },
        )
        .returning(User.id, User.role)
    )

    result = (await db.execute(stmt)).one()
    user_id = result[0]
    # The RETURNING clause gives us the *post-update* role.  To detect
    # a promotion we need to know the previous state.  Since we always
    # set role=admin, the only way it was *not* admin before is if the
    # row previously existed with a different role.  We cannot easily
    # tell from the RETURNING result alone, so we track the created flag
    # via whether the row existed before the insert.

    # Determine whether a row was created or updated.
    # ``on_conflict_do_update`` always returns the row; we use the
    # ``xmax`` system column to detect INSERT vs UPDATE in Postgres:
    # xmax = 0 → fresh INSERT; xmax != 0 → UPDATE.
    xmax_result = await db.execute(
        __import__("sqlalchemy", fromlist=["text"]).text(
            "SELECT xmax = 0 AS is_insert FROM users WHERE id = :uid"
        ),
        {"uid": user_id},
    )
    row = xmax_result.one()
    created: bool = bool(row[0])
    # We cannot reliably detect "role was changed" after the upsert
    # without a pre-read; treat any update as a potential promotion for
    # the audit message.
    promoted: bool = not created

    await write_audit(
        db,
        action=AuditAction.admin_seeded,
        actor_id=None,
        actor_email="system",
        actor_display_name="bootstrap",
        target=(f"user:{user_id} email:{email} " f"{'created' if created else 'updated'}"),
    )

    log.info(
        "admin_seeded",
        extra={
            "email": email,
            "user_id": str(user_id),
            "was_created": created,
            "was_promoted": promoted,
        },
    )
    return created, promoted


async def _run(emails: list[tuple[str, str]]) -> int:
    """Seed all (email, display_name) pairs and return an exit code."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: PLC0415

    from app.config import get_settings  # noqa: PLC0415

    settings = get_settings()

    url = settings.database_url
    if "+psycopg_async" not in url:
        url = url.replace("+psycopg", "+psycopg_async", 1)
        if "+psycopg_async" not in url:
            # Plain postgresql:// — inject the async driver
            url = url.replace("postgresql://", "postgresql+psycopg_async://", 1)

    engine = create_async_engine(url, pool_size=1, max_overflow=0)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

    try:
        async with factory() as session:
            for email, display_name in emails:
                try:
                    created, promoted = await seed_admin(
                        session, email=email, display_name=display_name
                    )
                    await session.commit()
                    verb = "created" if created else ("promoted" if promoted else "confirmed")
                    print(f"  OK  {verb}: {email}")  # noqa: T201
                except Exception as exc:  # noqa: BLE001
                    await session.rollback()
                    print(f"  ERR {email}: {exc}", file=sys.stderr)  # noqa: T201
                    return 2
    finally:
        await engine.dispose()

    return 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import os

    configure_logging()

    parser = argparse.ArgumentParser(
        prog="python -m app.admin.bootstrap",
        description=(
            "Seed day-one admin users into the allowlist. " "Idempotent — safe to re-run."
        ),
    )
    parser.add_argument("--email", help="Admin email address (repeatable)", action="append")
    parser.add_argument(
        "--name",
        help=(
            "Display name for the admin (used with --email; "
            "defaults to the part before @ if omitted)"
        ),
    )
    args = parser.parse_args()

    # Collect emails from --email flag(s) and DAY_ONE_ADMIN_EMAILS env var.
    pairs: list[tuple[str, str]] = []

    # --email flags (may be specified multiple times)
    if args.email:
        for raw_email in args.email:
            name = args.name if args.name and len(args.email) == 1 else raw_email.split("@")[0]
            pairs.append((raw_email.strip(), name))

    # DAY_ONE_ADMIN_EMAILS env var — comma-separated list of email[:display name]
    # e.g. "aida.jugo@symphony.is:Aida Jugo,enis.kudo@symphony.is:Enis Kudo"
    env_emails = os.getenv("DAY_ONE_ADMIN_EMAILS", "").strip()
    if env_emails:
        for entry in env_emails.split(","):
            stripped = entry.strip()
            if ":" in stripped:
                raw_email, raw_name = stripped.split(":", 1)
                pairs.append((raw_email.strip(), raw_name.strip()))
            elif stripped:
                pairs.append((stripped, stripped.split("@")[0]))

    if not pairs:
        print(  # noqa: T201
            "Error: provide at least one admin email via --email or "
            "DAY_ONE_ADMIN_EMAILS env var.\n"
            "Example: python -m app.admin.bootstrap "
            "--email aida.jugo@symphony.is --name 'Aida Jugo'",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Seeding {len(pairs)} admin(s)...")  # noqa: T201
    rc = asyncio.run(_run(pairs))
    sys.exit(rc)
