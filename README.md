# ZCHAT Quota Viewer

Windows 本地额度查看器，用于查看 `https://www.zchat.tech` 账号余额、每日高级额度和免费额度。

## 功能

- 流量卡式主界面，优先显示剩余高级额度
- VIP 额度表，展示各套餐下的 `已用 / 总量`
- 迷你窗口，可作为轻量悬浮监控
- 高级额度和余额阈值告警
- 支持自动优先或手动套餐 ID 识别
- token 只保存在本机 `%APPDATA%\ZchatQuotaViewer\config.json`

## 使用

运行：

```powershell
outputs\run_zchat_quota_viewer.bat
```

首次启动点击“设置”，粘贴 zchat 的 `token` 或包含 `token=...` 的 `document.cookie`。

获取 cookie 的一种方式：

1. 登录 `https://www.zchat.tech/users/setting`
2. 按 `F12`
3. 在 Console 输入 `document.cookie`
4. 复制整段内容到设置窗口

## 套餐 ID

- `6`：zchat体验月卡
- `7`：zchat基础月卡
- `8`：zchat高级月卡
- `9`：zchat超级月卡
- `12`：zchat顶级周卡

如果接口不能返回当前套餐，建议在设置里使用“手动套餐 ID”。
