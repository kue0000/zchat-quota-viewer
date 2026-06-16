# ZCHAT 额度查看器

这是一个本地 Windows 小窗，用 zchat 前端同款接口查看额度：

- `POST https://www.zchat.tech/api/get_user`
- `POST https://www.zchat.tech/api/get_vip_level`

## 使用方法

1. 确认电脑上有 Python。
2. 双击或运行：

```powershell
python .\zchat_quota_viewer.py
```

3. 第一次打开会提示设置 token。
4. 登录 `https://www.zchat.tech/users/setting` 后，按 `F12` 打开开发者工具，在 Console 输入：

```js
document.cookie
```

5. 复制里面 `token=` 后面的值，或者整段 cookie，粘贴到程序设置里。

程序会把 token 保存在本机：

```text
%APPDATA%\ZchatQuotaViewer\config.json
```

## 说明

我还不能直接读取你的浏览器登录态，所以这里采用手动粘贴 token 的方式。之后不用再打开网页，除非 zchat 登录过期，需要重新粘贴 token。

如果首次运行后“高级额度/免费额度”没有自动识别，点击“复制原始数据”，把复制出的 JSON 发给 Codex，就能按真实字段名补一次适配。
