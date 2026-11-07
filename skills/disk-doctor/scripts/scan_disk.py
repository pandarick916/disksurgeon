#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""硬盘扫描器（Windows / macOS）：只读遍历，输出树形 JSON 供可视化用。

设计原则（fail-closed）：
  · 只读。不删、不移动、不改任何文件。
  · 权限不够的目录记为 skipped，不中断整体扫描。
  · 符号链接 / junction / symlink 一律不跟随（避免绕圈 + 重复计数）。
  · 硬链接去重：同一份数据被多个路径引用时，只在第一次出现时计尺寸。

跨平台说明：
  · Windows：必须用 os.stat() 才能拿到 nlink/ino —— DirEntry.stat() 在 Windows 上
    这两个字段恒为 0（走的是快速属性查询，不打开句柄）。代价是慢一些，
    但数字准确比快重要；急的话加 --fast 跳过去重。
  · macOS：stat 天然带 ino/nlink，无额外开销。需跳过 /System/Volumes
    （那是数据卷的另一个挂载点，和 /Users 是同一份数据）。

用法：
    python scan_disk.py                          # Windows 扫 C:\ ，macOS 扫 /
    python scan_disk.py --path D:\
    python scan_disk.py --path ~/ --min-size 20 --depth 6
    python scan_disk.py --path / --fast          # 跳过硬链接去重，更快
