"""Owner-only account administration command line interface."""

import argparse
import getpass
import sys
from collections.abc import Callable

from huginn.management.application.commands.provisioning import ProvisionIdentity
from huginn.management.application.requests.assign_account_role_request import (
    AssignAccountRoleRequest,
)
from huginn.management.application.services.account_management import (
    AccountAdministrationServices,
)
from huginn.management.domain.errors.errors import (
    ConflictError,
    ManagementDomainError,
    ValidationDomainError,
)
from huginn.management.domain.value_objects.account_role import AccountRole
from huginn.management.persistence.errors.database import DatabaseError


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
    assign_role = actions.add_parser("assign-role")
    assign_role.add_argument("--username", required=True)
    assign_role.add_argument("--role", choices=("user", "admin"), required=True)
    assign_role.add_argument(
        "--confirm", action="store_true", help="confirm this trusted role change"
    )
    return parser


def main(
    argv: list[str] | None = None,
    *,
    services_factory: Callable[[], AccountAdministrationServices] | None = None,
) -> int:
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
        if services_factory is None:
            raise RuntimeError("account services are required")
        services = services_factory()

        if args.action == "provision":
            password = _password(stdin=args.password_stdin)
            result = services.provisioning.provision(
                ProvisionIdentity(
                    args.username,
                    args.first_name,
                    args.last_name,
                    args.email,
                    args.phone_number,
                    args.country_of_residence,
                    args.timezone,
                    password,
                )
            )
            print(
                f"Provisioned account {result.username} ({result.account_id}); "
                f"User {result.user_id}; ProfessionalProfile {result.profile_id}"
            )
        elif args.action in {"enable", "disable"}:
            status = "active" if args.action == "enable" else "disabled"
            services.lifecycle.set_status(args.username, status)
            print(
                f"Account {args.username} {'enabled' if status == 'active' else 'disabled'}"
            )
        elif args.action == "reset-password":
            password = _password(stdin=args.password_stdin)
            services.lifecycle.reset_password(args.username, password)
            print(f"Password reset for account {args.username}")
        else:
            if not args.confirm:
                print(
                    "Account command failed: role changes require --confirm",
                    file=sys.stderr,
                )
                return 2
            if services.role_assignment is None:
                raise RuntimeError("account role assignment service is required")
            result = services.role_assignment.execute(
                AssignAccountRoleRequest(args.username, AccountRole(args.role))
            )
            print(f"Assigned {result.role.value} role to account {result.username}")
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
    except DatabaseError as exc:
        print(f"Account command failed: {exc.error_name}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Account command failed: {type(exc).__name__}", file=sys.stderr)
        return 2
