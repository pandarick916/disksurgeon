---
name: disk-doctor
description: Windows 磁盘诊断与减负。一键扫描生成可视化的"磁盘地图"（面积=占用，颜色=危险等级），自动排出最占地方的目录；再对确认的大目录做 junction（目录传送门）搬家，把数据挪到别的盘、原位留链接，程序无感。当用户说「C 盘满了/红了、盘不够用、看看什么占空间、清理磁盘、给文件夹搬家、junction、mklink、目录链接、磁盘分析、空间可视化」时使用。
---

# 硬盘瘦身专项助理

一句话：**先看清谁占地方（诊断），再把它搬走（搬家）。** 两件事都只做确定的事，不确定就不动手。

**Windows 和 macOS 都能用；C 盘、D 盘、外接盘、整个 `/` 都能扫**——它画的是"任意一个目录"的地图，不限系统盘。

---

## 能力总览

| 能力 | 一键做什么 | 产物 | 是否改数据 |
|---|---|---|---|
| **① 一键诊断** | 扫描任意盘/目录 → 生成单文件 HTML 磁盘地图 → 自动打开（可选同时导出一张 PNG） | `disk_report.html` + `disk_report.png` | ❌ 纯只读 |
| **② 一键搬家** | 预检 → 干跑 → 确认 → 搬 + 建链接 → 验证 | Windows：`<JUNCTION>`；macOS：symlink。数据在目标盘 | ✅ 移动文件 + 建链接 |
| **③ 一键清理清单** | 扫描 → 生成可勾选清单（每项写清「最坏情况」）→ 勾完复制指令回对话 | `scan_cleanup.html` | ❌ 只读（用户勾了才删） |

**联动**：诊断出的每个大目录，直接对应一个搬家候选。这是本专家存在的理由——不是两个工具的拼盘。

---

## 🔴 铁律（fail-closed，任何情况不得绕过）

1. **诊断阶段绝不写盘。** 扫描器只 `scandir` + `stat`，不删不改。
2. **搬家必须三关**：预检 GO → 干跑（`-DryRun`）→ 用户明确说「搬」。少一关不动手。
3. **只建 junction（`/J`）**，不用符号链接（`/D` 需管理员 + 兼容差）。
4. **删链接只用 `rmdir "链接"`**（不带 `/s`）。用 `del /s` 或资源管理器「删除」会顺着链接删掉目标盘的真数据。
5. **一次只搬一个目录**，搬完验证，再搬下一个。
6. **程序必须完全退出**（含托盘、后台服务），否则文件占用会搬一半。
7. **系统目录与程序目录禁止搬**：`Windows`、`Program Files`、`ProgramData`（除非明确知道后果）。
8. **Docker/WSL 的 vhdx 不走本法**，用官方迁移。

> 铁律 4 是唯一会造成「不可逆数据丢失」的操作。每次删链接前，先 `dir /a:l` 确认那是个链接。

---

## 能力一 · 一键诊断

### 跑

```bash
# Windows
python "<skill>/scripts/scan_disk.py" --path "C:\\" --min-size 50 --depth 7 --out "scan.json"
python "<skill>/scripts/make_report.py" "scan.json" --open --png --with-checklist

# macOS（扫整机 / 或家目录 ~ ，按需换）
python3 "<skill>/scripts/scan_disk.py" --path "/" --min-size 50 --depth 7 --out "scan.json"
python3 "<skill>/scripts/make_report.py" "scan.json" --open --png --with-checklist
```

**`--with-checklist` 不要省。** 它顺手把可勾选清理清单也生成出来，同一份 scan.json、几乎零成本。
用户说「排查」「看看」「分析」的时候，他心里的下一句一定是「那我该删哪些」——
少给这一件，他就要再问一轮。**地图和清单一次出齐，这是默认动作，不是可选项。**

**`--png` 同样很重要**：它会把地图同时截成一张图。用户问「地图呢」、要把结果发给别人、或要把对话发布成分享页时，**只有 HTML 是看不见的**（分享页里 HTML 只是个附件），必须给图。

**一条命令版本**（Windows cmd）：

```bat
python "<skill>\scripts\scan_disk.py" --path C:\ --out "%TEMP%\scan.json" && python "<skill>\scripts\make_report.py" "%TEMP%\scan.json" --open --png --with-checklist
```

### 参数怎么定