"""
import argparse
import json
import os
import shutil
import sys
import time

IS_WIN = (os.name == "nt")
DEFAULT_ROOT = "C:\\" if IS_WIN else "/"

SKIP_NAMES = {
    # Windows
    "System Volume Information", "$RECYCLE.BIN", "$Recycle.Bin",
    "pagefile.sys", "hiberfil.sys", "swapfile.sys",
    # macOS
    ".Spotlight-V100", ".fseventsd", ".DocumentRevisions-V100",
    ".TemporaryItems", ".Trashes",
}

# macOS：这些路径是别的卷的挂载点，扫进去就是重复计数
SKIP_ABS_PREFIX = () if IS_WIN else ("/System/Volumes", "/Volumes")


def human(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024.0:
            return "%.1f%s" % (n, unit) if unit != "B" else "%d%s" % (n, unit)
        n /= 1024.0
    return "%.1fPB" % n


class Scanner:
    def __init__(self, min_bytes=1 << 20, max_depth=8, dedup=True):
        self.min_bytes = min_bytes
        self.max_depth = max_depth
        self.dedup = dedup
        self.files = 0
        self.dirs = 0
        self.skipped = 0
        self.errors = []
        # (st_dev, st_ino) -> 首次出现的路径
        self.inodes = {}
        self.dedup_bytes = 0
        self.dedup_files = 0

    # ── 基础工具 ──────────────────────────────────────────
    def skip_dir(self, path, name):
        if name in SKIP_NAMES:
            return True
        for pre in SKIP_ABS_PREFIX:
            if path == pre or path.startswith(pre + os.sep):
                return True
        return False

    def stat_file(self, entry):
        """拿准确的 nlink/ino。Windows 上 DirEntry.stat() 这两个字段是 0。"""
        if self.dedup:
            return os.stat(entry.path, follow_symlinks=False)
        return entry.stat(follow_symlinks=False)

    def account(self, st, path):
        """返回应计入的字节数；重复的硬链接返回 0。"""
        sz = st.st_size
        if self.dedup and st.st_nlink > 1:
            key = (st.st_dev, st.st_ino)
            if key in self.inodes:
                self.dedup_bytes += sz
                self.dedup_files += 1
                return 0
            self.inodes[key] = path
        return sz

    # ── 主扫描 ────────────────────────────────────────────
    def scan(self, path, depth=0):
        node = {"name": os.path.basename(path.rstrip("\\/")) or path,
                "path": path, "size": 0, "files": 0, "children": []}
        try:
            entries = list(os.scandir(path))
        except (PermissionError, OSError) as e:
            self.skipped += 1
            if len(self.errors) < 20:
                self.errors.append("%s: %s" % (path, e.__class__.__name__))
            return node

        kids = []
        for e in entries:
            try:
                if e.is_dir(follow_symlinks=False):
                    self.dirs += 1
                    if self.skip_dir(e.path, e.name):
                        continue
                    if depth < self.max_depth:
                        sub = self.scan(e.path, depth + 1)
                        node["size"] += sub["size"]
                        node["files"] += sub["files"]
                        if sub["size"] >= self.min_bytes:
                            kids.append(sub)
                        elif sub["size"] > 0:
                            node["_small"] = node.get("_small", 0) + sub["size"]
                    else:
                        sz = self.dir_size_deep(e.path)   # 超深度：只统计不展开
                        node["size"] += sz
                        node["_small"] = node.get("_small", 0) + sz
                elif e.is_file(follow_symlinks=False):
                    self.files += 1
                    st = self.stat_file(e)
                    sz = self.account(st, e.path)
                    node["size"] += sz
                    node["files"] += 1
                    if sz >= self.min_bytes:
                        kids.append({"name": e.name, "path": e.path,
                                     "size": sz, "files": 1, "children": [],
                                     "file": True})
                    elif sz > 0:
                        node["_small"] = node.get("_small", 0) + sz
            except (PermissionError, OSError):
                self.skipped += 1
                continue

        kids.sort(key=lambda x: -x["size"])
        node["children"] = kids
        return node

    def dir_size_deep(self, path):
        """不建树，只算总量（超过深度限制时用）。同样做硬链接去重。"""
        total = 0
        stack = [path]
        while stack:
            cur = stack.pop()
            try:
                for e in os.scandir(cur):
                    try:
                        if e.is_dir(follow_symlinks=False):
                            if not self.skip_dir(e.path, e.name):
                                stack.append(e.path)
                        elif e.is_file(follow_symlinks=False):
                            self.files += 1
                            total += self.account(self.stat_file(e), e.path)
                    except OSError:
                        continue
            except OSError:
                continue
        return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default=DEFAULT_ROOT)
    ap.add_argument("--min-size", type=float, default=50, help="只保留大于该 MB 的节点")
    ap.add_argument("--depth", type=int, default=7)
    ap.add_argument("--out", default="disk_scan.json")
    ap.add_argument("--fast", action="store_true",
                    help="跳过硬链接去重（更快，但 WinSxS 这类目录会虚高）")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    root = os.path.normpath(os.path.expanduser(args.path))
    if not os.path.isdir(root):
        print("✗ 路径不存在: %s" % root)
        sys.exit(2)

    min_b = int(args.min_size * 1024 * 1024)
    sc = Scanner(min_bytes=min_b, max_depth=args.depth, dedup=not args.fast)

    t0 = time.time()
    if not args.quiet:
        print("扫描 %s（只读，不改任何文件）…%s"
              % (root, "" if not args.fast else "  [--fast 已关闭硬链接去重]"), flush=True)

    tree = sc.scan(root)
    elapsed = time.time() - t0

    # 拿系统口径对一次账：数字对不上时，要由工具自己说出来，
    # 不能等用户发现「你这数比 Windows 报的多」才解释。
    disk = None
    try:
        tu = shutil.disk_usage(root if os.path.abspath(root) else ".")
        disk = {"total": tu.total, "used": tu.used, "free": tu.free,
                "delta": tree["size"] - tu.used}
    except Exception:
        pass

    data = {
        "platform": "windows" if IS_WIN else "macos",
        "root": root,
        "scanned_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_sec": round(elapsed, 1),
        "total_size": tree["size"],
        "total_files": sc.files,
        "total_dirs": sc.dirs,
        "skipped": sc.skipped,
        "dedup_bytes": sc.dedup_bytes,
        "dedup_files": sc.dedup_files,
        "min_size_mb": args.min_size,
        "disk": disk,
        "errors": sc.errors,
        "tree": tree,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

    if not args.quiet:
        print("✓ 完成：%s ／ %d 个文件 ／ %.1f 秒 ／ 跳过 %d 处（无权限）"
              % (human(tree["size"]), sc.files, elapsed, sc.skipped))
        if sc.dedup_bytes:
            print("  硬链接去重：少算 %s（%d 个重复引用，数据其实只存了一份）"
                  % (human(sc.dedup_bytes), sc.dedup_files))
        if disk and abs(disk["delta"]) > 512 << 20:
            print("  ⚠ 对账：系统已用 %s，本次统计 %s，差 %s"
                  % (human(disk["used"]), human(tree["size"]), human(abs(disk["delta"]))))
            if disk["delta"] > 0:
                print("     偏多通常是：压缩/稀疏文件按逻辑大小算、OneDrive 占位符没真占盘、"
                      "硬链接还有没认出来的；偏少通常是上面那 %d 处没权限的目录。"
                      % sc.skipped)
            else:
                print("     偏少通常是：%d 处目录没权限没进去、或部分文件被系统占用读不到。"
                      % sc.skipped)
        print("  → %s" % os.path.abspath(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
