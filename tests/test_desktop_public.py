"""Shared Flet controls and local actions without network or user files."""
import asyncio
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import flet as ft
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ("app" if (ROOT / "app").is_dir() else "src")))
from desktop_ui import DesktopUI
from local_desktop import LocalDesktop
from desktop_media import _run_async
import desktop_ui


def host():
    application = DesktopUI()
    application.queue = []
    application.song_list = []
    application.config = {"copy_on_play": True}
    application._try_update = lambda: None
    application._sing_search_input = lambda: None
    application.page = SimpleNamespace(update=lambda: None, show_dialog=lambda dialog: None)
    application._build_queue_panel()
    application._build_sing()
    return application


def test_controls_render_without_private_adapters():
    app = host()
    app._refresh_queue()
    app._sing_refresh()
    assert app.queue_count.value == "0 首待播"
    assert app.sing_count.value == "共 0 首"
    app.queue = [{"song": "晴天", "artist": "周杰伦", "status": "playing", "requester": "主播"}]
    app._refresh_queue()
    assert app.song_now.value == "晴天"
    assert app.queue_count.value == "1 首待播"
    assert len(app.song_queue_list.controls) == 1


def test_queue_skip_promotes_next_and_commits():
    app = host()
    app.queue = [{"song": "A", "status": "playing"}, {"song": "B", "status": "waiting"}]
    committed = []
    app._commit_queue = lambda: committed.append(True)
    app._queue_act("skip")
    assert app.queue[0]["status"] == "skipped"
    assert app.queue[1]["status"] == "playing"
    assert app.song_now.value == "B"
    assert committed == [True]


def test_song_library_deduplicates_and_persists_through_host():
    app = host()
    persisted = []
    app._persist_song_list = lambda: persisted.append(list(app.song_list))
    song = {"name": "晴天", "artists": "周杰伦"}
    app._sing_add(song)
    app._sing_add(song)
    assert len(app.song_list) == len(persisted) == 1
    app._sing_remove(0)
    assert app.song_list == [] and persisted[-1] == []


def test_clipboard_failure_has_visible_feedback(monkeypatch):
    app = host()
    messages = []
    app._toast = lambda message, icon: messages.append(message)
    def fail(text):
        raise RuntimeError("synthetic clipboard failure")
    monkeypatch.setattr(desktop_ui, "copy_text", fail)
    app._copy_song("晴天", "周杰伦")
    assert messages == ["复制失败，请手动选中歌名"]


def test_async_media_bridge_inside_event_loop():
    async def answer():
        return 42
    async def outer():
        assert _run_async(answer()) == 42
    asyncio.run(outer())


def test_late_overlay_callback_cannot_restart_closed_view():
    app = host()
    app._stop_event = threading.Event()
    app._overlay_generation = 2
    app._overlay_proc = None
    app._send_overlay_command = lambda payload: pytest.fail("stale callback sent a command")
    app._finish_overlay_start(1)
    app._stop_event.set()
    app._finish_overlay_start(2)


def test_late_search_result_is_ignored_without_network(monkeypatch):
    app = LocalDesktop.__new__(LocalDesktop)
    app._stop_event = threading.Event()
    app._sing_search_generation = 2
    app._render_sing_search = lambda *args: pytest.fail("stale search rendered")
    app._try_update = lambda: pytest.fail("stale search updated the page")
    async def offline(*args):
        return [{"name": "old", "artists": "old"}]
    monkeypatch.setattr(asyncio, "to_thread", offline)
    asyncio.run(app._search_async("old", 1))


def test_local_desktop_uses_independent_files_and_manual_admission(tmp_path):
    dialogs = []
    page = SimpleNamespace(window=SimpleNamespace(), services=[],
        add=lambda control: None, update=lambda: None,
        show_dialog=dialogs.append, pop_dialog=lambda: dialogs.pop())
    app = LocalDesktop(page, tmp_path)
    app._request_dialog()
    dialog = dialogs[-1]
    dialog.content.controls[0].value = "晴天"
    dialog.content.controls[1].value = "周杰伦"
    dialog.actions[1].on_click(None)
    assert len(app.queue) == 1 and app.queue[0]["artist"] == "周杰伦"
    assert (tmp_path / "queue.json").is_file()
    assert not (tmp_path / "config.json").exists()
    app._request_dialog()
    dialog = dialogs[-1]
    dialog.content.controls[0].value = "晴天"
    dialog.actions[1].on_click(None)
    assert len(app.queue) == 1
    app._close()
