"""Documented owner-administration module launcher."""

from huginn.management.app import create_account_administration_services
from huginn.management.presentation.cli import account_admin


def main(argv: list[str] | None = None) -> int:
    return account_admin.main(
        argv, services_factory=create_account_administration_services
    )


if __name__ == "__main__":
    raise SystemExit(main())