| 参数 | 默认 | 什么时候改 |
|---|---|---|
| `--path` | Windows `C:\`；macOS `/` | 只查家目录更快：`C:\Users\<你>` 或 `~/`。也可以指任意盘：`D:\`、`/Volumes/外接盘` |
| `--min-size` | 50（MB） | 小盘（<100GB）调到 20；找零碎垃圾调到 5（会慢一些） |
| `--depth` | 7 | 一般不用改。太深会拖慢，太浅看不进子目录 |
| `--fast` | 关 | **跳过硬链接去重**。大概快一倍，但 `WinSxS` 这类目录会虚高（多算一倍）。只在你赶时间、且不做删除决策时用 |

**性能基准（实测）**：Windows 家目录 55.9 GB / 12.4 万文件 / **10 秒**；`C:\Windows` 22.8 GB / 23 万文件 / **39 秒**（去重模式）。全盘 C 通常 1–4 分钟。

### 数字为什么和资源管理器不一样（重要，必须主动解释）

两个原因，都不是 bug：

1. **硬链接**。`C:\Windows\WinSxS` 里大量文件和 `System32` 是同一份数据（只是多了个名字）。资源管理器会把两边都算上，**看起来 11.4 GB，其实只有 4.8 GB**。我们按"数据只存了一份"计，所以数字更小、也更接近磁盘真实占用。
2. **目录链接 / 挂载点**。junction、symlink、macOS 的 `/System/Volumes/Data` 都不跟随，避免同一份数据被数两遍。

扫描器输出里带 `dedup_bytes`（少算了多少）。**主动把这个数告诉用户**，否则他会觉得"你们的数字不准"。

### 产出怎么读（这是"一看就懂"的关键）

打开后是一张**磁盘地图**：

| 看图规则 | 含义 |
|---|---|
| **方块面积** | 就是这个目录/文件占多大。面积 = 空间，不需要看数字 |
| **红色** | ≥10 GB，优先处理 |
| **橙色** | 1–10 GB，值得看一眼 |
| **蓝色 / 青色** | 100 MB–1 GB / 10–100 MB，正常 |
| **灰色** | <10 MB，不用管 |
| **右侧 TOP 10** | 当前这一层最占地方的十个，点一下直接进 |
| **点方块** | 进去看它内部（面包屑在上方，ESC 或右键返回） |

**推荐动作顺序**：先看红的 → 点进去一层 → 看它内部哪个子目录最大 → 判断能不能搬。

### 从地图直接下指令（最重要的一步）

看清之后不用描述，**直接点它**：

| 操作 | 结果 |
|---|---|
| **单击方块** | 选中（青色高亮），底部弹出操作条 |
| **双击方块** | 进入下一层 |
| **右键 / ESC** | 返回上一层 |

操作条四个按钮：`进入下一层` / `复制清理指令` / `复制搬家指令` / `复制路径`。

点「复制清理指令」，剪贴板里就有一句完整请求，粘贴回对话即可：

> 帮我清理 `C:\Users\xxx\.cache`，它占了 1.8 GB。先扫描说明里面到底有什么、哪些能安全删，再等我确认后动手。

**所以：当用户贴来一句"帮我清理 XXX"或"把 XXX 搬走"时，先看他是不是从地图复制的**——如果是，路径和大小都是实测值，直接采信，不用再问一遍。

**风险分级（地图自动判断，收到指令后不得绕过）**：

| 选中对象 | 按钮表现 | 该怎么处理 |
|---|---|---|
| 普通目录 | `复制清理指令` | 正常走流程 |
| `AppData` 等用户容器 | `看看里面哪些能清` | **整个不能删/不能搬**，必须先下钻看子目录 |
| `Windows` / `Program Files` / `ProgramData` / `$RECYCLE.BIN` | `系统目录 · 不能清理`（**按钮禁用**） | 一律不动，说明原因即可 |

### 扫描器行为（可核查）

- 多线程 `scandir`，符号链接/junction **不跟随**（避免绕圈重复计数）
- 无权限的目录记入 `skipped`，不中断
- `pagefile.sys` / `hiberfil.sys` / `System Volume Information` 跳过
- 小于 `--min-size` 的节点归并为「其它」，避免树爆炸
- 输出 JSON + 自包含 HTML（数据内嵌，单文件可分享，无外部依赖）

---

## 能力二 · 一键搬家（Windows: junction / macOS: symlink）

### 0) 先预检（只读）

```powershell
powershell -ExecutionPolicy Bypass -File "<skill>\scripts\preflight_check.ps1" -Source "C:\Users\<你>\.codex" -Target "D:\AgentData\.codex"
```

输出 `RESULT: GO` 或 `NO-GO`。**NO-GO 不许搬。**
自动检查：源是真文件夹（非链接）、目标盘存在、目标非空、是否同盘、目标空间 ≥ 源大小 × 1.1。

### 1) 干跑（只打印计划，不搬）

```powershell
powershell -ExecutionPolicy Bypass -File "<skill>\scripts\move_with_junction.ps1" -Source "C:\Users\<你>\.codex" -Target "D:\AgentData\.codex" -DryRun
```

### 2) 用户确认

把干跑结果给用户看：搬哪个、搬到哪、腾出多少、风险点。**等用户明确说「搬」**。

### 3) 真搬

```powershell
powershell -ExecutionPolicy Bypass -File "<skill>\scripts\move_with_junction.ps1" -Source "C:\Users\<你>\.codex" -Target "D:\AgentData\.codex" -Force
```

内部顺序：robocopy 复制（保留源）→ 校验 → 删源 → `mklink /J` → 验证。任一步失败自动停。

### 4) 验证

```bat
dir /a:l "C:\Users\<你>"
```

应显示 `<JUNCTION>`。然后重开程序：登录态、历史、配置都在 → 成功。

### 5) 回滚（出事就用）

```powershell
powershell -ExecutionPolicy Bypass -File "<skill>\scripts\rollback_junction.ps1" -Source "C:\Users\<你>\.codex" -Target "D:\AgentData\.codex" -Force
```

删链接 → 数据搬回 → 恢复程序。**回滚前确认目标盘数据完好。**

---

### macOS 的做法（symlink，不是 junction）

macOS 没有 junction，用符号链接 `ln -s`。**风险比 Windows 高一点**：少数 App 的沙盒会拒绝跟随 symlink，所以只对「程序自己会重建的缓存目录」下手，别碰沙盒数据。

```bash
# 干跑（默认就是干跑，不动任何东西）
bash "<skill>/scripts/move_with_symlink.sh" \
  --src "$HOME/Library/Caches" --dst "/Volumes/Data/Caches"

