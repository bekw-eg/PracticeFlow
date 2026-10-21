"""Create the first organization and Super Admin: python -m app.cli.bootstrap."""
from __future__ import annotations

import argparse
import getpass
import hmac
import sys
import warnings
from typing import NoReturn

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError


class BootstrapInputError(ValueError):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        # argparse normally echoes unrecognized arguments, which might include
        # a mistakenly supplied password. Never reproduce argument values.
        self.exit(2, "Invalid command options. Use --help. Passwords must use hidden input or --password-stdin.\n")


def read_password(*, password_stdin: bool) -> str:
    from app.core.security import validate_password

    if password_stdin:
        if sys.stdin.isatty():
            raise BootstrapInputError("--password-stdin requires a protected pipe; omit it for hidden terminal input.")
        # Bounded read; the producer must close stdin. Accept exactly one line,
        # preserving spaces and every password byte except its line terminator.
        password = sys.stdin.read(75)
        if password.endswith("\r\n"):
            password = password[:-2]
        elif password.endswith("\n"):
            password = password[:-1]
        if "\n" in password or "\r" in password:
            raise BootstrapInputError("Provide exactly one password line on stdin.")
    else:
        with warnings.catch_warnings():
            # getpass must never fall back to an echoed read on an unsafe tty.
            warnings.simplefilter("error", getpass.GetPassWarning)
            try:
                password = getpass.getpass("Super Admin password: ")
                confirmation = getpass.getpass("Confirm password: ")
            except getpass.GetPassWarning:
                raise BootstrapInputError("Hidden terminal input is unavailable. Use a protected pipe with --password-stdin.") from None
        if not hmac.compare_digest(password.encode("utf-8"), confirmation.encode("utf-8")):
            raise BootstrapInputError("Passwords do not match.")
    try:
        return validate_password(password)
    except ValueError as exc:
        raise BootstrapInputError(str(exc)) from None


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(allow_abbrev=False, description="Bootstrap an empty, migrated database without seed data. Existing identities are never modified.")
    parser.add_argument("--organization-name", required=True)
    parser.add_argument("--organization-slug", required=True)
    parser.add_argument("--admin-email", required=True)
    parser.add_argument("--admin-full-name", required=True)
    parser.add_argument("--password-stdin", action="store_true", help="Read one password line from a protected stdin pipe, closed by its producer.")
    args = parser.parse_args(argv)
    engine = None
    try:
        # Lazy imports keep invalid production Settings out of tracebacks and
        # still run the exact same safety validation as the API and workers.
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session

        from app.core.config import settings
        from app.services.bootstrap_service import BootstrapConflict, BootstrapIdentity, bootstrap

        if not settings.is_production:
            print("Bootstrap requires ENV=production with validated deployment settings. Development seed is not used.", file=sys.stderr)
            return 1
        identity = BootstrapIdentity(
            organization_name=args.organization_name,
            organization_slug=args.organization_slug,
            admin_email=args.admin_email,
            admin_full_name=args.admin_full_name,
        )
        engine = create_engine(settings.DATABASE_URL, hide_parameters=True, pool_pre_ping=True)
        with Session(engine) as db:
            try:
                result = bootstrap(db, identity, lambda: read_password(password_stdin=args.password_stdin))
            except BootstrapConflict as exc:
                print(f"Bootstrap refused: {exc}", file=sys.stderr)
                return 1
        if result.created:
            print("Created the first organization and Super Admin. MFA enrollment is required at first login.")
        else:
            print("Already initialized with this active Super Admin and organization. No changes made; password and MFA preserved.")
        print(f"organization_id={result.organization_id} user_id={result.user_id}")
        return 0
    except ValidationError as exc:
        fields = sorted({".".join(map(str, error["loc"])) or "application settings" for error in exc.errors(include_input=False)})
        print("Invalid configuration or identity fields: " + ", ".join(fields) + ". Check production settings and --help.", file=sys.stderr)
    except BootstrapInputError as exc:
        print(f"Password input rejected: {exc}", file=sys.stderr)
    except (EOFError, KeyboardInterrupt):
        print("Bootstrap cancelled. No partial bootstrap writes are kept.", file=sys.stderr)
    except SQLAlchemyError as exc:
        code = getattr(getattr(exc, "orig", None), "sqlstate", None)
        if code == "55P03":
            message = "Database is busy with another writer. Retry after it finishes."
        elif code in {"42P01", "42703"}:
            message = "Database schema is not ready. Apply alembic upgrade head before bootstrap."
        else:
            message = "Database operation could not be confirmed. Check connectivity, migrations and permissions; retry the same identity safely."
        print(message, file=sys.stderr)
    except Exception:
        # Database/configuration errors and tracebacks can contain credentials
        # or bound values. Do not print arbitrary exception strings or locals.
        print("Bootstrap failed. No partial bootstrap writes are kept. Check deployment configuration and retry the same identity.", file=sys.stderr)
    finally:
        if engine is not None:
            engine.dispose()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
