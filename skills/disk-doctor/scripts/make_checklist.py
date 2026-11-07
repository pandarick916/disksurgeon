#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""把扫描结果变成「可勾选的清理清单」。

输入：scan_disk.py 产出的 scan.json
输出：cleanup.html（可勾选界面，勾完一键复制指令）

判定逻辑：
  · forbidden  先判，命中就禁止勾选（系统目录、个人文件、密钥）
  · safe       缓存 / 日志 / 临时 / 旧安装包 / 迁移旧副本 / 着色器缓存
  · caution    运行时依赖、浏览器配置、需要人来判断的

每条都带一句「最坏情况」，用大白话，让人敢勾。
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(os.path.dirname(HERE), "templates", "cleanup.html")
MIN_BYTES = 100 * 1024 * 1024          # 小于 100MB 的不进清单，避免噪音

# ── 最坏情况文案：说人话，给退路，别用「无风险」 ──────────────
WORST = {
    "cache":   "这是程序放临时文件的地方。删了以后第一次打开那个软件会慢几秒（重新生成）；"
               "里面的设置、登录、聊天记录都不在这里，不会丢。",
    "cache_root": "这是用户目录下的通用缓存文件夹，多个工具共用。大部分会自己重建，"
                  "但如果里面有下载好的运行时（Node / Python / 模型），删掉要重新下载几百 MB 到几个 GB。"
                  "不确定就先别勾，我可以进去看一层再告诉你。",
    "browser_cache": "只是网页的临时图片和脚本。删了以后头几个网页加载慢一点，"
                     "书签、密码、登录状态都存在别的地方，不受影响。",
    "log":     "这是软件的运行记录。删了等于把那天的监控录像撕了——以后出问题没法查，"
               "但软件本身照常用。",
    "temp":    "临时文件，本来就是用完该清掉的。删了系统可能提示「有个文件正在用」，跳过就行。",
    "upgrade": "旧版本的安装包。更新早就装完了，留着只是占地方。删了不影响现在用的版本，"
               "只是以后想退回旧版得重新下载。",
    "migold":  "升级或迁移时留下的旧副本。现在在用的是另一份，这份只是没清理干净。",
    "shadercache": "显卡的编译缓存。删了以后头几次玩游戏或看视频会卡一下（重新编译），之后就一样了。",
    "installer": "安装程序的残留。软件已经装好了，这些打包文件用不上。想重装可以去官网再下。",
    "crash":   "崩溃时留下的现场记录。删了不影响软件运行，只是下次崩溃时没有详细报告可看。",
    "thumb":   "缩略图缓存。删了以后第一次打开图片文件夹会重新生成缩略图，慢一两秒。",
    "data_stage": "安装过程的暂存数据，装完就没人动了。删了不影响已安装的程序。",
    "node_modules": "项目的依赖包。删了以后跑项目要重新 npm install（要联网，几分钟）。"
                    "如果你还在用这个项目，先别删。",
    "runtime": "某个工具下载的运行时（比如 PHP、Node、Python）。删了那个工具会用不了，"
               "除非你确实不用它了。",
    "config":  "这是软件的配置文件，可能含账号、书签、偏好设置。删了要重新配置一遍。"
               "确定不用那个软件了再删。",
    "win_appcache": "Windows 自己的缓存仓库：图标缩略图、错误报告、字体缓存、网页缓存。"
                    "删了 Windows 会自己重新生成，不丢任何文件。只是一段时间内，"
                    "图片文件夹的缩略图和部分图标要重新爬一遍，看着有点空，别慌。",
}

# 类别显示名
KIND_LABEL = {
    "cache": "缓存", "browser_cache": "浏览器缓存", "log": "日志", "temp": "临时文件",
    "upgrade": "旧安装包", "migold": "迁移旧副本", "shadercache": "显卡缓存",
    "installer": "安装包残留", "crash": "崩溃记录", "thumb": "缩略图缓存",
    "data_stage": "安装暂存", "node_modules": "项目依赖", "runtime": "运行时依赖",
    "config": "配置/数据", "cache_root": "通用缓存", "win_appcache": "应用缓存",
}

# ── 禁区判定：只认「位置」，不认「名字」──────────────────
# 曾经踩过的坑：C:\Windows 和 AppData\Local\Microsoft\Windows 同名，
# 按裸名字判会把这 792 MB 应用缓存也锁死 → 用户看到能删的东西被无缘无故禁掉，
# 等于告诉用户「别信这个清单」。所以拆成三张表。