# 真搬
bash "<skill>/scripts/move_with_symlink.sh" \
  --src "$HOME/Library/Caches" --dst "/Volumes/Data/Caches" --force

# 回滚
bash "<skill>/scripts/rollback_symlink.sh" --src "$HOME/Library/Caches" --force
```

脚本会依次：确认源不是链接 → 拒绝系统路径（`/System` `/Library` `/Applications` `/usr` `/bin` `/etc` `/private`）→ 检查目标空余 ≥ 源 ×1.1 → rsync 复制 → 核对文件数 → 删源 → 建 symlink。
**旧副本保留为 `<源>.oldmove`**，等用户确认程序正常后再让他手动删。

| macOS 上值得搬 | 为什么 |
|---|---|
| `~/Library/Caches` | 纯缓存，删了都会重建 |
| `~/Library/Developer/CoreSimulator` | iOS 模拟器镜像，常几十 GB |
| `~/Library/Developer/Xcode/DerivedData` | 编译产物，可重建 |
| `~/Library/Containers/<某App>/Data/Library/Caches` | 单个 App 的缓存 |

| 不建议搬 | 原因 |
|---|---|
| `~/Library/Application Support` | 大量 App 走沙盒，认不得 symlink |
| `~/Documents` / `~/Pictures` | 用系统「移到」功能更安全，不必建链 |
| `/System` `/Library` `/Applications` | SIP 保护，脚本已拒绝 |

---

## 能力三 · 一键清理清单（可勾选，小白最顺手）

诊断回答「谁占地方」，清单回答「**哪几项能删、删了会怎样**」。
**实战顺序通常是 一 → 三 → 二**：先看清，再清掉能清的，最后才谈搬家。

```bash
python "<skill>/scripts/make_checklist.py" scan.json --open --png
# → scan_cleanup.html / .png
```

> 一般不用单独调：`make_report.py --with-checklist` 已经带上了。
> 单独调的场景只有一个——地图早就给过了，用户这时候才说要清理。

### 界面长什么样

| 组 | 含义 | 交互 |
|---|---|---|
| ✅ 可以删 | 缓存 / 日志 / 临时 / 旧安装包 / 迁移旧副本 / 显卡缓存 | 可勾 |
| ⚠️ 你决定 | 运行时依赖、浏览器配置、项目依赖 | 可勾，但每条都写了代价 |
| 🚫 别动 | 系统目录、密钥、字体、游戏存档 | **勾不上**，点了会抖一下并显示原因 |

每一条都有一句「最坏情况」，用大白话，例如：

> 旧安装包 → 「更新早就装完了，留着只是占地方。删了不影响现在用的版本，只是以后想退回旧版得重新下载。」

底部固定条：`已选 N 项 · 能腾出 X GB` + `一键勾上放心项` + `复制清理指令`。

### 判定错了就当场查：`--why`

清单的结论全靠一张规则表，规则表比代码更容易错。**任何一条你觉得不对劲，先自查再回话**：

```bash
python "<skill>/scripts/make_checklist.py" --why "C:\Windows" \
    "C:\Users\me\AppData\Local\Microsoft\Windows" \
    "/System/Library/Caches" "/Users/me/Library/Caches"
