# ZCHAT Quota Viewer

Windows 本地额度查看器，用于查看 `https://www.zchat.tech` 账号余额、每日高级额度和免费额度。

## 功能

- **流量卡式主界面**：深色仪表盘显示剩余高级额度、圆环百分比、用量进度
- **HTML 仪表盘**：现代 Web 前端（Chart.js），在浏览器中打开即可查看所有额度详情
- **迷你悬浮窗**：无边框挂件，可拖拽，显示剩余额度和余额，右键菜单操作
- **系统托盘**：常驻托盘图标，悬停显示额度信息，关闭窗口最小化到托盘
- **VIP 额度表**：各套餐 `已用 / 总量` 对比
- **额度告警**：高级额度剩余和余额低于阈值时弹窗提醒
- **Token 管理**：过期检测、书签脚本一键提取 token
- **套餐识别**：支持自动优先或手动套餐 ID

## 使用

### 脚本运行

```powershell
outputs\run_zchat_quota_viewer.bat
```

首次启动点击"设置"，粘贴 zchat 的 `token` 或包含 `token=...` 的 `document.cookie`。

### 获取 Token

**方式一：F12 Console**
1. 登录 `https://www.zchat.tech/users/setting`
2. 按 `F12` 打开开发者工具
3. 在 Console 输入 `document.cookie`
4. 复制整段内容到设置窗口

**方式二：书签脚本（推荐）**
1. 在设置窗口点击"复制书签脚本"
2. 在浏览器创建新书签，网址栏粘贴脚本内容
3. 登录 zchat 后点击该书签即可复制 token

### HTML 仪表盘

启动程序后点击"仪表盘"按钮，或在浏览器访问：

```text
http://127.0.0.1:18932/
```

## 套餐 ID

| ID | 套餐名称 |
|----|----------|
| 6  | zchat体验月卡 |
| 7  | zchat基础月卡 |
| 8  | zchat高级月卡 |
| 9  | zchat超级月卡 |
| 12 | zchat顶级周卡 |

## 系统托盘

需要安装 `pystray` 和 `Pillow`：

```powershell
pip install pystray Pillow
```

安装后程序会自动创建托盘图标。未安装时程序正常运行但无托盘功能。

## 一键 EXE

本地打包：

```powershell
build_exe.bat
```

产物位于 `dist\ZchatQuotaViewer.exe`。

## 配置

Token 和设置保存在：

```text
%APPDATA%\ZchatQuotaViewer\config.json
```

## 架构

```
zchat_quota_viewer.py    # 主程序（Tkinter + HTTP Server + 系统托盘）
dashboard.html           # Web 仪表盘前端
run_zchat_quota_viewer.bat  # 启动脚本
build_exe.bat            # PyInstaller 打包脚本
```

Python 主程序启动时会：
1. 创建 Tkinter 主窗口 + 迷你悬浮窗
2. 启动本地 HTTP 服务器（端口 18932）提供仪表盘页面和 `/api/data` 接口
3. 可选创建系统托盘图标（需要 pystray + Pillow）
4. 定时调用 zchat API 刷新额度数据
