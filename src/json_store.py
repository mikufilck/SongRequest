"""Thread-safe atomic JSON I/O with corrupt-file preservation and diagnostics."""
import copy
import json
import os
import tempfile
import threading
import shutil
import uuid
from datetime import datetime
from pathlib import Path

_IO_LOCK = threading.RLock()
_BAD_PATHS = set()
_PRESERVED_PATHS = set()
_DIAGNOSTICS = []

def _preserve_bad_file(path, reason):
    path = Path(path).resolve()
    if path not in _BAD_PATHS:
        _BAD_PATHS.add(path)
        backup = path.with_name(path.name + ".corrupt-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
        preserved = False
        try:
            shutil.copy2(path, backup)
            preserved = True
            _PRESERVED_PATHS.add(path)
        except OSError:
            pass
        _DIAGNOSTICS.append({"file": path.name, "reason": reason, "preserved": preserved})

def take_diagnostics():
    with _IO_LOCK:
        items = list(_DIAGNOSTICS)
        _DIAGNOSTICS.clear()
        return items

def load_json(path, default=None, validator=None):
    with _IO_LOCK:
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            if validator and not validator(data):
                raise ValueError("schema")
            _BAD_PATHS.discard(Path(path).resolve())
            return data
        except FileNotFoundError:
            pass
        except (OSError, ValueError, UnicodeError, RecursionError) as exc:
            _preserve_bad_file(path, "schema" if str(exc) == "schema" else type(exc).__name__)
        return copy.deepcopy(default if default is not None else {})

def save_json(path, data):
    with _IO_LOCK:
        _save_json(path, data)

def _save_json(path, data):
    # 每次写入使用独立临时文件，UI 与后台线程并发保存时不会互相覆盖临时文件。
    path = Path(path)
    if path.resolve() in _BAD_PATHS and path.exists() and path.resolve() not in _PRESERVED_PATHS:
        raise OSError("原文件尚未成功保全，停止覆盖")
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=path.name + ".", suffix=".tmp", delete=False) as f:
            temp_path = Path(f.name)
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
