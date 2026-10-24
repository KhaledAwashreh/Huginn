"""Filesystem implementation for Silver JSON report output."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from uuid import UUID


class FilesystemJsonReportWriter:
    def prepare_summary_path(self, path: str | Path | None) -> Path | None:
        if path is None:
            return None
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and not target.is_file():
            raise IsADirectoryError("summary path must name a file")
        if target.exists() and not os.access(target, os.W_OK):
            raise PermissionError("summary path is not writable")
        descriptor, probe = tempfile.mkstemp(prefix=".currentness-", dir=target.parent)
        os.close(descriptor)
        Path(probe).unlink()
        return target

    def write_json(self, path: str | Path, value: object) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(value, indent=2, ensure_ascii=False, default=_json_default)
            + "\n",
            encoding="utf-8",
        )

    def write_summary(self, path: Path | None, report: Mapping[str, object]) -> None:
        if path is None:
            return
        descriptor, temporary = tempfile.mkstemp(
            prefix=".currentness-", dir=path.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                json.dump(report, output, indent=2, ensure_ascii=False)
                output.write("\n")
            os.replace(temporary, path)
        except BaseException:
            with suppress(OSError):
                os.unlink(temporary)
            raise


def _json_default(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, UUID):
        return str(value)
    raise TypeError(f"unsupported report value: {type(value).__name__}")
