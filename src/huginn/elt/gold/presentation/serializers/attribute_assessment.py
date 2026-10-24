"""Private JSON report writing for attribute assessment presentation."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import suppress
from datetime import date, datetime
from pathlib import Path
from uuid import UUID


def json_default(value: object) -> str:
    if isinstance(value, (UUID, datetime, date)):
        return str(value)
    raise TypeError(f"Unsupported report type: {type(value).__name__}")


def write_private(path: Path, value: object) -> None:
    """Atomically write JSON with mode 0600, including over public existing files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".assessment-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, default=json_default, indent=2, sort_keys=True)
            stream.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except BaseException:
        with suppress(OSError):
            os.unlink(temporary)
        raise
