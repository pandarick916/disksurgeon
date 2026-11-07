"""Generate a fully synthetic scan.json used for the README screenshot.

No real machine data is involved: every path below is invented, and the
user name is the literal string "demo". Run this from the repo root:

    python docs/gen_demo.py
    python skills/disk-doctor/scripts/make_report.py docs/demo-scan.json --png
"""

import json

GB = 1024 ** 3
ROOT = "C:\\"


def node(name, parent, gb, nfiles, children=None, small_mb=0):
    path = ROOT + name if parent is None else parent + "\\" + name
    kids = children or []
    size = int(gb * GB) + sum(k["size"] for k in kids) + int(small_mb * 1024 ** 2)
    return {
        "name": name,
        "path": path,
        "size": size,
        "files": nfiles + sum(k["files"] for k in kids),
        "children": kids,
        "_small": int(small_mb * 1024 ** 2),
    }


def appdata():
    local = node("Local", None, 0, 0, [
        node("Google", None, 4.1, 6000),
        node("Packages", None, 2.4, 4000),
        node("ms-playwright", None, 2.2, 2200),
        node("Microsoft", None, 1.6, 5000),
        node("JianyingPro", None, 1.2, 1800),
        node("Temp", None, 0.5, 9000),
    ], small_mb=380)
    roaming = node("Roaming", None, 0, 0, [
        node("Tencent", None, 6.2, 5000),
        node("Baidu", None, 1.1, 900),
        node("360safe", None, 0.6, 700),
    ], small_mb=240)
    local_low = node("LocalLow", None, 0, 0, [
        node("NVIDIA", None, 1.3, 400),
    ], small_mb=60)
    a = node("AppData", None, 0, 0, [local, roaming, local_low])
    for k in a["children"]:
        k["path"] = a["path"] + "\\" + k["name"]
        for g in k["children"]:
            g["path"] = k["path"] + "\\" + g["name"]
    return a


def users():
    a = appdata()
    kids = [
        a,
        node("Documents", None, 6.5, 4000),
        node(".cache", None, 0, 0, [
            node("codex-runtimes", None, 2.0, 900),
            node("hyperframes", None, 1.2, 500),
            node("npm", None, 0.9, 800),
            node("pip", None, 0.9, 600),
        ], small_mb=140),
        node("Downloads", None, 4.2, 300),
        node(".codex", None, 3.5, 1500),
        node("Desktop", None, 2.8, 900),
    ]
    u = node("Users", None, 0, 300, kids, small_mb=520)
    u["path"] = ROOT + "Users"
    for k in u["children"]:
        k["path"] = u["path"] + "\\" + k["name"]
    a["path"] = u["path"] + "\\AppData"
    for k in a["children"]:
        k["path"] = a["path"] + "\\" + k["name"]
        for g in k["children"]:
            g["path"] = k["path"] + "\\" + g["name"]
    for k in u["children"]:
        for g in k["children"]:
            g["path"] = k["path"] + "\\" + g["name"]
    return u


def windows():
    w = node("Windows", None, 0, 40000, [
        node("WinSxS", None, 6.8, 90000),
        node("System32", None, 4.2, 50000),
        node("Installer", None, 2.1, 12000),
        node("assembly", None, 1.4, 9000),
        node("SysWOW64", None, 1.1, 15000),
        node("Fonts", None, 0.6, 700),
    ], small_mb=420)
    w["path"] = ROOT + "Windows"
    for k in w["children"]:
        k["path"] = w["path"] + "\\" + k["name"]
    return w


def main():
    top = [
        users(),
        windows(),
        node("Program Files", None, 8.2, 14000, small_mb=300),
        node("Program Files (x86)", None, 10.5, 16000, small_mb=300),
        node("ProgramData", None, 6.8, 9000, small_mb=260),
        node("Games", None, 6.2, 3000),
        node("pagefile.sys", None, 4.8, 1),
    ]
    total = sum(t["size"] for t in top)
    tree = {
        "name": ROOT,
        "path": ROOT,
        "size": total,
        "files": sum(t["files"] for t in top),
        "children": top,
        "_small": 0,
    }
    out = {
        "platform": "windows",
        "root": ROOT,
        "scanned_at": "2026-11-07 21:30:00",
        "elapsed_sec": 90.3,
        "total_size": total,
        "total_files": tree["files"],
        "total_dirs": 200661,
        "skipped": 266,
        "dedup_bytes": int(8.7 * GB),
        "dedup_files": 38711,
        "min_size_mb": 50.0,
        "errors": [],
        "tree": tree,
    }
    with open("docs/demo-scan.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("demo total: %.1f GB -> docs/demo-scan.json" % (total / GB))


if __name__ == "__main__":
    main()
