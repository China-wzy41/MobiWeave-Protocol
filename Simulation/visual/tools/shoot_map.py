"""把地图窗口在若干时刻截成图片，用于文档与验收（不需要人手点）。"""

from __future__ import annotations

import ctypes
import os
import sys

from PIL import ImageGrab

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from visual.mapview import MapView  # noqa: E402

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:  # pragma: no cover - 老系统没有 shcore
    pass


PLANS = {
    "sim": [(0.0, "map-hike-00-开局.png"), (120.0, "map-hike-01-携带中.png"),
            (495.0, "map-hike-02-首次送达.png"), (880.0, "map-hike-03-末段.png")],
    "sim-inspection": [(0.0, "map-insp-00-开局.png"), (390.0, "map-insp-01-首单送达.png"),
                       (860.0, "map-insp-02-末段.png")],
    "sim-lab": [(0.0, "map-lab-00-开局.png"), (245.0, "map-lab-01-首单送达.png"),
                (560.0, "map-lab-02-末段.png")],
}


def main() -> int:
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    out_dir = os.path.join(base, "docs", "shots")
    os.makedirs(out_dir, exist_ok=True)

    for folder, shots in PLANS.items():
        trace = os.path.join(base, folder, "trace.jsonl")
        log = os.path.join(base, folder, "log.jsonl")
        if not os.path.exists(trace):
            print("跳过（没有数据）", folder)
            continue
        app = MapView(trace, log)
        app.update()
        app.geometry("1280x760")
        app.update()
        app.update_idletasks()
        for t, name in shots:
            app._seek_time(t)
            app._render()
            app.update()
            app.update_idletasks()
            x, y = app.winfo_rootx(), app.winfo_rooty()
            w, h = app.winfo_width(), app.winfo_height()
            image = ImageGrab.grab(bbox=(x, y, x + w, y + h))
            path = os.path.join(out_dir, name)
            image.save(path)
            print("拍好", name, image.size)
        app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
