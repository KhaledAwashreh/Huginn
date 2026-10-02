"""Owner-only account administration command line interface."""

import argparse
import getpass
import sys

from huginn.management.config import load_config
from huginn.management.database import ManagementConnectionFactory, UnitOfWork
from huginn.management.domain import (
    ConflictError,
    ManagementDomainError,
    ValidationDomainError,
)
from huginn.management.identity import AccountAdminService, IdentityProvisioningService


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        del message
        raise ValueError("invalid command arguments")


def _password(*, stdin: bool) -> str:
    if stdin:
        first, second = sys.stdin.readline(), sys.stdin.readline()
        if not first or not second:
            raise ValueError("password was not supplied twice on stdin")
        first, second = first.rstrip("\r\n"), second.rstrip("\r\n")
        if first != second:
            raise ValueError("passwords do not match")
        return first
    first = getpass.getpass("Password: ")
    second = getpass.getpass("Confirm password: ")
    if first != second:
        raise ValueError("passwords do not match")
    return first


def _parser() -> argparse.ArgumentParser:
    parser = _SafeArgumentParser(
        prog="python -m huginn.management.admin", allow_abbrev=False
    )
    resources = parser.add_subparsers(dest="resource", required=True)
    account = resources.add_parser("account")
    actions = account.add_subparsers(dest="action", required=True)
    provision = actions.add_parser("provision")
    for name in (
        "username",
        "first-name",
        "last-name",
        "email",
        "phone-number",
        "country-of-residence",
    ):
        provision.add_argument(f"--{name}", required=True)
    provision.add_argument("--timezone")
    provision.add_argument("--password-stdin", action="store_true")
    for action in ("enable", "disable", "reset-password"):
        command = actions.add_parser(action)
        command.add_argument("--username", required=True)
        if action == "reset-password":
            command.add_argument("--password-stdin", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if any(
        token == "--password" or token.startswith("--password=") for token in arguments
    ):
        print(
            "Account command failed: passwords cannot be supplied as arguments",
            file=sys.stderr,
        )
        return 2
    try:
        args = _parser().parse_args(arguments)
    except ValueError:
        print("Account command failed: invalid command arguments", file=sys.stderr)
        return 2

    try:
        config = load_config()
        factory = ManagementConnectionFactory(config.database_url)

        def uow():
            return UnitOfWork(factory)

        if args.action == "provision":
            password = _password(stdin=args.password_stdin)
            result = IdentityProvisioningService(uow).provision(
                username=args.username,
                first_name=args.first_name,
                last_name=args.last_name,
                email=args.email,
                phone_number=args.phone_number,
                country_of_residence=args.country_of_residence,
                timezone=args.timezone,
                password=password,
            )
            print(
                f"Provisioned account {result.username} ({result.account_id}); "
                f"User {result.user_id}; ProfessionalProfile {result.profile_id}"
            )
        elif args.action in {"enable", "disable"}:
            status = "active" if args.action == "enable" else "disabled"
            AccountAdminService(uow).set_status(args.username, status)
            print(
                f"Account {args.username} {'enabled' if status == 'active' else 'disabled'}"
            )
        else:
            password = _password(stdin=args.password_stdin)
            AccountAdminService(uow).reset_password(args.username, password)
            print(f"Password reset for account {args.username}")
        return 0
    except ConflictError:
        print("Account command failed: username already in use", file=sys.stderr)
        return 2
    except ValidationDomainError as exc:
        print(f"Account command failed: {exc}", file=sys.stderr)
        return 2
    except ManagementDomainError:
        print("Account command failed: account operation failed", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Account command failed: {type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
