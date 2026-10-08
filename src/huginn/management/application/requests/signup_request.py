"""Signup request application value."""

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class SignupRequest:
    username: str = field(repr=False)
    password: str = field(repr=False)
    first_name: str
    last_name: str
    email: str = field(repr=False)
    phone_number: str = field(repr=False)
    country_of_residence: str
    client_ip: str = field(repr=False)
    timezone: str | None = None
