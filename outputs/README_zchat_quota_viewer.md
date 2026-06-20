# ZCHAT 额度查看器

双击 `run_zchat_quota_viewer.bat` 启动。

## 新功能

- 主界面像流量卡一样显示剩余高级额度
- 下方展示完整 VIP 额度表
- “迷你窗”可以常驻屏幕角落
- 可以设置高级额度和余额告警
- 设置中可以选择自动识别套餐，或手动填写当前套餐 ID

## 首次配置

1. 打开程序，点击“设置”。
2. 登录 `https://www.zchat.tech/users/setting`。
3. 按 `F12` 打开开发者工具。
4. 在 Console 输入：

```js
document.cookie
```

5. 复制整段输出，粘贴到程序设置里的 token 输入框。
6. 如果自动识别不准，选择“手动套餐 ID”：

```text
6  = zchat体验月卡
7  = zchat基础月卡
8  = zchat高级月卡
9  = zchat超级月卡
12 = zchat顶级周卡
```

程序会把配置保存在本机：

```text
%APPDATA%\ZchatQuotaViewer\config.json
```
