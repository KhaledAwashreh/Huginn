"""Pure normalization and validation of owner-provisioned identity fields."""

import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from huginn.management.domain.errors.errors import ValidationDomainError

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s.]+(?:\.[^@\s.]+)+$")
_E164_PATTERN = re.compile(r"^\+[1-9][0-9]{1,14}$")


def _required_text(field: str, value: object) -> str:
    if not isinstance(value, str):
        raise ValidationDomainError(f"invalid identity field: {field}")
    normalized = value.strip()
    if not normalized:
        raise ValidationDomainError(f"invalid identity field: {field}")
    return normalized


def validated_identity_fields(
    *,
    username: object,
    first_name: object,
    last_name: object,
    email: object,
    phone_number: object,
    country_of_residence: object,
    timezone: object,
) -> tuple[str, str, str, str, str, str, str | None]:
    """Validate and normalize identity fields without a transport framework."""
    username = _required_text("username", username)
    first_name = _required_text("first_name", first_name)
    last_name = _required_text("last_name", last_name)
    email = _required_text("email", email)
    if not 3 <= len(email) <= 254 or not _EMAIL_PATTERN.fullmatch(email):
        raise ValidationDomainError("invalid identity field: email")

    if not isinstance(phone_number, str) or not _E164_PATTERN.fullmatch(phone_number):
        raise ValidationDomainError("invalid identity field: phone_number")

    country = _required_text("country_of_residence", country_of_residence)
    if timezone is not None:
        if not isinstance(timezone, str) or len(timezone) < 1:
            raise ValidationDomainError("invalid identity field: timezone")
        try:
            ZoneInfo(timezone)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise ValidationDomainError("invalid identity field: timezone") from exc

    return (
        username,
        first_name,
        last_name,
        email,
        phone_number,
        country,
        timezone,
    )