```

```
🚫  C:\Windows                        → forbidden | 系统本体，删了开不了机
✅  C:\Users\me\AppData\Local\Microsoft\Windows → safe / 应用缓存
🚫  /System/Library/Caches            → forbidden | 这是 macOS 系统目录
✅  /Users/me/Library/Caches          → safe / 缓存
```

### 🔴 三个必须记住的判定原则

1. **同名 ≠ 同物，按位置判不按名字判。**
   `C:\Windows` 是系统内核；`AppData\Local\Microsoft\Windows` 只是一个 792 MB 的缓存文件夹。
   按裸名字匹配会把后者一起锁死 —— 用户看到能删的东西被无缘无故禁掉，**整个清单就不可信了**。
   规则表因此拆成三层：`FORBIDDEN_ANY`（密钥/内核文件，任何位置都禁）、
   `OS_ROOT_NAMES`（只在盘根才算）、`APPDATA_CACHE_NAMES`（在 AppData 里反而是缓存）。
   可删的东西被误锁，和危险的东西被误放，是同等级的错误。

2. **`.migold` 必须现场验证「另一份还在」。**
   `User Data.migold` 只有在 `User Data` 确实存在时才是旧副本；
   否则它是唯一的数据，勾了就是清掉全部书签密码。脚本用 `os.path.exists()` 落实，
   找不到对应目录就自动降级成 ⚠️ 并改写文案。

3. 🔴 **锁死的容器，不许把里面的可删子项一起吞掉。**
   这是用户 2026-11-04 亲自指出来的层级设计缺陷：`AppData\Local\Packages` 整体判 🚫，
   但同一张规则表又写着 `Packages\DATA` → ✅ 安装暂存。旧代码一命中父级就 `continue`，
   于是那 2 GB 从头到尾没上过清单，**用户看得到它被锁，却勾不到里面能删的**。
   规则表自相矛盾：子项判可删，父项把子项一起吞了。

   现在的做法（`DESCEND_LOCKED` 白名单 + `collect(locked=...)`）：
   - 只有白名单里的容器才「探进去」：`AppData\Local\Packages`、`ProgramData`、
     `Program Files`、`Program Files (x86)`。**`C:\Windows` 不在名单里**，永远不进去。
   - 进去以后**只收 safe**，caution / forbidden 一律不再展开。宁少收，不错收。
   - 捞出来的子项带 `lockedParent`，界面显示「它在锁死的 X 里面，但这一项单独删是安全的」；
     父行显示「里面有 N 项（X GB）可以单独删，已列在上面」。

   实测收益（C 盘一次扫）：Locked `Packages` 里捞出 Python 的 LocalCache 1.08 GB；
   `ProgramData` / `Program Files (x86)` 里捞出安装残留 3.6 GB
   （Adobe 补丁 967 MB、NVIDIA 旧驱动 691 MB、InstallShield 存的安装包 878 MB、Edge 安装包 330 MB）。

4. **安装残留靠「躺在哪个目录」判，不靠文件名。**
   `527.56-desktop-win10-win11-64bit-international-dch-whql-g.exe` 这种名字看不出用途，
   但它在 `Downloader\` 下就是旧驱动。规则：
   - `.msp` / `.msu` → 补丁，一律可删
   - 非用户目录下，`Download / Downloader / Update / Upgrade / Patch` 里的 `.exe/.msi` → 可删
   - `InstallShield Installation Information\{GUID}\` 里的 `.exe/.msi` → 是安装包本体，不是程序
   - **`\users\` 下的不算** —— 用户自己「下载」文件夹里的安装包，不能替他决定

### 用户勾完会发生什么

点「复制清理指令」，剪贴板里是：

```
我已经在清理清单里勾好了下面 28 项，合计约 19.2 GB。请逐项清理：
删一项、报一项，不要批量删；遇到文件被占用或权限不足就跳过并说明原因。

