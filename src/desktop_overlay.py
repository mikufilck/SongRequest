"""Local overlay process lifecycle and loopback socket commands."""
import json
import subprocess
import sys
import threading
from pathlib import Path


class DesktopOverlay:
    def _overlay_ontop(self, value):
        """切换浮窗置顶状态并持久化，重启后仍生效。"""
        self.config["overlay_ontop"] = bool(value)
        self._persist_settings()
        self._send_overlay_command({"action": "ontop", "value": bool(value)})

    def _toggle_overlay(self):
        enabled = self.sing_overlay_sw.value
        self.config["overlay_enabled"] = enabled
        self._persist_settings()
        if enabled:
            self._start_overlay()
        else:
            self._overlay_generation += 1
            self._send_overlay_command({"action": "close"})
            if self._overlay_proc:
                try:
                    self._overlay_proc.terminate()
                except Exception:
                    pass
            self._overlay_proc = None
            self._overlay_ready = False
            self.sing_overlay_label.value = "点唱板浮窗 (已关闭)"
        self._try_update()

    def _overlay_command(self):
        if getattr(sys, "frozen", False):
            executable = Path(sys.executable).resolve().parent / "overlay.exe"
            return [str(executable)] if executable.exists() else None
        # 开发环境优先使用当前解释器；未安装 PySide6 时回退到已打包的浮窗。
        try:
            import importlib.util
            if importlib.util.find_spec("PySide6") is not None:
                return [sys.executable, str(Path(__file__).resolve().parent / "overlay.py")]
        except Exception:
            pass
        project_dir = Path(__file__).resolve().parent.parent
        for executable in (
            project_dir / "dist" / "SongRequest" / "overlay.exe",
            project_dir / "dist" / "overlay" / "overlay.exe",
        ):
            if executable.exists():
                return [str(executable)]
        return None

    def _send_overlay_command(self, payload, timeout=0.45):
        import socket
        try:
            with socket.create_connection(("127.0.0.1", 19527), timeout=timeout) as client:
                client.sendall(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            return True
        except OSError:
            return False

    def _start_overlay(self):
        if self._stop_event.is_set() or not self.config.get("overlay_enabled", False):
            return
        self._overlay_generation += 1
        generation = self._overlay_generation
        if self._send_overlay_command({"action": "ping"}):
            self._overlay_ready = True
            self.sing_overlay_sw.value = True
            self.sing_overlay_label.value = "点唱板浮窗 (已开启)"
            self._update_overlay()
            self._overlay_ontop(self.sing_ontop_sw.value)
            self._try_update()
            return
        if self._overlay_proc and self._overlay_proc.poll() is None:
            self._schedule_overlay_probe(generation)
            return
        cmd = self._overlay_command()
        if not cmd:
            self.sing_overlay_sw.value = False
            self.sing_overlay_label.value = "点唱板浮窗 (缺少 PySide6 或 overlay.exe)"
            self.config["overlay_enabled"] = False
            self._persist_settings()
            self._overlay_proc = None
            self._try_update()
            return
        try:
            self._overlay_proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._overlay_ready = False
            self.sing_overlay_label.value = "点唱板浮窗 (正在启动…)"
            self._schedule_overlay_probe(generation)
        except OSError as exc:
            print(f"[Overlay] start failed: {exc}")
            self._overlay_start_failed(generation)
        self._try_update()

    def _schedule_overlay_probe(self, generation, attempt=0):
        timer = threading.Timer(0.2, lambda: self._schedule_ui(lambda: self._finish_overlay_start(generation, attempt)))
        timer.daemon = True
        timer.start()

    def _finish_overlay_start(self, generation=None, attempt=0):
        generation = self._overlay_generation if generation is None else generation
        if generation != self._overlay_generation or self._stop_event.is_set():
            return
        if self._overlay_proc and self._overlay_proc.poll() is not None:
            self._overlay_start_failed(generation)
            return
        if self._send_overlay_command({"action": "ping"}):
            self._overlay_ready = True
            self.sing_overlay_sw.value = True
            self.sing_overlay_label.value = "点唱板浮窗 (已开启)"
            self._update_overlay()
            self._overlay_ontop(self.sing_ontop_sw.value)
            self._try_update()
        elif attempt < 19:
            self._schedule_overlay_probe(generation, attempt + 1)
        else:
            self._overlay_start_failed(generation)

    def _overlay_start_failed(self, generation):
        if generation != self._overlay_generation:
            return
        if self._overlay_proc:
            try:
                self._overlay_proc.terminate()
            except Exception:
                pass
        self._overlay_proc = None
        self._overlay_ready = False
        self.sing_overlay_sw.value = False
        self.sing_overlay_label.value = "点唱板浮窗 (启动失败)"
        self.config["overlay_enabled"] = False
        self._persist_settings()
        self._try_update()

    def _update_overlay(self):
        """发送当前点唱列表到浮窗"""
        if not self._overlay_ready:
            return
        items = [{"song": i["song"], "requester": i.get("requester","")} for i in self.queue if i.get("type") == "singalong"]
        if not self._send_overlay_command({"action": "show", "items": items}):
            self._overlay_ready = False
            if self.config.get("overlay_enabled", False):
                self._start_overlay()
