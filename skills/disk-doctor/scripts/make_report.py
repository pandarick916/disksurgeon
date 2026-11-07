#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""把扫描结果渲染成单文件 HTML 磁盘地图（纯代码，零外部依赖）。

用法：
    python make_report.py scan.json                 # 生成 scan.html
    python make_report.py scan.json --open          # 生成并自动打开浏览器
    python make_report.py scan.json -o D:\out.html
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(os.path.dirname(HERE), "templates", "report.html")
PLACEHOLDER = "/*__DATA__*/"


def shoot(html_path, png_path, size="1600x1000", wait_ms=2000):
    """把地图截成一张 PNG —— 对话里、分享页里都能直接看见。"""
    from playwright.sync_api import sync_playwright
    w, h = [int(x) for x in size.lower().split("x")]
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=2)
        pg.goto("file:///" + html_path.replace("\\", "/"))
        pg.wait_for_timeout(wait_ms)          # 等入场动画走完
        pg.screenshot(path=png_path)
        b.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scan_json")
    ap.add_argument("-o", "--out", default="")
    ap.add_argument("--open", action="store_true", help="生成后自动打开")
    ap.add_argument("--png", action="store_true", help="同时导出一张 PNG（对话/分享可直接看）")
    ap.add_argument("--png-size", default="1600x1000")
    ap.add_argument("--with-checklist", action="store_true",
                    help="顺手把可勾选清理清单也生成出来（同一个 scan.json，几乎零成本）")
    ap.add_argument("--min-mb", type=float, default=100,
                    help="清单只收这个大小以上的项")
    args = ap.parse_args()

    if not os.path.exists(args.scan_json):
        print("✗ 找不到扫描结果: %s" % args.scan_json)
        return 2
    if not os.path.exists(TEMPLATE):
        print("✗ 找不到模板: %s" % TEMPLATE)
        return 2

    with open(args.scan_json, encoding="utf-8") as f:
        data = json.load(f)

    with open(TEMPLATE, encoding="utf-8") as f:
        tpl = f.read()

    # 防止 JSON 里的 </script> 提前闭合脚本块
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

    html = tpl.replace(PLACEHOLDER, payload)

    out = args.out or os.path.splitext(args.scan_json)[0] + ".html"
    out = os.path.abspath(out)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)

    size_mb = os.path.getsize(out) / 1024 / 1024
    print("✓ 已生成: %s （%.1f MB）" % (out, size_mb))

    if args.png:
        png = os.path.splitext(out)[0] + ".png"
        try:
            shoot(out, png, args.png_size)
            print("✓ 图片: %s" % png)
        except Exception as e:
            print("! 截图失败（HTML 不受影响）: %s: %s" % (type(e).__name__, e))

    # ── 顺手出清单：地图和清单是同一份 scan.json 的两个视图 ──
    cl = ""
    if args.with_checklist:
        try:
            sys.path.insert(0, HERE)
            from make_checklist import build as build_checklist
            cl, st = build_checklist(
                args.scan_json,
                os.path.splitext(out)[0] + "_cleanup.html",
                args.min_mb,
            )
            gb = lambda n: "%.1f GB" % (n / 1024 ** 3) if n >= 1024 ** 3 else "%.0f MB" % (n / 1024 ** 2)
            print("✓ 清理清单: %s" % cl)
            print("  放心删 %d 项 / %s" % (st["safe"]["count"], gb(st["safe"]["bytes"])))
            print("  你决定 %d 项 / %s" % (st["caution"]["count"], gb(st["caution"]["bytes"])))
            print("  禁止删 %d 项（界面里锁死）" % st["forbidden"]["count"])
            # 分享页里 HTML 只是附件，清单也得有图才看得见
            if args.png:
                try:
                    from make_checklist import shoot as shoot_checklist
                    clpng = os.path.splitext(cl)[0] + ".png"
                    shoot_checklist(cl, clpng, "1300x1400")
                    print("  清单图: %s" % clpng)
                except Exception as e:
                    print("  ! 清单截图失败（不影响 HTML）: %s: %s" % (type(e).__name__, e))
        except Exception as e:
            print("! 清单生成失败（地图不受影响）: %s: %s" % (type(e).__name__, e))

    if args.open:
        try:
            os.startfile(out)  # noqa: S606  Windows
        except AttributeError:
            subprocess.run(["open" if sys.platform == "darwin" else "xdg-open", out], check=False)
        print("  已在浏览器打开")
        # 清单是"要动手"的那件，最后打开它，让它落在前台
        if cl:
            try:
                os.startfile(cl)  # noqa: S606  Windows
            except AttributeError:
                subprocess.run(["open" if sys.platform == "darwin" else "xdg-open", cl], check=False)
            print("  清单也打开了 —— 勾完点「复制清理指令」贴回来就行")
    return 0


if __name__ == "__main__":
    sys.exit(main())
