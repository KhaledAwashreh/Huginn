import ast
import inspect
from typing import Any, get_type_hints

from huginn.management import domain, primitives, repository_ports


def test_application_and_domain_modules_do_not_import_flask():
    for module in (domain, primitives, repository_ports):
        syntax = ast.parse(inspect.getsource(module))
        imported = {
            alias.name
            for node in ast.walk(syntax)
            if isinstance(node, ast.Import)
            for alias in node.names
        } | {
            node.module for node in ast.walk(syntax) if isinstance(node, ast.ImportFrom)
        }
        assert all(
            name != "flask" and not name.startswith("flask.") for name in imported
        )


def test_page_result_and_principal_are_typed_immutable_values():
    from uuid import uuid4

    from huginn.management.domain import Page, Principal

    principal = Principal(account_id=uuid4(), user_id=uuid4())
    page = Page(items=("a", "b"), offset=5, limit=2, has_more=True)
    assert principal.user_id
    assert page.items == ("a", "b")
    assert page.offset == 5
    assert page.has_more is True


def test_domain_errors_have_stable_types_and_safe_messages():
    from huginn.management.domain import ConflictError, NotFoundError

    assert str(ConflictError("already exists")) == "already exists"
    assert issubclass(NotFoundError, Exception)


def test_repository_ports_are_protocols():
    from huginn.management.repository_ports import (
        AccountRepository,
        ClientDiscoveryStrategyRepository,
        IdealClientProfileRepository,
        ProfessionalProfileRepository,
        ServiceOfferingRepository,
        SessionRepository,
        UserRepository,
    )

    for port in (
        AccountRepository,
        ClientDiscoveryStrategyRepository,
        IdealClientProfileRepository,
        ProfessionalProfileRepository,
        ServiceOfferingRepository,
        SessionRepository,
        UserRepository,
    ):
        assert getattr(port, "_is_protocol", False)


def test_repository_ports_cover_documented_operations_with_typed_results():
    from huginn.management import repository_ports as ports
    from huginn.management.domain import (
        Account,
        ClientDiscoveryStrategy,
        IdealClientProfile,
        ProfessionalProfile,
        ServiceOffering,
        Session,
        User,
    )

    expected = {
        ports.AccountRepository: {
            "get_by_normalized_username",
            "create",
            "set_status",
            "set_password_hash",
        },
        ports.UserRepository: {"create", "update"},
        ports.ProfessionalProfileRepository: {"create", "update"},
        ports.SessionRepository: {
            "create",
            "get_by_token_digest",
            "revoke_current",
            "revoke_for_account",
        },
        ports.ServiceOfferingRepository: {
            "create",
            "get_owned",
            "list_owned",
            "update_owned",
            "delete_owned",
        },
        ports.IdealClientProfileRepository: {
            "create",
            "get_owned",
            "list_owned",
            "update_owned",
            "delete_owned",
        },
        ports.ClientDiscoveryStrategyRepository: {
            "create",
            "get_owned",
            "list_owned",
            "update_owned",
            "delete_owned",
        },
    }
    results = {
        ports.AccountRepository: Account,
        ports.UserRepository: User,
        ports.ProfessionalProfileRepository: ProfessionalProfile,
        ports.SessionRepository: Session,
        ports.ServiceOfferingRepository: ServiceOffering,
        ports.IdealClientProfileRepository: IdealClientProfile,
        ports.ClientDiscoveryStrategyRepository: ClientDiscoveryStrategy,
    }
    for port, methods in expected.items():
        for method_name in methods:
            method = getattr(port, method_name)
            assert callable(method), f"{port.__name__}.{method_name} is missing"
            hints = get_type_hints(method)
            assert hints.get("return") not in (object, Any, None)
            assert all(
                annotation not in (object, Any)
                for name, annotation in hints.items()
                if name != "return"
            )
        assert results[port].__module__ == "huginn.management.domain"
