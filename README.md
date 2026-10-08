# ACGN同好会点歌版

ACGN同好会点歌版（SongRequest）是一款面向直播场景的点歌管理工具。观众选择歌曲，主播在桌面端统一查看和处理点歌队列，让歌曲搜索、接歌、播放安排和直播展示连成一套日常工作流程。

## 功能

- **歌曲搜索**：汇总网易云音乐与 QQ 音乐的搜索结果，合并同歌名、同歌手条目，保留平台信息与付费标记。
- **队列管理**：查看待播歌曲，切换播放、跳过和清理条目，按自己的直播节奏处理点歌。
- **点歌规则**：设置队列容量、每人待播上限、重复歌曲过滤和请求冷却时间。
- **主播歌单**：维护自己会唱的歌曲，观众可以从歌单中选择点唱。
- **播放辅助**：复制歌名到剪贴板，并通过系统媒体控制读取播放状态、辅助切歌。
- **直播展示**：提供透明点唱浮窗及 OBS / 直播姬浏览器源点歌板，支持调整展示样式。
- **个性设置**：设置背景、展示主题和队列清理方式。

## 下载与使用

1. 从 [Releases](https://github.com/mikufilck/SongRequest/releases/latest) 下载 Windows 完整包。
2. 解压后运行 `SongRequest/SongRequest.exe`，按提示完成 B站登录。
3. 在设置中调整点歌规则，需要点唱时先添加主播歌单。
4. 将应用提供的观众地址发给观众，在直播控制台处理点歌队列；直播展示链接可添加为 OBS 浏览器源。

软件采用绿色压缩包分发，无需安装。增量包只适用于 Release 标注的基线版本；不确定原版本时使用完整包。更新前退出旧程序，并保留自己的数据。

Release 中的 `SHA256SUMS.txt` 用于核对下载文件。在 Windows 中可运行：

```powershell
Get-FileHash -Algorithm SHA256 <文件路径>
```

## 代码导航

| 模块 | 内容 |
| --- | --- |
| `src/music_search.mjs` | 网易云 / QQ 音乐搜索、结果归一化与合并 |
| `src/queue_rules.py` | 歌名去重、队列与每人上限、冷却、持久化入队与失败回滚 |
| `src/overlay.py` | 本地透明点唱浮窗 |
| `src/overlay_protocol.py` | 分片收包、大小限制和连接超时 |
| `tests/` | 搜索与入队行为回归 |

启动浮窗与运行测试：

```powershell
python -m pip install -r src/requirements.txt
python -m pip install pytest
python src/overlay.py
python -m pytest tests/test_queue_rules.py -q
node --test tests/music_search.test.mjs
```

搜索模块可在支持 `fetch` 的 JavaScript 环境中调用 `searchSongs(keyword)`；入队模块的 `enqueue_song` 接收调用方提供的保存函数，保存失败时恢复队列和冷却状态。

## 反馈

遇到问题请在 [Issues](https://github.com/mikufilck/SongRequest/issues) 中提供版本号、复现步骤和截图，并隐去账号与登录信息。
