import ast
from pathlib import Path


def test_identity_and_password_compatibility_modules_are_removed():
    package = Path(__file__).parents[2] / "src/huginn/management"
    assert not (package / "identity.py").exists()
    assert not (package / "passwords.py").exists()


def test_postgres_repositories_import_domain_and_protocol_contracts():
    package = (
        Path(__file__).parents[2] / "src/huginn/management/persistence/repositories"
    )
    expected_protocols = {
        "account.py": "AccountRepository",
        "user.py": "UserRepository",
        "professional_profile.py": "ProfessionalProfileRepository",
        "session.py": "SessionRepository",
    }

    for filename, protocol in expected_protocols.items():
        tree = ast.parse((package / filename).read_text())
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }
        assert protocol in imports, filename
        assert any(
            (node.module or "").startswith("huginn.management.domain")
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        ), filename


def test_postgres_package_does_not_reexport_repository_implementations():
    from huginn.management.persistence import repositories as postgres

    assert not hasattr(postgres, "PostgresAccountRepository")
    assert not hasattr(postgres, "PostgresSessionRepository")
