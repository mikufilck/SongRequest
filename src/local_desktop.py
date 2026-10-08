"""Run the shared desktop views with local files and direct provider search."""
import argparse
import asyncio
import json
import os
import subprocess
import threading
from pathlib import Path

import flet as ft

from desktop_ui import DesktopUI
from json_store import load_json, save_json
from queue_rules import (QueueRejected, check_queue_rules, check_requester_limit,
                         enqueue_song, make_queue_item, waiting_entries)


class LocalDesktop(DesktopUI):
    def __init__(self, page, data_dir):
        self.page = page
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self.config = {"queue_limit": 500, "per_viewer_limit": 0,
                       "prevent_duplicate": True, "copy_on_play": True,
                       "accept_singalong": True, "overlay_enabled": False,
                       **load_json(self._data_dir / "settings.json", {}, lambda x: isinstance(x, dict))}
        self.queue = load_json(self._data_dir / "queue.json", [], lambda x: isinstance(x, list) and all(isinstance(i, dict) and isinstance(i.get("song"), str) for i in x))
        self.song_list = load_json(self._data_dir / "songs.json", [], lambda x: isinstance(x, list) and all(isinstance(i, dict) and isinstance(i.get("name"), str) and isinstance(i.get("artists"), str) for i in x))
        self._last_request_at = {}
        self._sing_timer = None
        self._sing_search_generation = 0
        self._stop_event = threading.Event()
        self._overlay_proc = None
        self._overlay_ready = False
        self._overlay_generation = 0
        self._desktop_background_picker = ft.FilePicker()
        page.services.append(self._desktop_background_picker)
        page.title = "ACGN同好会点歌版 · 本地控制台"
        page.window.width, page.window.height = 1120, 800
        page.padding = 0
        page.theme_mode = ft.ThemeMode.LIGHT
        page.bgcolor = self.BG
        page.theme = ft.Theme(color_scheme_seed=self.ACCENT, font_family="Microsoft YaHei UI")
        self.background_layer = ft.Container(expand=True)
        self.background_scrim = ft.Container(expand=True)
        self.desktop_bg_text = ft.Text("使用默认背景", color=self.MUTED)
        queue_panel = self._build_queue_panel()
        self.song_status.value, self.song_status.color = "本地队列", self.SUCCESS
        library = self._build_sing()
        settings = self._local_settings()
        self._view = ft.Container(content=queue_panel, expand=True)
        navigation = ft.Row([
            ft.TextButton("队列", on_click=lambda e: self._select_view(queue_panel)),
            ft.TextButton("歌单", on_click=lambda e: self._select_view(library)),
            ft.TextButton("设置", on_click=lambda e: self._select_view(settings)),
            ft.Container(expand=True),
            ft.FilledButton("添加点歌", on_click=self._request_dialog),
        ])
        page.add(ft.Stack([self.background_layer, self.background_scrim,
                           ft.Column([navigation, self._view], expand=True)], expand=True))
        self._refresh_queue()
        self._sing_refresh()
        self._apply_desktop_background()
        page.on_close = self._close
        page.update()

    def _select_view(self, control):
        self._view.content = control
        self._try_update()

    def _local_settings(self):
        def toggle(key, value):
            self.config[key] = value
            self._persist_settings()
        return ft.Container(padding=20, content=self._card(ft.Column([
            self._section_title("本地设置", "调整播放辅助与桌面背景"),
            self._setting_row("过滤重复歌曲", "忽略歌名版本标记及空白",
                ft.Switch(value=self.config["prevent_duplicate"], on_change=lambda e: toggle("prevent_duplicate", e.control.value))),
            self._setting_row("播放时复制歌名", "复制歌曲和歌手到剪贴板",
                ft.Switch(value=self.config["copy_on_play"], on_change=lambda e: toggle("copy_on_play", e.control.value))),
            self.desktop_bg_text,
            ft.Row([ft.TextButton("选择背景", on_click=lambda e: self.page.run_task(self._pick_desktop_background)),
                    ft.TextButton("恢复背景", on_click=lambda e: self._clear_desktop_background())]),
        ])))

    def _request_dialog(self, e=None):
        song, artist, requester = ft.TextField(label="歌曲"), ft.TextField(label="歌手"), ft.TextField(label="点歌人", value="主播")
        def submit(e):
            title = (song.value or "").strip()
            if not title:
                return
            try:
                waiting = waiting_entries(self.queue)
                check_queue_rules(self.config, waiting, title)
                check_requester_limit(self.config, waiting, requester.value or "匿名")
                item = make_queue_item({}, title, requester.value or "匿名", "song")
                item["artist"] = (artist.value or "").strip()
                enqueue_song(self.queue, item, lambda items: self._persist_queue(), self._last_request_at)
            except (QueueRejected, OSError, ValueError, TypeError) as exc:
                self._toast(str(exc), ft.Icons.ERROR_ROUNDED)
                return
            self.page.pop_dialog()
            self._refresh_queue()
            self._update_overlay()
        self.page.show_dialog(ft.AlertDialog(title=ft.Text("添加点歌"),
            content=ft.Column([song, artist, requester], tight=True),
            actions=[ft.TextButton("取消", on_click=lambda e: self.page.pop_dialog()),
                     ft.FilledButton("入队", on_click=submit)]))

    def _persist_queue(self):
        save_json(self._data_dir / "queue.json", self.queue)

    def _persist_song_list(self):
        save_json(self._data_dir / "songs.json", self.song_list)

    def _persist_settings(self):
        save_json(self._data_dir / "settings.json", self.config)

    def _queue_external_changed(self):
        pass

    def _commit_queue(self):
        self._persist_queue()
        self._refresh_queue()
        self._update_overlay()
        self._try_update()

    def _clear_songs_confirmed(self, e=None):
        self.page.pop_dialog()
        self.song_list.clear()
        self._persist_song_list()
        self._sing_refresh()
        self._try_update()

    def _schedule_ui(self, callback):
        self.page.run_task(self._invoke_ui, callback)

    async def _invoke_ui(self, callback):
        if not self._stop_event.is_set():
            callback()

    def _sing_do_search(self, keyword=None, generation=None):
        self.page.run_task(self._search_async, keyword, generation)

    async def _search_async(self, keyword, generation):
        script = Path(__file__).with_name("music_search.mjs")
        if not script.exists():
            script = Path(__file__).parents[1] / "worker/music-search.mjs"
        program = "import {searchSongs} from " + json.dumps(script.as_uri()) + "; console.log(JSON.stringify(await searchSongs(process.argv[1])));"
        def search():
            completed = subprocess.run(["node", "--input-type=module", "-e", program, "--", keyword],
                capture_output=True, text=True, encoding="utf-8", timeout=10, check=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return json.loads(completed.stdout)
        try:
            results, error = await asyncio.to_thread(search), ""
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            results, error = [], str(exc)
        if self._stop_event.is_set() or generation != self._sing_search_generation:
            return
        self._render_sing_search(keyword, results, error)
        self._try_update()

    def _close(self, e=None):
        self._stop_event.set()
        self._overlay_generation += 1
        if self._sing_timer:
            self._sing_timer.cancel()
        if self._overlay_proc and self._overlay_proc.poll() is None:
            self._overlay_proc.terminate()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "SongRequestLocal")
    args = parser.parse_args()
    ft.run(lambda page: LocalDesktop(page, args.data_dir))


if __name__ == "__main__":
    main()
