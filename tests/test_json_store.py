"""Public JSON I/O regressions use temporary files only."""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ("app" if (ROOT / "app").is_dir() else "src")))
import json_store as store


def test_concurrent_writes_remain_complete_and_clean(tmp_path):
    path = tmp_path / "songs.json"
    values = [{"writer": i, "songs": ["歌曲" * 100] * 10} for i in range(20)]
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(lambda value: store.save_json(path, value), values))
    assert json.loads(path.read_text(encoding="utf-8")) in values
    assert not list(tmp_path.glob("*.tmp"))


def test_failed_write_preserves_previous_document(tmp_path):
    path = tmp_path / "songs.json"
    store.save_json(path, {"original": True})
    with pytest.raises(TypeError):
        store.save_json(path, {"invalid": object()})
    assert store.load_json(path) == {"original": True}
    assert not list(tmp_path.glob("*.tmp"))


def test_corrupt_file_is_preserved_before_replacement(tmp_path):
    path = tmp_path / "songs.json"
    path.write_bytes(b"{broken")
    assert store.load_json(path, []) == []
    assert path.read_bytes() == b"{broken"
    backups = list(tmp_path.glob("*.corrupt-*"))
    assert len(backups) == 1 and backups[0].read_bytes() == b"{broken"
    store.save_json(path, [])
    assert store.load_json(path) == []


def test_failed_preservation_blocks_overwrite(tmp_path, monkeypatch):
    path = tmp_path / "songs.json"
    path.write_bytes(b"{broken")
    def fail(*args):
        raise OSError("backup denied")
    monkeypatch.setattr(store.shutil, "copy2", fail)
    assert store.load_json(path, []) == []
    with pytest.raises(OSError, match="停止覆盖"):
        store.save_json(path, [])
    assert path.read_bytes() == b"{broken"


def test_schema_failure_and_defaults_do_not_share_mutable_state(tmp_path):
    path = tmp_path / "songs.json"
    path.write_text("{}", encoding="utf-8")
    defaults = [{"name": "歌曲"}]
    result = store.load_json(path, defaults, lambda data: isinstance(data, list))
    result[0]["name"] = "changed"
    assert defaults == [{"name": "歌曲"}]
    assert list(tmp_path.glob("*.corrupt-*"))
