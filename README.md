# ZCHAT Quota Viewer

一个本地 Windows 小窗，用于查看 `https://www.zchat.tech` 账号余额和每日额度，不需要反复打开网页。

## 使用

运行：

```powershell
outputs\run_zchat_quota_viewer.bat
```

首次启动需要粘贴 zchat 的 `token` 或包含 `token=...` 的 `document.cookie`。

## 文件

- `outputs/zchat_quota_viewer.py`：主程序
- `outputs/run_zchat_quota_viewer.bat`：Windows 启动脚本
- `outputs/README_zchat_quota_viewer.md`：详细使用说明

token 只保存在本机：

```text
%APPDATA%\ZchatQuotaViewer\config.json
```