# ① 无论在哪儿出现都禁：密钥、系统内核文件
FORBIDDEN_ANY = {
    ".ssh": "你的 SSH 密钥，删了连不上服务器",
    ".gnupg": "你的 GPG 密钥",
    ".git": "版本历史，删了代码回不去",
    ".git-credentials": "存着 Git 账号凭据，删了要重新登录",
    "id_rsa": "SSH 私钥，删了连不上服务器",
    "id_ed25519": "SSH 私钥，删了连不上服务器",
    "pagefile.sys": "虚拟内存文件，系统正在用",
    "hiberfil.sys": "休眠文件，关休眠要在电源设置里改",
    "swapfile.sys": "系统交换文件",
    "ntuser.dat": "你的用户注册表，删了账户会出问题",
    "driverstore": "驱动仓库，删了硬件可能失灵",
}

# ② 只有「盘根的直接子目录」才算禁——C:\Windows 是系统，D:\Windows 也是，
#    但 AppData\Local\Microsoft\Windows 只是重名，不算。
OS_ROOT_NAMES = {
    "windows": "系统本体，删了开不了机",
    "system32": "系统核心文件，删了开不了机",
    "syswow64": "系统核心文件，删了开不了机",
    "winsxs": "系统组件库，只能用 DISM 清，手删会坏更新",
    "servicing": "系统更新组件，删了以后装不了补丁",
    "assembly": "系统组件缓存，手删会坏 .NET",
    "program files": "已安装的软件，要卸载请用控制面板",
    "program files (x86)": "已安装的软件，要卸载请用控制面板",
    "programdata": "所有用户共用的程序数据，删了软件会异常",
    "system volume information": "系统还原与卷信息，系统正在用",
    "$recycle.bin": "回收站",
    "recovery": "系统恢复分区的内容",
    "boot": "启动文件",
    "bootmgr": "启动管理器",
    "efi": "UEFI 启动分区",
    "fonts": "系统字体，删了文字会变方块",
    "catroot": "驱动签名目录",
    "inf": "系统驱动安装信息",
}

# ③ 已经在系统目录内部了 → 一律禁区（用 collect 一般到不了这层，兜底）
SYSTEM_ANCESTORS = {"windows", "system32", "syswow64", "winsxs", "servicing"}

# ④ macOS 盘根守卫
POSIX_ROOT_NAMES = {
    "system": "macOS 系统本体，删了开不了机",
    "usr": "系统 Unix 目录，删了命令全废",
    "bin": "系统命令目录",
    "sbin": "系统命令目录",
    "etc": "系统配置目录",
    "private": "系统内核与配置目录",
    "var": "系统数据目录",
    "library": "系统级资源库（应用的才在 ~/Library）",
    "applications": "已安装的应用，要卸载请拖进废纸篓",
    "cores": "系统崩溃转储",
    "dev": "设备文件",
}

# ⑤ 名字像系统、其实是应用缓存的（放在 AppData 里才成立）
APPDATA_CACHE_NAMES = {
    "windows", "explorer", "inetcache", "wer", "fontcache", "shell",
    "temporary internet files", "webcache", "d3dscache", "usoshared",
    "settingsync",
}

# ⑥ macOS：这些目录下面的任何东西都不许碰（和 SYSTEM_ANCESTORS 同义）
POSIX_ANCESTORS = {
    "system", "usr", "bin", "sbin", "private", "var", "etc", "cores", "dev",
    "applications", "library",
}


# ── 锁死的容器，允许「探进去找可删的子项」的白名单 ────────────
# 曾经的设计缺陷：collect() 一旦在父级命中 forbidden 就 continue，
# 于是 Packages\DATA（规则表里明明是 ✅ 安装暂存）永远不出现在清单上，
# 用户看得到 3.4 GB 被锁死，却勾不到里面那 2 GB 能删的。
# 规则表内部自相矛盾：子项判可删，父项把子项一起吞了。
#
# 但也不能无条件往下钻 —— 钻 C:\Windows 会挖出一堆「看起来能删」的东西。
# 所以只开白名单，且容器内部**只收 safe**，caution/forbidden 一律不再展开。
DESCEND_LOCKED = {
    # 容器名 : 必须满足的路径后缀
    "packages": "\\appdata\\local\\packages",
    # 这三个是「整体不能删，但里面堆着安装残留」的重灾区。
    # 实测 C 盘：ProgramData\NVIDIA\Downloader 1.63 GB 旧驱动、
    # ProgramData\Adobe\ARM 1.01 GB 旧补丁、InstallShield 921 MB 存着的安装包。
    "programdata": "\\programdata",
    "program files": "\\program files",
    "program files (x86)": "\\program files (x86)",
}


