"""Providers for the immutable management dependency container."""

from typing import Annotated, Any

from fastapi import Depends, Request


def get_management(request: Request) -> Any:
    return request.app.state.management


Management = Annotated[Any, Depends(get_management)]


def get_authentication_service(dependencies: Management) -> Any:
    return dependencies.authentication_service


def get_login_service(dependencies: Management) -> Any:
    return dependencies.login_service


def get_password_change_service(dependencies: Management) -> Any:
    return dependencies.password_change_service


def get_readiness(dependencies: Management) -> Any:
    return dependencies.readiness
