# junction 搬家的坑（真实踩过，照做）

## 必守三条

1. **先关程序，再搬。**
   程序开着时文件被占用，`move` 会失败，甚至把数据搬坏。托盘图标、后台服务、IDE 插件都算「开着」。

2. **建链用 `/J`，别用 `/D`。**
   - `/J` = junction，普通权限即可，兼容好。
   - `/D` = 符号链接，要管理员或开发者模式，部分程序不认。

3. **删链接用 `rmdir`，别用 `/s`。**
   - 正确：`rmdir "C:\Users\你\.codex"` → 只删「门」，D 盘数据不动。
   - 危险：`del /s` 或带 `/s` 的删除 → 会顺着门进到 D 盘，把真数据一起删光。
   - 删之前用 `dir` 确认它是 `<JUNCTION>`，别凭感觉。

## 其他要点

- **junction 只能指本地 NTFS 卷**，不能指网络盘。
- **搬前备份关键配置**（如 `config.toml`、`.json` 状态文件），以防万一。
- **部分 Electron 应用对 junction 敏感**，先拿小的、非关键的试；`%APPDATA%` 下的数据比 `~/.xxx` 更敏感。
- **升级/重装可能重建目录**：装完检查原位是否又变回真文件夹，是的话重做 junction。
- **Docker / WSL 不要用本法硬搬**：它们有自己的迁移方式（WSL export/import、Docker 设置里改 disk image location）。
- **node_modules**：删了重装更干净，未必值得搬。

## 验证

- `dir /a:l "C:\Users\你"` → 原位显示 `<JUNCTION>`。
- 重开程序：登录态、历史、功能都在。
- C 盘空间确实腾出。

## 回滚

```bat
rmdir "C:\Users\你\.codex"
move "D:\AgentData\.codex" "C:\Users\你\.codex"
```

回滚前确认 D 盘数据完好；回滚后重开程序验证。

## 真实案例（示意）

- `C:\Users\<you>\.workbuddy` → **Junction** → `D:\AgentData\.workbuddy`（实测可行）。
- `C:\Users\<you>\.codex` → 真文件夹，常见几百 MB，含日志、沙箱、attachments、memories——典型「改工作目录也动不了」的家目录。
- `C:\Users\<you>\.cache` → 常见 1 GB 以上。
- `%APPDATA%` 下：`Codex`、`WorkBuddyX`、`CodeBuddy CN`（Electron 数据）。
