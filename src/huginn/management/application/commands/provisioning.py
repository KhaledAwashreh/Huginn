"""Domain command for owner-controlled identity provisioning."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProvisionIdentity:
    """Use `None` to generate an opaque account handle."""

    username: str | None
    first_name: str
    last_name: str
    email: str
    phone_number: str
    country_of_residence: str
    timezone: str | None
    password: str = field(repr=False)
