"""Shared Flet desktop views and local actions.

Hosts provide page/config/queue/song_list, persistence, search and optional
presentation callbacks. This module owns no accounts or remote connections.
"""
import sys
import time
import threading
import shutil
from pathlib import Path

import flet as ft
from PIL import Image
from desktop_overlay import DesktopOverlay
from desktop_media import check_player, player_name, copy_text, smtc_get_now_playing


class DesktopUI(DesktopOverlay):
    BG = "#F8F5FF"
    SURFACE = "#E8FFFCFF"
    SURFACE_2 = "#DDF2ECFF"
    SURFACE_3 = "#E8FFF0F6"
    BORDER = "#E7DCF5"
    TEXT = "#392F4A"
    MUTED = "#887C98"
    ACCENT = "#FF6FA8"
    ACCENT_2 = "#9B8AFB"
    CYAN = "#61CFE3"
    SUCCESS = "#42B982"
    WARNING = "#D99936"
    DANGER = "#E85C78"

    def _build_queue_panel(self, notice=None):
        self.song_status = ft.Text("房间离线", size=12, color=self.DANGER, weight=ft.FontWeight.W_600)
        self.song_player_ne = ft.Text("网易云检测中", size=12, color=self.MUTED)
        self.song_player_qq = ft.Text("QQ音乐检测中", size=12, color=self.MUTED)
        self.song_now = ft.Text("等待开始播放", size=20, color=self.TEXT, weight=ft.FontWeight.BOLD)
        self.song_now_meta = ft.Text("队列中的歌曲将在这里显示", size=12, color=self.MUTED)
        self.queue_count = ft.Text("0 首待播", size=12, color=self.MUTED)
        self.song_queue_list = ft.ListView(expand=True, spacing=8, padding=0)

        status_row = ft.Container(
            content=ft.Row([
                ft.Row([ft.Icon(ft.Icons.CLOUD_ROUNDED, size=15, color=self.MUTED), self.song_status], spacing=7, expand=True),
                ft.VerticalDivider(width=1, color=self.BORDER),
                ft.Row([ft.Icon(ft.Icons.AUDIO_FILE_ROUNDED, size=15, color=self.MUTED), self.song_player_ne], spacing=7, expand=True),
                ft.VerticalDivider(width=1, color=self.BORDER),
                ft.Row([ft.Icon(ft.Icons.AUDIO_FILE_ROUNDED, size=15, color=self.MUTED), self.song_player_qq], spacing=7, expand=True),
            ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            height=44, padding=ft.Padding(14, 7, 14, 7), border_radius=12,
            bgcolor=self.SURFACE_2, border=ft.Border.all(1, self.BORDER),
        )
        queue_actions = ft.Row([
            self.queue_count,
            ft.IconButton(icon=ft.Icons.PLAY_ARROW_ROUNDED, tooltip="播放下一首（同时复制歌名）", on_click=lambda e: self._queue_act("next")),
            ft.IconButton(icon=ft.Icons.SKIP_NEXT_ROUNDED, tooltip="跳过当前（不复制歌名）", on_click=lambda e: self._queue_act("skip")),
        ], spacing=2)
        queue_card = self._card(ft.Column([
            self._section_title("待播队列", "新点歌会实时出现在这里", queue_actions),
            ft.Divider(color=self.BORDER, height=20),
            self.song_queue_list,
            ft.Divider(color=self.BORDER, height=18),
            ft.Row([
                ft.Text("可以置顶、下移、复制或移除单首歌曲", size=11, color=self.MUTED),
                ft.Container(expand=True),
                ft.TextButton("清空队列", icon=ft.Icons.DELETE_SWEEP_OUTLINED, on_click=self._confirm_clear),
            ]),
        ], expand=True), expand=True)

        return ft.Container(expand=True, padding=20, content=ft.Column([
            self._section_title("直播控制台", "直播时需要的状态与操作都集中在这里"),
            notice if notice is not None else ft.Container(height=0),
            status_row, queue_card,
        ], spacing=14, expand=True))

    def _card(self, content, padding=18, expand=False):
        return ft.Container(
            content=content,
            padding=padding,
            border_radius=22,
            bgcolor=self.SURFACE,
            border=ft.Border.all(1, self.BORDER),
            shadow=ft.BoxShadow(blur_radius=24, spread_radius=0, color="#160F2D12", offset=ft.Offset(0, 7)),
            expand=expand,
        )

    def _section_title(self, title, subtitle="", trailing=None):
        left = ft.Row([
            ft.Container(width=5, height=30, border_radius=6, gradient=ft.LinearGradient(colors=[self.ACCENT, self.ACCENT_2])),
            ft.Column([
            ft.Text(title, size=18, weight=ft.FontWeight.BOLD, color=self.TEXT),
            ft.Text(subtitle, size=11, color=self.MUTED) if subtitle else ft.Container(height=0),
            ], spacing=2),
        ], spacing=10)
        controls = [left]
        if trailing:
            controls.extend([ft.Container(expand=True), trailing])
        return ft.Row(controls, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def _setting_row(self, title, subtitle, control):
        """统一设置项排版：左边标题+说明，右边控件。

        设置页要一眼能扫，所以每一项都必须有说明文字，
        光秃秃一个开关用户不知道它控制什么。
        """
        return ft.Row([
            ft.Column([
                ft.Text(title, size=13, weight=ft.FontWeight.W_600, color=self.TEXT),
                ft.Text(subtitle, size=11, color=self.MUTED) if subtitle else ft.Container(height=0),
            ], spacing=2, expand=True),
            control,
        ], vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def _settings_nav_item(self, key, icon, label):
        return ft.Container(
            content=ft.Row([
                ft.Icon(icon, size=18, color=self.MUTED),
                ft.Text(label, size=13, weight=ft.FontWeight.W_600, color=self.TEXT),
            ], spacing=10),
            padding=ft.Padding(12, 11, 12, 11),
            border_radius=14,
            bgcolor=None,
            border=ft.Border.all(1, ft.Colors.TRANSPARENT),
            on_click=lambda e, k=key: self._settings_select(k),
        )

    def _settings_select(self, key):
        """切换设置分类，并高亮左侧当前项。"""
        page = getattr(self, "_settings_pages", {}).get(key)
        if page is None:
            return
        for name, item in self._settings_nav.items():
            active = name == key
            item.bgcolor = self.SURFACE if active else None
            item.border = ft.Border.all(1, self.BORDER if active else ft.Colors.TRANSPARENT)
            row = item.content
            row.controls[0].color = self.ACCENT if active else self.MUTED
            row.controls[1].color = self.ACCENT if active else self.TEXT
            row.controls[1].weight = ft.FontWeight.BOLD if active else ft.FontWeight.W_600
        self._settings_body.content = page
        self._try_update()

    def _build_sing(self):
        self.sing_search = ft.TextField(hint_text="输入歌名或歌手，至少 2 个字", prefix_icon=ft.Icons.SEARCH_ROUNDED, expand=True, on_change=lambda e: self._sing_search_input())
        self.sing_results = ft.ListView(expand=True, spacing=6, padding=0)
        self.sing_search_status = ft.Text("输入关键词后自动搜索", size=11, color=self.MUTED)
        self.sing_count = ft.Text("共 0 首", size=13, color=self.MUTED)
        self.sing_list = ft.ListView(expand=True, spacing=2)
        self.sing_overlay_sw = ft.Switch(value=False, on_change=lambda e: self._toggle_overlay())
        self.sing_overlay_label = ft.Text("点唱板浮窗 (已关闭)", size=14)
        self.sing_ontop_sw = ft.Switch(label="置顶", value=True, on_change=lambda e: self._overlay_ontop(e.control.value))
        library = self._card(ft.Column([
            self._section_title("我的歌单", "观众可以从这些歌曲中发起点唱", self.sing_count),
            ft.Divider(color=self.BORDER, height=20), self.sing_list,
        ], expand=True), expand=4)
        add_panel = self._card(ft.Column([
            self._section_title("添加歌曲", "搜索后添加到主播歌单"),
            self.sing_search, self.sing_search_status, self.sing_results,
        ], expand=True), expand=7)
        overlay_card = self._card(ft.Row([
            ft.Icon(ft.Icons.PICTURE_IN_PICTURE_ALT_ROUNDED, color=self.ACCENT),
            ft.Column([ft.Text("点唱板浮窗", weight=ft.FontWeight.BOLD), self.sing_overlay_label], spacing=2),
            ft.Container(expand=True), self.sing_ontop_sw, self.sing_overlay_sw,
        ]), padding=14)
        return ft.Container(expand=True, padding=20, content=ft.Column([
            self._section_title("主播歌单", "维护你会唱的歌曲，点击歌曲可复制歌名"),
            ft.Row([library, add_panel], spacing=14, expand=True), overlay_card,
        ], spacing=14, expand=True))

    @staticmethod
    def _queue_head_key(item):
        """队首的稳定身份，用来判断"是不是同一首歌还卡在第一位"。

        优先用点歌时生成的 id：歌名相同但先后点两次是两首不同的条目。
        """
        if not item:
            return ""
        if item.get("id"):
            return str(item["id"])
        return "|".join(str(item.get(k, "")) for k in ("song", "requester", "time"))

    def _check_queue_head_timeout(self, now_ts):
        """队首一首歌待太久就自动移出；返回是否真的移除了。

        盯的是「**同一首歌**在第一位待了多久」，换人了就重新计时 ——
        不是"每 N 秒删掉当前第一首"。后者在正常排队时会把还没轮到的歌白删掉，
        因为主播一首歌播完之前，队首本来就会一直待着。
        """
        timeout = int(self.config.get("queue_head_timeout", 600) or 0)
        if timeout <= 0 or not self.queue:
            self._queue_head = {"key": "", "since": 0.0}
            return False
        head = self.queue[0]
        key = self._queue_head_key(head)
        state = getattr(self, "_queue_head", None) or {"key": "", "since": 0.0}
        if state.get("key") != key:
            self._queue_head = {"key": key, "since": now_ts}
            return False
        if now_ts - float(state.get("since") or now_ts) < timeout:
            return False
        self.queue.pop(0)
        self._queue_head = {"key": "", "since": 0.0}
        self._toast(f"「{head.get('song', '这首歌')}」在队首停留超过 {timeout // 60} 分钟，已自动移出队列")
        return True

    def _poll_queue_guard(self):
        """每拍看一眼队首，避免整个队列被一首歌堵死。"""
        if self._check_queue_head_timeout(time.time()):
            self._commit_queue()

    def _poll_smtc(self):
        """SMTC 监控：读取系统正在播放的歌，自动标记队列进度。

        部分播放器（网页版、某些版本号）不向系统暴露媒体信息，
        这种时候自动识别会一直匹配不上，所以留了开关让主播关掉。
        """
        if not self.config.get("smtc_enabled", True):
            return
        try:
            np = smtc_get_now_playing()
            updated = False
            now_ts = time.time()

            # 已播条目按设置自动清理（0 = 不清理，留在队列里当历史）
            retention = int(self.config.get("played_retention", 10) or 0)
            if retention > 0:
                for item in list(self.queue):
                    if item.get("status") == "played":
                        played_at = item.get("played_at", 0)
                        if played_at and (now_ts - played_at) > retention * 60:
                            self.queue.remove(item)
                            updated = True

            if np and np["title"]:
                title_lower = np["title"].lower()
                matched = next((item for item in self.queue if item.get("song", "").lower() in title_lower), None)
                if matched:
                    current = next((item for item in self.queue if item.get("status") == "playing"), None)
                    if current and current is not matched:
                        current["status"] = "played"
                        current["played_at"] = now_ts
                    if matched.get("status") != "playing":
                        matched["status"] = "playing"
                    self.song_now.value = np['title']
                    self.song_now_meta.value = f"{np.get('artist','未知歌手')} · 正在通过播放器播放"
                    self.song_now.color = self.TEXT
                    updated = True
            if updated:
                self._persist_queue(); self._refresh_queue(); self._queue_external_changed()
                try: self.page.update()
                except: pass
        except: pass

    def _toast(self, message, icon=ft.Icons.CHECK_CIRCLE_ROUNDED):
        """轻提示。

        凡是「点一下做了个动作、但界面看不出任何变化」的操作（比如复制歌名）都必须给反馈，
        否则用户根本不知道到底成没成，只能自己找地方粘贴试试。
        """
        try:
            self.page.show_dialog(ft.SnackBar(
                content=ft.Row([
                    ft.Icon(icon, color=ft.Colors.WHITE, size=18),
                    ft.Text(message, color=ft.Colors.WHITE, size=13),
                ], spacing=8, tight=True),
                bgcolor=self.ACCENT_2,
                duration=2000,
            ))
        except Exception:
            pass

    def _copy_song(self, song, artist=""):
        """复制歌名（带歌手），并明确告诉用户复制成功了。"""
        text = f"{song} {artist}".strip()
        if not text:
            return
        try:
            copy_text(text)
        except Exception:
            self._toast("复制失败，请手动选中歌名", ft.Icons.ERROR_ROUNDED)
            return
        self._toast(f"已复制：{text}")

    def _queue_act(self, action):
        """clear=清空队列；next=播下一首（并推送歌名）；skip=跳过当前（不推送）。"""
        if action == "clear":
            self.queue.clear()
            self.song_now.value = "等待开始播放"
            self.song_now_meta.value = "队列中的歌曲将在这里显示"
            self.song_now.color = self.MUTED
        elif action in ("next", "skip"):
            current = next((item for item in self.queue if item.get("status") == "playing"), None)
            if current is not None:
                current["status"] = "played" if action == "next" else "skipped"
                current["played_at"] = time.time()
            self._promote_next(play=(action == "next"))
        self._commit_queue()

    def _confirm_clear(self, e=None):
        if not self.queue:
            return
        self._confirm_dialog(
            "清空整个点歌队列？",
            f"当前共有 {len(self.queue)} 首歌曲，清空后无法恢复。",
            "确认清空",
            self._clear_confirmed,
        )

    def _clear_confirmed(self, e=None):
        self.page.pop_dialog()
        self._queue_act("clear")

    def _remove_queue_item(self, idx):
        if 0 <= idx < len(self.queue):
            self.queue.pop(idx)
            self._commit_queue()

    def _move_queue_item(self, idx, delta):
        target = idx + delta
        if 0 <= idx < len(self.queue) and 0 <= target < len(self.queue):
            self.queue[idx], self.queue[target] = self.queue[target], self.queue[idx]
            self._commit_queue()

    def _refresh_queue(self):
        """重建待播队列列表。

        ⚠️ 这里自己负责把改动刷给客户端，不靠调用方记得再 update 一次：
        收到点歌的那条处理链后面还有自动播放、浮窗同步等动作，任何一步抛异常
        都会把末尾那次 `page.update()` 一起带走（异常还会被吞掉），
        主播看到的就是「队列里没有新歌，切一下 tab 又有了」。
        """
        self.song_queue_list.controls.clear()
        playing = next((item for item in self.queue if item.get("status") == "playing"), None)
        if playing:
            self.song_now.value = playing.get("song", "未知歌曲")
            self.song_now_meta.value = f"{playing.get('artist','未知歌手')} · {playing.get('requester','匿名')} 点歌"
        waiting_count = sum(1 for item in self.queue if item.get("status") in ("waiting", "playing"))
        self.queue_count.value = f"{waiting_count} 首待播"
        if not self.queue:
            self.song_queue_list.controls.append(ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.QUEUE_MUSIC_ROUNDED, size=34, color=self.MUTED),
                    ft.Text("队列还是空的", size=14, weight=ft.FontWeight.BOLD, color=self.TEXT),
                    ft.Text("观众提交的点歌会实时出现在这里", size=11, color=self.MUTED),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=5),
                padding=30, alignment=ft.Alignment.CENTER,
            ))
            return
        for i, item in enumerate(self.queue):
            is_sing = item.get("type") == "singalong"
            sc = self.SUCCESS if item.get("status") == "playing" else self.MUTED
            st = "播放中" if item.get("status") == "playing" else ("已播放" if item.get("status") == "played" else "等待中")
            song = item['song']; artist = item.get('artist',''); plat = item.get('platform',''); fee = item.get('fee',0)
            # 平台标签
            plat_badges = []
            if "netease" in plat and "qq" in plat: plat_badges.append(ft.Container(ft.Text("双平台",size=9,color="#5570B6",weight=ft.FontWeight.BOLD),bgcolor="#E8EFFF",border_radius=12,padding=ft.Padding(6,2,6,2)))
            elif "netease" in plat: plat_badges.append(ft.Container(ft.Text("网易云",size=9,color="#B95362",weight=ft.FontWeight.BOLD),bgcolor="#FFE7E7",border_radius=12,padding=ft.Padding(6,2,6,2)))
            elif "qq" in plat: plat_badges.append(ft.Container(ft.Text("QQ",size=9,color="#34885E",weight=ft.FontWeight.BOLD),bgcolor="#E2F8EC",border_radius=12,padding=ft.Padding(6,2,6,2)))
            if fee > 0: plat_badges.append(ft.Container(ft.Text("VIP",size=9,color="#835D18",weight=ft.FontWeight.BOLD),bgcolor="#FFF1BD",border_radius=12,padding=ft.Padding(6,2,6,2)))
            actions = ft.Row([
                ft.IconButton(icon=ft.Icons.KEYBOARD_ARROW_UP_ROUNDED, icon_size=17, tooltip="上移", disabled=i == 0, on_click=lambda e, idx=i: self._move_queue_item(idx, -1)),
                ft.IconButton(icon=ft.Icons.KEYBOARD_ARROW_DOWN_ROUNDED, icon_size=17, tooltip="下移", disabled=i == len(self.queue)-1, on_click=lambda e, idx=i: self._move_queue_item(idx, 1)),
                ft.IconButton(icon=ft.Icons.CONTENT_COPY_ROUNDED, icon_size=16, tooltip="复制歌名和歌手", on_click=lambda e, s=song, a=artist: self._copy_song(s, a)),
                ft.IconButton(icon=ft.Icons.CLOSE_ROUNDED, icon_size=17, tooltip="移除", on_click=lambda e, idx=i: self._remove_queue_item(idx)),
            ], spacing=0)
            self.song_queue_list.controls.append(ft.Container(content=ft.Row([
                ft.Container(ft.Text(str(i+1), size=12, color=ft.Colors.WHITE if item.get("status") == "playing" else self.ACCENT_2, weight=ft.FontWeight.BOLD), width=32, height=32, border_radius=11, bgcolor=self.ACCENT if item.get("status") == "playing" else self.SURFACE_2, alignment=ft.Alignment.CENTER),
                ft.Column([
                    ft.Row([ft.Text(f"{song} · {artist}", size=13, color=self.TEXT, weight=ft.FontWeight.BOLD, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, expand=True)] + plat_badges, spacing=5),
                    ft.Text(f"{'点唱' if is_sing else '点歌'} · {item.get('requester','匿名')} · {item.get('time','--:--')}", size=11, color=self.MUTED),
                ], spacing=3, expand=True),
                ft.Container(ft.Text(st, size=11, color=sc, weight=ft.FontWeight.W_600), padding=ft.Padding(9,5,9,5), border_radius=12, bgcolor="#E8F8F0" if item.get("status") == "playing" else self.SURFACE_2),
                actions,
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER), padding=11, border_radius=16, bgcolor="#FFFFFF", border=ft.Border.all(1, self.BORDER)))
        self._try_update()      # 画完就发出去，不等调用方

    def _promote_next(self, play=False):
        """把队列中第一首“等待中”的歌曲置为播放中；play=True 时同时推送到播放器。

        返回被提升的条目；队列已空时返回 None 并把 Now Playing 区域复位。
        """
        waiting = next((item for item in self.queue if item.get("status") == "waiting"), None)
        if waiting is None:
            self.song_now.value = "等待开始播放"
            self.song_now_meta.value = "队列中的歌曲将在这里显示"
            self.song_now.color = self.MUTED
            return None
        waiting["status"] = "playing"
        self.song_now.value = waiting["song"]
        self.song_now_meta.value = f"{waiting.get('artist','未知歌手')} · {waiting.get('requester','匿名')} 点歌"
        self.song_now.color = self.TEXT
        if play:
            self._play_song(waiting["song"], waiting.get("artist", ""))
        return waiting

    def _play_song(self, song, artist):
        """把歌名推给播放器：默认只复制文本，不抢窗口焦点。"""
        if not self.config.get("copy_on_play", True):
            return
        self._copy_song(song, artist)

    def _sing_search_input(self):
        if self._sing_timer:
            self._sing_timer.cancel()
        self._sing_search_generation += 1
        generation = self._sing_search_generation
        keyword = self.sing_search.value.strip()
        if len(keyword) < 2:
            self.sing_results.controls.clear()
            self.sing_search_status.value = "输入至少 2 个字开始搜索"
            self._try_update()
            return
        self.sing_search_status.value = "正在搜索…"
        self._try_update()
        self._sing_timer = threading.Timer(0.22, self._sing_do_search, args=(keyword, generation))
        self._sing_timer.daemon = True
        self._sing_timer.start()

    def _render_sing_search(self, keyword, results, error):
        self.sing_results.controls.clear()
        if error:
            self.sing_search_status.value = "搜索暂时失败，请稍后重试"
            self.sing_search_status.color = self.DANGER
            return
        self.sing_search_status.value = f"“{keyword}” 找到 {len(results)} 个结果"
        self.sing_search_status.color = self.MUTED
        for s in results[:20]:
            self.sing_results.controls.append(ft.Container(content=ft.Row([
                ft.Column([ft.Text(s["name"], size=13, weight=ft.FontWeight.BOLD), ft.Text(f"{s['artists']} · {s.get('album','')}", size=11, color=self.MUTED), self._badges(s.get("platforms",[]))], spacing=2, expand=True),
                ft.FilledButton("添加", on_click=lambda e, s=s: self._sing_add(s), height=32),
            ]), padding=10, border_radius=14, bgcolor="#FFFFFF"))

    def _badges(self, platforms):
        if not platforms: return ft.Row()
        b = []
        if len(platforms) >= 2:
            b.append(ft.Container(content=ft.Text("双平台", size=9, color="#5570B6", weight=ft.FontWeight.BOLD), bgcolor="#E8EFFF", border_radius=12, padding=ft.Padding(7,2,7,2)))
        else:
            for p in platforms:
                c, tc, l = ("#FFE7E7", "#B95362", "网易云") if p == "netease" else ("#E2F8EC", "#34885E", "QQ音乐")
                b.append(ft.Container(content=ft.Text(l, size=9, color=tc, weight=ft.FontWeight.BOLD), bgcolor=c, border_radius=12, padding=ft.Padding(7,2,7,2)))
        return ft.Row(b, spacing=4)

    def _sing_add(self, song):
        entry = {"name":song["name"],"artists":song["artists"],"album":song.get("album",""),"platforms":song.get("platforms",[])}
        for e in self.song_list:
            if e["name"] == entry["name"] and e["artists"] == entry["artists"]: return
        self.song_list.append(entry); self._persist_song_list(); self._sing_refresh(); self.page.update()

    def _sing_remove(self, idx):
        if 0 <= idx < len(self.song_list): self.song_list.pop(idx); self._persist_song_list(); self._sing_refresh(); self.page.update()

    def _sing_refresh(self):
        self.sing_list.controls.clear(); self.sing_count.value = f"共 {len(self.song_list)} 首"
        for i, s in enumerate(self.song_list):
            info = ft.GestureDetector(
                content=ft.Column([
                    ft.Text(f"{i+1}. {s['name']}", size=13, weight=ft.FontWeight.BOLD),
                    ft.Text(f"{s['artists']} · {s.get('album','')}", size=11, color=self.MUTED),
                    self._badges(s.get("platforms",[])),
                ], spacing=2, expand=True),
                on_tap=lambda e, s=s: self._copy_song(s['name'], s['artists']),
            )
            self.sing_list.controls.append(ft.Container(content=ft.Row([
                info,
                ft.IconButton(icon=ft.Icons.DELETE, icon_size=16, tooltip="从歌单移除", on_click=lambda e, idx=i: self._sing_remove(idx)),
            ]), padding=10, border_radius=14, bgcolor=self.SURFACE_3 if i % 2 else None))

    def _apply_desktop_background(self):
        path = Path(self.config.get("desktop_background", ""))
        if path.is_file():
            try:
                self.background_layer.image = ft.DecorationImage(src=path.read_bytes(), fit=ft.BoxFit.COVER)
                self.background_scrim.bgcolor = "#52F8F5FF"
                self.desktop_bg_text.value = path.name
                return
            except OSError:
                pass
        self.background_layer.image = None
        self.background_scrim.bgcolor = "#00FFFFFF"
        self.desktop_bg_text.value = "使用默认背景"

    async def _pick_desktop_background(self):
        files = await self._desktop_background_picker.pick_files(
            dialog_title="选择软件背景",
            file_type=ft.FilePickerFileType.IMAGE,
            allowed_extensions=["png", "jpg", "jpeg", "webp", "bmp"],
        )
        if not files or not files[0].path:
            return
        source = Path(files[0].path)
        target = self._data_dir / ("desktop_background" + source.suffix.lower())
        try:
            if source.stat().st_size > 30_000_000:
                raise ValueError("图片文件不能超过 30 MB")
            with Image.open(source) as image:
                image.verify()
            shutil.copy2(source, target)
            self.config["desktop_background"] = str(target)
            self._persist_settings()
            self._apply_desktop_background()
            self._try_update()
        except (OSError, ValueError) as exc:
            self.desktop_bg_text.value = f"设置失败：{exc}"
            self._try_update()

    def _clear_desktop_background(self):
        self.config["desktop_background"] = ""
        self._persist_settings()
        self._apply_desktop_background()
        self._try_update()

    def _diag_notice(self, text, ok=True):
        if not hasattr(self, "diag_notice"):
            return
        self.diag_notice.value = text
        self.diag_notice.color = self.SUCCESS if ok else self.DANGER
        self.diag_notice.visible = bool(text)
        self._try_update()

    def _confirm_dialog(self, title, body, action_label, on_confirm):
        """统一的二次确认弹窗。"""
        self.page.show_dialog(ft.AlertDialog(
            modal=True,
            title=ft.Text(title),
            content=ft.Text(body),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self.page.pop_dialog()),
                ft.FilledButton(action_label, icon=ft.Icons.DELETE_FOREVER_ROUNDED, on_click=on_confirm),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        ))

    def _confirm_clear_songs(self):
        if not self.song_list:
            return
        self._confirm_dialog(
            "清空主播歌单？",
            f"当前共有 {len(self.song_list)} 首。清空后观众将无法在「主播歌单」里点唱。",
            "确认清空",
            self._clear_songs_confirmed,
        )

    def _notify_new_request(self, song, requester):
        """有人点歌时提醒主播——切走窗口时很容易漏掉。"""
        mode = self.config.get("notify_mode", "sound")
        if mode == "off":
            return
        try:
            if sys.platform == "win32":
                import winsound
                winsound.MessageBeep()
        except Exception:
            pass
        if mode == "sound_title":
            self._title_flagged = True
            try:
                self.page.title = "● 有新点歌 - SongRequest"
            except Exception:
                pass

    def _update_player_status(self):
        pt = self.set_player_dd.value
        if pt:
            r = check_player(pt); n = player_name(pt)
            self.set_player_stat.value = f"{n}运行中" if r else f"未检测到{n}"
            self.set_player_stat.color = self.SUCCESS if r else self.DANGER
        else: self.set_player_stat.value = ""
        for p, lbl in [("netease",self.song_player_ne),("qq",self.song_player_qq)]:
            r = check_player(p); n = player_name(p)
            lbl.value = f"{n}运行中" if r else f"{n}未启动"
            lbl.color = self.SUCCESS if r else self.DANGER
        try: self.page.update()
        except: pass

    def _try_update(self):
        try: self.page.update()
        except: pass
