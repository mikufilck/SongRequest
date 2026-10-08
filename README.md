# ACGN同好会点歌版

ACGN同好会点歌版（SongRequest）是面向主播的桌面点歌工具。本仓库提供 Windows 完整桌面版 Release，以及选定的辅助源码。

## 下载

请从 [GitHub Releases](https://github.com/mikufilck/SongRequest/releases/latest) 下载完整包，解压后运行 `SongRequest/SongRequest.exe`。首次使用自行登录。

增量包仅适用于 Release 标注的基线版本；不确定原版本时使用完整包。更新前退出旧程序，保留自己的数据。

每个 Release 同时提供 `SHA256SUMS.txt`。Windows 可使用 `Get-FileHash -Algorithm SHA256 <文件路径>` 核对下载文件。

## 公开源码

| 文件 | 用途 |
| --- | --- |
| `src/overlay.py` | PySide6 本地透明点唱浮窗 |
| `src/overlay_protocol.py` | 有大小上限与超时的本地 TCP 收包 |
| `src/requirements.txt` | 辅助模块所需依赖 |

辅助浮窗可独立启动：

```powershell
python -m pip install -r src/requirements.txt
python src/overlay.py
```

浮窗接收来自本机的队列展示数据。公开部分不构成完整桌面项目，不能用来重建完整 Release。主程序、账号认证、机器人同步、观众网页、OBS 网页、Cloudflare Worker 与其联动协议源码不在本仓库。

完整桌面包保留这些功能；源码公开范围与安装包功能范围不同。PyInstaller 打包不提供防反编译保证。

`PUBLIC-EXPORT.json` 记录本次公开文件的 SHA256；公开提交历史来自独立导出目录，不包含完整项目的历史。

## 反馈

请在 [Issues](https://github.com/mikufilck/SongRequest/issues) 中提供版本号、复现步骤和经过脱敏的截图。不要上传 Cookie、账号配置、登录二维码或认证信息。