1. ✓ C:\Users\...\User Data.migold　（2.13 GB，迁移旧副本）
2. ✓ C:\Users\...\WXWork\upgrade　（2.05 GB，旧安装包）
3. ⚠ C:\Users\...\.cache　（1.75 GB，通用缓存）
...

清完之后请告诉我：成功几项、跳过几项、失败几项，以及磁盘空间从多少变成了多少。
```

**用户把这段贴回来，就是授权你删这些。不要再问一遍「确定吗」。**

### 执行纪律（收到清单后必须照做）

1. **逐项删，一项一条命令。** 不要 `rmdir /s` 一把梭，也不要循环批删。
2. **每删完一项记一行结果**：成功 / 跳过（原因）/ 失败（原因）。
3. **被占用就跳过**，别强删。告诉用户"关掉 XX 再来"。
4. **`⚠` 开头的项要格外小心**：先看一眼里面有没有不像是缓存的东西，发现异常就跳过并说明。
5. **删完必须给一个总结**（格式见下），并报磁盘前后剩余空间。

### 删完的标准回复（照这个格式）

```
清完了。

✅ 成功 24 项，释放 19.2 GB
⚠️ 跳过 3 项 —— 文件正被占用（Chrome、企业微信还开着）
❌ 失败 1 项 —— 权限不足，需要管理员

C 盘剩余：37.8 GB → 57.0 GB

