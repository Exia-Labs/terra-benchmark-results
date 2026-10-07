from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PIN = "0edf6109ea5dca3e70fdfe081d39c9ccd0f832fb"
TASK_IDS = ("333321", "130168")


class Blocked(RuntimeError):
    """An explicit preflight or protocol obstacle; never an analytical missing-data inference."""


def timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def read(path):
    return json.loads(Path(path).read_text())


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(path.name + ".writing")
    with temporary.open("w") as stream:
        os.chmod(temporary, 0o600)
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False, default=str)
        stream.write("\n")
    temporary.replace(path)


def beneath(root, path):
    root = Path(root).resolve()
    path = (root / path).resolve()
    if not path.is_relative_to(root):
        raise Blocked("Path escapes the benchmark-owned directory.")
    return path