def may_descend(name, path):
    want = DESCEND_LOCKED.get((name or "").lower().strip())
    if not want:
        return False
    return norm(path).lower().endswith(want)


# 这些位置普通权限删不动，必须提权。清单里要提前标出来，
# 否则用户勾了半天，执行时一条条撞「拒绝访问」—— 实测 16 项里就废了 5 项。
ADMIN_PREFIXES = (
    "c:\\program files\\",
    "c:\\program files (x86)\\",
    "c:\\programdata\\",
    "c:\\windows\\",
)


def needs_admin(path):
    p = norm(path).lower() + "\\"
    return any(p.startswith(pre) for pre in ADMIN_PREFIXES)


def norm(p):
    """统一成反斜杠、折叠重复分隔符、去掉结尾分隔符。UNC 前缀保留。"""
    p = (p or "").replace("/", "\\")
    lead = "\\\\" if p.startswith("\\\\") else ""
    p = lead + re.sub(r"\\+", lambda m: "\\", p.lstrip("\\"))
    return p.rstrip("\\")


def _segs(p):
    return [s for s in norm(p).lower().split("\\") if s]


def _is_drive_child(segs):
    """是否盘根的直接子目录：C:\\Windows、/System"""
    if not segs:
        return False
    if re.fullmatch(r"[a-z]:", segs[0]):
        return len(segs) == 2
    return len(segs) == 1


def classify(name, path):
    """返回 (verdict, kind, hint) 或 None"""
    n = name.lower().strip()
    p = norm(path).lower()
    segs = _segs(p)

    # ── A) 任何位置都禁 ──────────────────────────────
    if n in FORBIDDEN_ANY:
        return ("forbidden", None, FORBIDDEN_ANY[n])

    # ── B) 系统目录：看位置，不看名字 ──────────────────
    # 关键：AppData 里的同名目录不是系统目录（C:\Windows ≠ ...\AppData\Local\Microsoft\Windows）
    in_appdata = "\\appdata\\" in p
    if not in_appdata:
        if any(s in SYSTEM_ANCESTORS for s in segs[:-1]):
            return ("forbidden", None, "这是系统目录里的东西，不能删")
        if segs[0] in POSIX_ANCESTORS:
            return ("forbidden", None, "这是 macOS 系统目录，不能删")
    if n in OS_ROOT_NAMES and _is_drive_child(segs):
        return ("forbidden", None, OS_ROOT_NAMES[n])
    if n in POSIX_ROOT_NAMES and _is_drive_child(segs):
        return ("forbidden", None, POSIX_ROOT_NAMES[n])

    # UWP 应用数据：里面是真实数据（存档、设置），不能整个端
    if n == "packages" and p.endswith("\\appdata\\local\\packages"):
        return ("forbidden", None, "UWP 应用的数据，里面有存档和设置，不能整个删")

    # 个人文档类：可见但禁止（只拦"看上去像存档"的）
    if re.search(r"\\(documents|desktop|pictures|videos|music|downloads)\\", p):
        if re.search(r"^(saves?|saved|存档|profile|userdata)$", n) or n in {
            "konami", "rockstar games", "mount & blade", "mount and blade"}:
            return ("forbidden", None, "游戏存档或用户数据，删了进度就没了")

    # ── C) 名字像系统、其实是 AppData 里的缓存 ────────────
    if n in APPDATA_CACHE_NAMES and "\\appdata\\" in p:
        return ("safe", "win_appcache", None)

    # ── D) safe —— 先判更具体的，再判通用的 ──────────────
    # （顺序不能反：dxcache 会被 .*cache 抢走，文案就错了）

    # 安装残留：名字看不出用途（527.56-desktop-win10-...exe），只能靠「它躺在哪个目录」判断。
    # 注意排除 \users\ —— 用户自己的「下载」文件夹里的安装包不能替人决定。
    if re.search(r"\.(msp|msu)$", n):
        return ("safe", "installer", None)
    if "\\users\\" not in p and re.search(r"\.(exe|msi|msix)$", n) and re.search(
            r"\\(downloader|download|updates?|upgrades?|patch|patches)\\", p):
        return ("safe", "installer", None)
    # InstallShield 的安装信息目录里存的是安装包本体，不是程序
    if "\\installshield installation information\\" in p and re.search(r"\.(exe|msi)$", n):
        return ("safe", "installer", None)

    if n in ("dxcache", "glcache", "shadercache", "nv_cache", "nvidia cache"):
        return ("safe", "shadercache", None)
    if n == "windows.old":
        return ("safe", "migold", None)
    if n.endswith("migold") or n.endswith(".migold"):
        return ("safe", "migold", None)
    if n.endswith("cache") and n not in ("", "cache_"):
        if "user data" in p:
            return None
        # 根目录下的 .cache / .caches 常混着下载好的运行时，单独归谨慎
        if n in (".cache", ".caches") and p.count("\\") <= 3:
            return ("caution", "cache_root", None)
        return ("safe", "cache", None)
    if n in ("cache", "caches", "code cache", "gpucache", "cacheddata"):
        return ("safe", "cache", None)
    if re.fullmatch(r".*\.(log|elog|dmp|etl)", n) or n in ("log", "logs", "logfiles", "crashlogs"):
        return ("safe", "log", None)
    if n in ("temp", "tmp", ".tmp", "temporary items"):
        return ("safe", "temp", None)
    if n in ("upgrade", "upgrades", "updater"):
        return ("safe", "upgrade", None)
    if re.fullmatch(r".*\.(msi|msix|msixbundle|appx)", n):
        return ("safe", "installer", None)
    if n in ("crashpad", "crashdumps", "reports") and "crash" in p:
        return ("safe", "crash", None)
    if n in ("thumbcache", "thumbnails"):
        return ("safe", "thumb", None)
    if n == "data" and "packages" in p:
        return ("safe", "data_stage", None)

    # ── E) caution ──────────────────────────────────
    if n == "node_modules":
        return ("caution", "node_modules", None)
    if n in ("runtimes", "runtime", "runtimes-download"):
        return ("caution", "runtime", None)
    if n in ("user data", "userdata", "profile", "profiles"):
        return ("caution", "config", None)
    return None


