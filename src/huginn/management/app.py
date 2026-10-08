"""Composition root for the synchronous management API."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import FastAPI

from huginn.management.application.services.account_admin import AccountAdminService
from huginn.management.application.services.account_management import (
    AccountAdministrationServices,
)
from huginn.management.application.services.authentication import AuthenticationService
from huginn.management.application.services.current_session_service import (
    CurrentSessionService,
)
from huginn.management.application.services.discovery_strategies import (
    ClientDiscoveryStrategyService,
)
from huginn.management.application.services.enroll_recovery_email_service import (
    EnrollRecoveryEmailService,
)
from huginn.management.application.services.forgot_password_service import (
    ForgotPasswordService,
)
from huginn.management.application.services.get_account_security_service import (
    GetAccountSecurityService,
)
from huginn.management.application.services.ideal_client_profiles import (
    IdealClientProfileService,
)
from huginn.management.application.services.provisioning import (
    IdentityProvisioningService,
)
from huginn.management.application.services.resend_verification_service import (
    ResendVerificationService,
)
from huginn.management.application.services.reset_password_service import (
    ResetPasswordService,
)
from huginn.management.application.services.service_offerings import (
    ServiceOfferingService,
)
from huginn.management.application.services.signup_service import SignupService
from huginn.management.application.services.user_profile import UserProfileService
from huginn.management.application.services.verify_email_service import (
    VerifyEmailService,
)
from huginn.management.application.throttling.failed_login import FailedLoginThrottle
from huginn.management.config import ManagementConfig, load_config
from huginn.management.persistence.database.client import (
    ManagementConnectionFactory,
    PostgresReadiness,
)
from huginn.management.persistence.database.unit_of_work import UnitOfWork
from huginn.management.persistence.repositories.account import PostgresAccountRepository
from huginn.management.persistence.repositories.account_lifecycle_proof import (
    PostgresAccountLifecycleProofRepository,
)
from huginn.management.persistence.repositories.account_recovery_identity import (
    PostgresAccountRecoveryIdentityRepository,
)
from huginn.management.persistence.repositories.discovery_strategy import (
    PostgresClientDiscoveryStrategyRepository,
)
from huginn.management.persistence.repositories.ideal_client_profile import (
    PostgresIdealClientProfileRepository,
)
from huginn.management.persistence.repositories.lifecycle_mail_outbox import (
    PostgresLifecycleMailOutboxRepository,
)
from huginn.management.persistence.repositories.lifecycle_throttle import (
    PostgresLifecycleThrottleRepository,
)
from huginn.management.persistence.repositories.professional_profile import (
    PostgresProfessionalProfileRepository,
)
from huginn.management.persistence.repositories.service_offering import (
    PostgresServiceOfferingRepository,
)
from huginn.management.persistence.repositories.session import PostgresSessionRepository
from huginn.management.persistence.repositories.user import PostgresUserRepository
from huginn.management.presentation.api.errors.handlers import (
    register_exception_handlers,
    suppress_handled_server_error_tracebacks,
)
from huginn.management.presentation.api.openapi.customization import customize_openapi
from huginn.management.presentation.api.routers.account_lifecycle import (
    router as account_lifecycle_router,
)
from huginn.management.presentation.api.routers.account_security import (
    router as account_security_router,
)
from huginn.management.presentation.api.routers.current_user import (
    router as current_user_router,
)
from huginn.management.presentation.api.routers.discovery_strategies import (
    router as discovery_strategies_router,
)
from huginn.management.presentation.api.routers.health import router as health_router
from huginn.management.presentation.api.routers.ideal_client_profiles import (
    router as ideal_client_profiles_router,
)
from huginn.management.presentation.api.routers.service_offerings import (
    router as service_offerings_router,
)
from huginn.management.presentation.api.routers.sessions import (
    router as sessions_router,
)
from huginn.management.presentation.api.static_assets import mount_frontend_assets
from huginn.management.security.encrypted_proof_cipher import EncryptedProofCipher
from huginn.management.security.passwords import hash_password, verify_password
from huginn.management.security.tokens import generate_token


@dataclass(frozen=True, slots=True)
class ManagementDependencies:
    """Immutable references to application services and infrastructure."""

    config: ManagementConfig
    readiness: Any
    unit_of_work_factory: Callable[[], Any]
    sessions_factory: Callable[[Any], Any]
    login_service: Any
    authentication_service: Any
    password_change_service: Any
    user_profile_service: Any
    service_offering_service: Any
    ideal_client_profile_service: Any
    discovery_strategy_service: Any
    current_session_service: Any = None
    signup_service: Any = None
    verify_email_service: Any = None
    resend_verification_service: Any = None
    enroll_recovery_email_service: Any = None
    forgot_password_service: Any = None
    reset_password_service: Any = None
    get_account_security_service: Any = None
    clock: Callable[[], datetime] | None = None


def create_account_administration_services(
    config: ManagementConfig | None = None,
) -> AccountAdministrationServices:
    """Wire owner CLI services lazily, without opening a database connection."""
    resolved = config if config is not None else load_config()
    factory = ManagementConnectionFactory(resolved.database_url)

    def make_uow() -> UnitOfWork:
        return UnitOfWork(factory)

    def accounts(work: UnitOfWork) -> PostgresAccountRepository:
        return PostgresAccountRepository(work.connection)

    return AccountAdministrationServices(
        provisioning=IdentityProvisioningService(
            make_uow,
            accounts_factory=accounts,
            recovery_identities_factory=lambda work: (
                PostgresAccountRecoveryIdentityRepository(work.connection)
            ),
            users_factory=lambda work: PostgresUserRepository(work.connection),
            profiles_factory=lambda work: PostgresProfessionalProfileRepository(
                work.connection
            ),
            hash_password_fn=hash_password,
        ),
        lifecycle=AccountAdminService(
            make_uow,
            accounts_factory=accounts,
            sessions_factory=lambda work: PostgresSessionRepository(work.connection),
            hash_password_fn=hash_password,
        ),
    )


def create_app(
    config: ManagementConfig | None = None,
    *,
    readiness: Any | None = None,
    unit_of_work_factory: Callable[[], Any] | None = None,
    sessions_factory: Callable[[Any], Any] | None = None,
    login_service: Any | None = None,
    authentication_service: Any | None = None,
    password_change_service: Any | None = None,
    user_profile_service: Any | None = None,
    service_offering_service: Any | None = None,
    ideal_client_profile_service: Any | None = None,
    discovery_strategy_service: Any | None = None,
    current_session_service: Any | None = None,
    clock: Callable[[], datetime] | None = None,
    throttle: Any | None = None,
) -> FastAPI:
    """Build the app and its dependency graph without opening a connection."""
    resolved_config = config if config is not None else load_config()
    probe = (
        readiness
        if readiness is not None
        else PostgresReadiness(resolved_config.database_url)
    )
    make_uow = unit_of_work_factory or (
        lambda: UnitOfWork(ManagementConnectionFactory(resolved_config.database_url))
    )
    make_sessions = sessions_factory or (
        lambda uow: PostgresSessionRepository(uow.connection)
    )
    login_throttle = throttle or FailedLoginThrottle(
        clock=clock,
        max_failures=resolved_config.login_throttle_failures,
        window=resolved_config.login_throttle_window,
    )
    auth = (
        authentication_service
        if authentication_service is not None
        else AuthenticationService(
            make_uow,
            resolved_config,
            login_throttle,
            accounts_factory=lambda uow: PostgresAccountRepository(uow.connection),
            recovery_identities_factory=lambda uow: (
                PostgresAccountRecoveryIdentityRepository(uow.connection)
            ),
            sessions_factory=make_sessions,
            clock=clock,
            token_generator=generate_token,
            verify_password_fn=verify_password,
            hash_password_fn=hash_password,
        )
    )
    login = login_service if login_service is not None else auth
    change_password = (
        password_change_service if password_change_service is not None else auth
    )
    lifecycle_arguments = {
        "cipher": EncryptedProofCipher(resolved_config.lifecycle_proof_key)
        if resolved_config.lifecycle_proof_key
        else None,
        "accounts_factory": lambda uow: PostgresAccountRepository(uow.connection),
        "users_factory": lambda uow: PostgresUserRepository(uow.connection),
        "profiles_factory": lambda uow: PostgresProfessionalProfileRepository(
            uow.connection
        ),
        "recovery_identities_factory": lambda uow: (
            PostgresAccountRecoveryIdentityRepository(uow.connection)
        ),
        "proofs_factory": lambda uow: PostgresAccountLifecycleProofRepository(
            uow.connection
        ),
        "outbox_factory": lambda uow: PostgresLifecycleMailOutboxRepository(
            uow.connection
        ),
        "throttle_factory": lambda uow: PostgresLifecycleThrottleRepository(
            uow.connection
        ),
        "sessions_factory": make_sessions,
        "clock": clock,
    }
    dependencies = ManagementDependencies(
        signup_service=SignupService(make_uow, resolved_config, **lifecycle_arguments),
        verify_email_service=VerifyEmailService(
            make_uow, resolved_config, **lifecycle_arguments
        ),
        resend_verification_service=ResendVerificationService(
            make_uow, resolved_config, **lifecycle_arguments
        ),
        enroll_recovery_email_service=EnrollRecoveryEmailService(
            make_uow, resolved_config, **lifecycle_arguments
        ),
        forgot_password_service=ForgotPasswordService(
            make_uow, resolved_config, **lifecycle_arguments
        ),
        reset_password_service=ResetPasswordService(
            make_uow, resolved_config, **lifecycle_arguments
        ),
        get_account_security_service=GetAccountSecurityService(
            make_uow, resolved_config, **lifecycle_arguments
        ),
        current_session_service=current_session_service
        if current_session_service is not None
        else CurrentSessionService(
            make_uow, sessions_factory=make_sessions, clock=clock
        ),
        config=resolved_config,
        readiness=probe,
        unit_of_work_factory=make_uow,
        sessions_factory=make_sessions,
        login_service=login,
        authentication_service=auth,
        password_change_service=change_password,
        user_profile_service=user_profile_service
        if user_profile_service is not None
        else UserProfileService(
            make_uow,
            users_factory=lambda uow: PostgresUserRepository(uow.connection),
            profiles_factory=lambda uow: PostgresProfessionalProfileRepository(
                uow.connection
            ),
        ),
        service_offering_service=service_offering_service
        if service_offering_service is not None
        else ServiceOfferingService(
            make_uow,
            offerings_factory=lambda uow: PostgresServiceOfferingRepository(
                uow.connection
            ),
        ),
        ideal_client_profile_service=ideal_client_profile_service
        if ideal_client_profile_service is not None
        else IdealClientProfileService(
            make_uow,
            profiles_factory=lambda uow: PostgresIdealClientProfileRepository(
                uow.connection
            ),
        ),
        discovery_strategy_service=discovery_strategy_service
        if discovery_strategy_service is not None
        else ClientDiscoveryStrategyService(
            make_uow,
            strategies_factory=lambda uow: PostgresClientDiscoveryStrategyRepository(
                uow.connection
            ),
            offerings_factory=lambda uow: PostgresServiceOfferingRepository(
                uow.connection
            ),
            profiles_factory=lambda uow: PostgresIdealClientProfileRepository(
                uow.connection
            ),
        ),
        clock=clock,
    )
    app = FastAPI()
    app.state.management = dependencies
    customize_openapi(app)
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(sessions_router)
    app.include_router(current_user_router)
    app.include_router(service_offerings_router)
    app.include_router(ideal_client_profiles_router)
    app.include_router(discovery_strategies_router)
    app.include_router(account_lifecycle_router)
    app.include_router(account_security_router)
    mount_frontend_assets(app, resolved_config.frontend_assets_path)
    suppress_handled_server_error_tracebacks(app)
    return app
