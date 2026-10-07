from collections.abc import Mapping

type RawJsonValue = (
    None
    | bool
    | int
    | float
    | str
    | tuple[RawJsonValue, ...]
    | Mapping[str, RawJsonValue]
)