def collect(node, out, depth=0, locked=""):
    """自顶向下扫，命中的节点整体收走（避免父子重复）。

    `locked` = 当前所处的「锁死容器」路径。进了锁定容器只收 safe，
    别的档位一律不出 —— 父项已经说了不能删，就不该在下面列一堆要人判断的。
    """
    for child in node.get("children", []):
        size = child.get("size", 0)
        name = child.get("name", "")
        path = child.get("path", "")
        hit = classify(name, path)

        if hit:
            verdict, kind, hint = hit

            # 锁死的容器，但里面有单独可删的子项 → 探进去，子项单独上清单
            if verdict == "forbidden" and may_descend(name, path):
                inner = []
                collect(child, inner, depth + 1, locked=path)
                out.extend(inner)
                if size >= MIN_BYTES and depth < 8:
                    out.append({
                        "path": path, "name": name, "size": size,
                        "files": child.get("files", 0),
                        "verdict": "forbidden", "kind": "other",
                        "kindLabel": "整个不能删",
                        "worst": hint or "",
                        "hint": hint or "",
                        "lockedParent": "",
                        "needsAdmin": needs_admin(path),
                        "innerCount": len(inner),
                        "innerBytes": sum(i["size"] for i in inner),
                    })
                continue

            # 在锁定容器内部：只认 safe，其余不展开也不上清单
            if locked and verdict != "safe":
                continue

            if size >= MIN_BYTES and depth < 8:
                out.append({
                    "path": path,
                    "name": name,
                    "size": size,
                    "files": child.get("files", 0),
                    "verdict": verdict,
                    "kind": kind or "other",
                    "kindLabel": KIND_LABEL.get(kind, "文件"),
                    "worst": WORST.get(kind, "删了以后可能需要重新下载或重新生成，具体看那个软件的说明。"),
                    "hint": hint or "",
                    "lockedParent": locked,
                    "needsAdmin": needs_admin(path),
                })
                continue

        if depth < 8 and child.get("children"):
            collect(child, out, depth + 1, locked=locked)


def verify_migold(items):
    """`.migold` 只有在「对应的在用版本确实存在」时才算旧副本。

    这是清单里唯一一条靠推断得出的 verdict，必须落实：
    Chromium 系的 `User Data.migold` 如果是唯一一份，勾了就是清掉全部书签密码。
    """
    for it in items:
        if it.get("kind") != "migold":
            continue
        p = it["path"]
        if not p.lower().endswith(".migold"):
            continue
        base = p[: -len(".migold")]
        if os.path.exists(base):
            continue
        it["verdict"] = "caution"
        it["worst"] = (
            "我找不到它对应的在用版本（%s 不存在），说明这可能是唯一的一份数据。"
            "先别勾，让我进去看一眼里面是什么再说。" % os.path.basename(base))


