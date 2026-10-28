from datetime import datetime


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def text(value: object, name: str) -> None:
    require(type(value) is str and bool(value.strip()), f"{name} must be nonempty text")


def aware(value: object, name: str) -> None:
    require(
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None,
        f"{name} must include a timezone",
    )


def string_tuple(value: object, name: str, *, nonempty: bool = False) -> None:
    require(type(value) is tuple, f"{name} must be an immutable tuple")
    require(not nonempty or bool(value), f"{name} must not be empty")
    for item in value:
        text(item, name)
