"""Offline tests for song deduplication, limits and durable admission."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ("app" if (ROOT / "app").is_dir() else "src")))
from queue_rules import QueueRejected, check_queue_rules, check_requester_limit, enqueue_song, make_queue_item, song_key, waiting_entries


def test_deduplication_ignores_edition_brackets_and_spacing():
    assert song_key("晴天 （现场版）") == song_key(" 晴 天 ")
    with pytest.raises(QueueRejected, match="已经在队列"):
        check_queue_rules({}, [{"song": "晴天 (现场版)"}], "晴天")


def test_history_does_not_consume_queue_or_personal_limits():
    items = [{"status": "played", "requester": "小明"}, {"status": "skipped", "requester": "小明"}]
    waiting = waiting_entries(items)
    assert waiting == []
    check_queue_rules({"queue_limit": 1}, waiting, "晴天")
    check_requester_limit({"per_viewer_limit": 1}, waiting, "小明")


def test_full_queue_closed_singalong_and_personal_limit_reject():
    with pytest.raises(QueueRejected, match="队列已满"):
        check_queue_rules({"queue_limit": 1}, [{"song": "A"}], "B")
    with pytest.raises(QueueRejected, match="没有开放点唱"):
        check_queue_rules({"accept_singalong": False}, [], "B", "singalong")
    with pytest.raises(QueueRejected, match="已点过"):
        check_requester_limit({"per_viewer_limit": 1}, [{"requester": "小明"}], "小明")


def test_success_is_persisted_before_admission_returns(tmp_path):
    file = tmp_path / "queue.json"
    items, cooldowns = [], {}
    item = make_queue_item({"artist": "歌手", "unexpected": "ignore"}, "晴天", "小明")
    result = enqueue_song(items, item, lambda value: file.write_text(json.dumps(value), encoding="utf-8"), cooldowns, cooldown=60, now=100)
    assert json.loads(file.read_text(encoding="utf-8")) == items == [result]
    assert cooldowns == {"小明": 100}
    assert "unexpected" not in item


def test_persistence_failure_restores_existing_cooldown():
    items, cooldowns = [], {"小明": 7}
    item = make_queue_item({}, "晴天", "小明")
    def fail(value):
        raise OSError("synthetic disk failure")
    with pytest.raises(OSError):
        enqueue_song(items, item, fail, cooldowns, cooldown=60, now=100)
    assert items == [] and cooldowns == {"小明": 7}


def test_cooldown_rejection_does_not_save_or_change_queue():
    items, cooldowns = [], {"小明": 95}
    item = make_queue_item({}, "晴天", "小明")
    def unexpected_save(value):
        pytest.fail("rejected request must not persist")
    with pytest.raises(QueueRejected, match="太频繁"):
        enqueue_song(items, item, unexpected_save, cooldowns, cooldown=60, now=100)
    assert items == [] and cooldowns == {"小明": 95}