def shoot(html_path, png_path, size="1300x1500", wait_ms=1800, full=False):
    """把清单截成 PNG —— 对话里、分享页里都能直接看见。"""
    from playwright.sync_api import sync_playwright
    w, h = [int(x) for x in size.lower().split("x")]
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=1.5)
        pg.goto("file:///" + html_path.replace("\\", "/"))
        pg.wait_for_timeout(wait_ms)
        pg.screenshot(path=png_path, full_page=full)
        b.close()


def build(scan_json, out="", min_mb=100.0):
    """生成清单 HTML，返回 (out_path, stats)。

    给 make_report.py 的 --with-checklist 复用：一次扫描、两件产物，
    不让用户再开口要一次。stats 里的数字直接用于汇报。
    """
    global MIN_BYTES
    MIN_BYTES = int(min_mb * 1024 * 1024)

    with open(scan_json, encoding="utf-8") as f:
        scan = json.load(f)

    items = []
    collect(scan["tree"], items)

    # 同一路径只留一条；按大小降序
    seen, uniq = set(), []
    for it in items:
        if it["path"] in seen:
            continue
        seen.add(it["path"])
        uniq.append(it)
    uniq.sort(key=lambda x: -x["size"])
    verify_migold(uniq)

    data = {
        "root": scan.get("root", ""),
        "scanned_at": scan.get("scanned_at", ""),
        "total_size": scan.get("total_size", 0),
        "dedup_bytes": scan.get("dedup_bytes", 0),
        "min_mb": round(MIN_BYTES / 1024 / 1024, 1),
        "items": uniq,
    }

    with open(TEMPLATE, encoding="utf-8") as f:
        tpl = f.read()
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = tpl.replace("/*__DATA__*/", payload)

    out = os.path.abspath(out or os.path.splitext(scan_json)[0] + "_cleanup.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)

    def pack(v):
        g = [i for i in uniq if i["verdict"] == v]
        return {"count": len(g), "bytes": sum(i["size"] for i in g)}

    return out, {
        "safe": pack("safe"),
        "caution": pack("caution"),
        "forbidden": pack("forbidden"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scan_json", nargs="?", default="")
    ap.add_argument("-o", "--out", default="")
    ap.add_argument("--open", action="store_true")
    ap.add_argument("--min-mb", type=float, default=100)
    ap.add_argument("--png", action="store_true", help="同时导出一张 PNG")
    ap.add_argument("--png-size", default="1300x1500")
    ap.add_argument("--png-full", action="store_true", help="PNG 截整页（很长）")
    ap.add_argument("--why", nargs="+", default=None,
                    help="自查模式：只打印这些路径的判定结果，不生成 HTML")
    args = ap.parse_args()

    # 自查：python make_checklist.py --why "C:\\Windows" "C:\\Users\\a\\AppData\\Local\\Microsoft\\Windows"
    if args.why:
        for p in args.why:
            p = norm(p)
            nm = os.path.basename(p) or p
            hit = classify(nm, p)
            if not hit:
                print("  ——   %s\n         → 不归类（交给更深一层）" % p)
                continue
            v, k, hint = hit
            mark = {"forbidden": "🚫", "caution": "⚠️ ", "safe": "✅"}[v]
            print("  %s   %s\n         → %s / %s%s" % (
                mark, p, v, KIND_LABEL.get(k, "—"),
                ("  |  " + hint) if hint else ""))
        return 0

    if not args.scan_json:
        ap.error("需要 scan.json（或用 --why 自查）")

    out, st = build(args.scan_json, args.out, args.min_mb)
    h = lambda n: "%.1f GB" % (n / 1024**3) if n >= 1024**3 else "%.0f MB" % (n / 1024**2)

    print("✓ 清理清单: %s" % out)
    print("  放心删 %d 项 / %s" % (st["safe"]["count"], h(st["safe"]["bytes"])))
    print("  你决定 %d 项 / %s" % (st["caution"]["count"], h(st["caution"]["bytes"])))
    print("  禁止删 %d 项（界面里锁死）" % st["forbidden"]["count"])
    if args.png:
        png = os.path.splitext(out)[0] + ".png"
        try:
            shoot(out, png, args.png_size, full=args.png_full)
            print("  图片: %s" % png)
        except Exception as e:
            print("  ⚠ 截图失败（HTML 已生成，可直接打开）: %s" % e)
    if args.open:
        try:
            os.startfile(out)
        except AttributeError:
            import subprocess
            subprocess.run(["open" if sys.platform == "darwin" else "xdg-open", out], check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