要不要把跳过的 3 项再试一次？关掉那两个软件就行。
```

三行结论 + 一个数字对比 + 一个下一步。不要写小作文。

### 判定规则（清单是按这个分的，有异议可以改）

| 判定 | 命中什么 |
|---|---|
| 🚫 禁止 | `Windows` `System32` `WinSxS` `Program Files*` `ProgramData` `pagefile.sys` `.ssh` `.gnupg` `.git` `Fonts` `DriverStore`、游戏存档 |
| ✅ 可删 | `*Cache*` `Code Cache` `GPUCache` `CachedData`、`*.log` `*.dmp`、`Temp`、`upgrade`、`*migold`、`DXCache`/`GLCache`、`*.msi/msix`、`Crashpad`、缩略图缓存、`Packages\DATA` |
| ⚠️ 谨慎 | `node_modules`、`runtimes`、`User Data`、根目录下的 `.cache`（可能装了运行时） |

阈值：**小于 100 MB 的不进清单**（改了 `--min-mb`）。

---

## 联动：诊断结果 → 搬家决策

诊断出来的大目录，按这张表判断：

| 类型 | 典型路径 | 能不能搬 | 建议 |
|---|---|---|---|
| **AI agent 家目录** | `.codex` / `.workbuddy` / `.claude` | ✅ 最优先 | 通常几百 MB–数 GB，程序关了就能搬 |
| **包与模型缓存** | `.cache` / `.ollama` / `.npm` / `pip` | ✅ 安全 | 往往最大，收益最高 |
| **工具数据** | `AppData\Local\<App>`、`AppData\Roaming\<App>` | ⚠️ 谨慎 | 先小样本试一个，确认程序仍正常 |
| **node_modules** | 项目内 | ⚠️ 可搬但未必值 | 删了重装更干净 |
| **Docker / WSL** | `.vhdx` | ❌ 别用本法 | 走 Docker Desktop 官方迁移 |
| **系统 / 程序** | `Windows`、`Program Files` | 🚫 禁止 | — |
| **用户文档 / 照片** | `Documents` / `Pictures` | ✅ 但另有更好办法 | 直接改库位置（属性→位置→移动），不必 junction |

**推荐给小白的第一刀**：`.cache` 或最大的 agent 家目录。收益高、风险低、可回滚。

---

## 脚本一览

| 脚本 | 平台 | 作用 | 安全级别 |
|---|---|---|---|
| `scripts/scan_disk.py` | Win + mac | 扫描 + 输出树形 JSON（含硬链接去重） | 只读 |
| `scripts/make_report.py` | Win + mac | JSON → 单文件 HTML 地图（`--png` 同时出图） | 只读 |
| `scripts/make_checklist.py` | Win + mac | JSON → 可勾选清理清单（`--png` 同时出图，`--why 路径…` 自查判定） | 只读 |
| `templates/report.html` | — | 地图模板（Canvas + squarified treemap，零外部库） | — |
| `templates/cleanup.html` | — | 清单模板（勾选 + 最坏情况 + 复制指令） | — |
| `scripts/scan_big_dirs.ps1` | Win | 快速列常见 AI 目录大小 + junction 状态 | 只读 |
| `scripts/preflight_check.ps1` | Win | 搬前六项检查，GO/NO-GO | 只读 |
| `scripts/move_with_junction.ps1` | Win | 搬 + 建 junction；**默认干跑**，`-Force` 才真执行 | 需确认 |
| `scripts/rollback_junction.ps1` | Win | 删链接 + 搬回；`-Force` 才执行 | 需确认 |
| `scripts/move_with_symlink.sh` | mac | 搬 + 建 symlink；**默认干跑**，`--force` 才执行 | 需确认 |
| `scripts/rollback_symlink.sh` | mac | 删 symlink + 搬回；`--force` 才执行 | 需确认 |

---

## 常见问题（排障）

| 症状 | 原因 | 处理 |
|---|---|---|
| `mklink` 报「已存在」 | 原位还有空文件夹 | 删空文件夹再建链 |
| 搬一半报错 | 文件被占用 / 权限不足 | 关程序重试；robocopy 已保留源，不丢数据 |
| 建链后程序打不开 | 程序不认 junction，或没关干净 | 回滚，再排查 |
| 用 `del /s` 后目标盘数据没了 | 顺着 junction 删了真数据 | **立刻停手**，用数据恢复工具；以后只用 `rmdir` |
| 升级后 C 盘又涨 | 程序重建了家目录 | 重做 junction |
| 扫描很慢 | 目录深 / 机械盘 / 杀软实时扫描 | 加 `--min-size`，或只扫家目录 |
| 🔴 **脚本明明改了，跑出来还是老版本**；或用户说「怎么没让我勾选」而清单文件根本没生成 | **缓存副本没刷新**。专家运行的不是 `plugins/marketplaces/.../disk-doctor`，而是 `plugins/cache/my-experts/disk-doctor/<版本号>/` 那份快照。只改源不升版本号，缓存永远不动 | 见下 |

### 🔴 改完脚本必须做的事（否则白改）

改 `skills/` 里任何文件后，**仅 `register_expert.py` 是不够的**——它只更新 `marketplace.json`，缓存目录按版本号固化，不会重新拷贝。必须：

1. `.codebuddy-plugin/plugin.json` 的 `version` **升一位**（`1.0.0` → `1.1.0`）
2. 重新 `validate_expert.py` + `register_expert.py`
3. 确认缓存：`ls plugins/cache/my-experts/disk-doctor/` 下应出现新版本目录
4. **删掉旧版本目录**，并把新源复制进去对齐（缓存是生成物，可以安全重建）
5. 验一遍：缓存里的 `scan_disk.py` 字节数必须和源一致

自查一行：

```bash
find "$HOME/.workbuddy" -name "scan_disk.py" -exec stat -c "%s %n" {} \;
```

两个路径的字节数不一样 → 就是在跑旧代码。**2026-11-04 就是这么翻船的**：
缓存停在 `1.0.0`，那份连 `make_checklist.py` 都没有，用户要清单当然给不出来；
而且旧扫描器没有硬链接去重，C 盘多报了 23 GB。

细节坑见 `references/junction-pitfalls.md`。

**执行一次清理之前，先读 `references/execution-lessons.md`。**
里面是 2026-11-04 真删 16 项、废掉 11 项换来的四条硬教训：
先 realpath 再报数、删完必须清空回收站并用系统口径复核、失败要分三类、需管理员的项提前标出来。

---

## 参考

- `references/execution-lessons.md` — **真实清理的教训账本**（要做什么 / 不要做什么 / 三条线方法论）
- `references/junction-pitfalls.md` — junction 全部已知坑（来源：windows-disk-relief）
- `references/space-tool-capability.md` — SpaceSniffer 能力矩阵与本工具的对应关系（逆向记录）
- `LICENSE-origin` — 搬家工具箱原始许可
