"""
SongRequest 点唱板 - PySide6 透明浮窗
由主程序通过 localhost socket 控制
"""
import sys
import json
import socket
import threading
from overlay_protocol import receive_command
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGraphicsOpacityEffect
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, Signal
from PySide6.QtGui import QMouseEvent

_BTN_STYLE = """
QPushButton {
    color: white;
    background: rgba(60, 60, 60, 200);
    border: 1px solid rgba(255,255,255,90);
    border-radius: 6px;
    padding: 2px 8px;
    font-size: 11px;
}
QPushButton:hover { background: rgba(100, 100, 100, 220); }
QPushButton:checked { background: rgba(0, 120, 215, 220); }
"""


class SingalongOverlay(QWidget):
    command_received = Signal(dict)

    def __init__(self, port=19527):
        super().__init__()
        self._port = port
        self.setWindowTitle("点唱板")
        self.setFixedSize(420, 200)
        self._drag_pos = None
        self._ontop = True
        self._server_socket = None
        self.command_received.connect(self._handle_command)

        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )

        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - 440, screen.top() + 80)

        self.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # 顶部透明工具栏：鼠标进入窗口时才浮现
        self.toolbar = QWidget(self)
        self.toolbar.setStyleSheet("background: rgba(15, 15, 15, 170); border-radius: 8px;")
        tb = QHBoxLayout(self.toolbar)
        tb.setContentsMargins(4, 2, 4, 2)
        tb.setSpacing(4)

        self.btn_ontop = QPushButton("📌 置顶")
        self.btn_ontop.setCheckable(True)
        self.btn_ontop.setChecked(True)
        self.btn_ontop.setToolTip("窗口置顶")
        self.btn_ontop.setStyleSheet(_BTN_STYLE)
        self.btn_ontop.clicked.connect(self._toggle_ontop)

        self.btn_close = QPushButton("✕ 关闭")
        self.btn_close.setToolTip("关闭浮窗")
        self.btn_close.setStyleSheet(_BTN_STYLE)
        self.btn_close.clicked.connect(self.close)

        tb.addWidget(self.btn_ontop)
        tb.addWidget(self.btn_close)
        tb.addStretch(1)

        self._tb_effect = QGraphicsOpacityEffect(self.toolbar)
        self.toolbar.setGraphicsEffect(self._tb_effect)
        self._tb_effect.setOpacity(0.0)
        self.toolbar.hide()
        self._tb_anim = None

        layout.addWidget(self.toolbar)

        self.label = QLabel("等待点唱...")
        self.label.setTextFormat(Qt.PlainText)
        self.label.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 20px;
                background: rgba(0, 0, 0, 160);
                border-radius: 16px;
                padding: 18px;
            }
        """)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setWordWrap(True)
        layout.addWidget(self.label, 1)

        print("[Overlay] UI ready")
        self.show()

        self.running = True
        self.thread = threading.Thread(target=self._listen, daemon=True)
        self.thread.start()

    # ---- 悬停显示工具栏 ----
    def enterEvent(self, e):
        self._show_toolbar()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hide_toolbar()
        super().leaveEvent(e)

    def _show_toolbar(self):
        if self._tb_anim:
            self._tb_anim.stop()
        self.toolbar.show()
        self._tb_anim = QPropertyAnimation(self._tb_effect, b"opacity", self)
        self._tb_anim.setDuration(150)
        self._tb_anim.setStartValue(self._tb_effect.opacity())
        self._tb_anim.setEndValue(1.0)
        self._tb_anim.start()

    def _hide_toolbar(self):
        if self._tb_anim:
            self._tb_anim.stop()
        self._tb_anim = QPropertyAnimation(self._tb_effect, b"opacity", self)
        self._tb_anim.setDuration(150)
        self._tb_anim.setStartValue(self._tb_effect.opacity())
        self._tb_anim.setEndValue(0.0)
        self._tb_anim.finished.connect(self.toolbar.hide)
        self._tb_anim.start()

    # ---- 拖动 ----
    def mousePressEvent(self, e: QMouseEvent):
        if e.button() == Qt.LeftButton:
            if self.toolbar.isVisible() and self.toolbar.geometry().contains(e.position().toPoint()):
                super().mousePressEvent(e)
                return
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e: QMouseEvent):
        if self._drag_pos is not None:
            self.move(e.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, e: QMouseEvent):
        self._drag_pos = None

    # ---- 按钮 ----
    def _toggle_ontop(self):
        self._ontop = self.btn_ontop.isChecked()
        self._apply_ontop()
        self.btn_ontop.setText("📌 置顶" if self._ontop else "📌 置顶(关)")

    def _apply_ontop(self):
        flags = self.windowFlags()
        if self._ontop:
            self.setWindowFlags(flags | Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(flags & ~Qt.WindowStaysOnTopHint)
        self.show()

    # ---- Socket 通信 ----
    def _listen(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket = sock
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(('127.0.0.1', self._port))
            self._port = sock.getsockname()[1]
            sock.listen(4)
            sock.settimeout(0.5)
            while self.running:
                try:
                    conn, _ = sock.accept()
                    with conn:
                        try:
                            cmd = receive_command(conn)
                        except OSError:
                            continue
                    if isinstance(cmd, dict):
                        self.command_received.emit(cmd)
                except socket.timeout:
                    continue
                except (ValueError, UnicodeDecodeError):
                    continue
                except OSError:
                    if self.running:
                        print("[Overlay] socket listener stopped unexpectedly")
                    break
        except OSError as exc:
            print(f"[Overlay] cannot listen on port {self._port}: {exc}")
            self.command_received.emit({"action": "close"})
        finally:
            try:
                sock.close()
            except OSError:
                pass
            self._server_socket = None

    def _handle_command(self, cmd):
        action = cmd.get('action', '')
        if action == 'ping':
            return
        if action == 'show':
            self._update(cmd)
            self.show()
        elif action == 'hide':
            self.hide()
        elif action == 'close':
            self.close()
        elif action == 'update':
            self._update(cmd)
        elif action == 'ontop':
            self._ontop = bool(cmd.get('value', True))
            self.btn_ontop.setChecked(self._ontop)
            self.btn_ontop.setText("📌 置顶" if self._ontop else "📌 置顶(关)")
            self._apply_ontop()

    def closeEvent(self, event):
        self.running = False
        if self._server_socket:
            try:
                self._server_socket.close()
            except OSError:
                pass
        event.accept()

    def _update(self, cmd):
        items = cmd.get('items', [])
        if items:
            lines = [f"🎤 {i.get('song','')} - {i.get('requester','')}" for i in items[:5]]
            self.label.setText('\n'.join(lines))
        else:
            self.label.setText("等待点唱...")
        self.adjustSize()
        self.repaint()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    overlay = SingalongOverlay()
    sys.exit(app.exec())
