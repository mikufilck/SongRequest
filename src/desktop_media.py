"""
播放器控制模块
SMTC: 播放状态监控 + 播放/暂停/切歌
剪贴板: 复制歌名
"""
import asyncio
import concurrent.futures
import pyperclip


# ============ SMTC ============

async def _smtc_get_session():
    try:
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager
        manager = await GlobalSystemMediaTransportControlsSessionManager.request_async()
        return manager.get_current_session()
    except Exception:
        return None


_SMTC_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="smtc")


def _run_async(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # A second event loop cannot run in a thread with an active loop.
    return _SMTC_EXECUTOR.submit(asyncio.run, coro).result()


def smtc_play_pause():
    async def _do():
        s = await _smtc_get_session()
        if s: await s.try_toggle_play_pause_async()
    _run_async(_do())


def smtc_next():
    async def _do():
        s = await _smtc_get_session()
        if s: await s.try_skip_next_async()
    _run_async(_do())


def smtc_get_now_playing():
    """获取当前播放信息 {title, artist, status}"""
    async def _do():
        s = await _smtc_get_session()
        if not s: return None
        info = await s.try_get_media_properties_async()
        pb = s.get_playback_info()
        status_map = {4: "paused", 5: "playing", 3: "stopped"}
        return {
            "title": info.title or "",
            "artist": info.artist or "",
            "status": status_map.get(pb.playback_status, "unknown"),
        }
    return _run_async(_do())


# ============ 剪贴板 ============

def copy_text(text):
    """仅复制到剪贴板"""
    pyperclip.copy(text)



_PLAYER_PROC = {"netease": ["cloudmusic.exe"], "qq": ["qqmusic.exe", "QQMusic.exe"]}
_PLAYER_NAME = {"netease": "网易云音乐", "qq": "QQ音乐"}


def check_player(ptype):
    import psutil
    for process in psutil.process_iter(["name"]):
        try:
            if process.info["name"] and process.info["name"].lower() in [name.lower() for name in _PLAYER_PROC.get(ptype, [])]:
                return True
        except (psutil.Error, OSError):
            pass
    return False


def player_name(ptype):
    return _PLAYER_NAME.get(ptype, ptype)
