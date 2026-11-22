# -*- coding: utf-8 -*-
"""从 H5 bundle 里提取 18 个称号图标（rP Map: comment_N -> base64 PNG）。"""
import base64
import io
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
JS = Path(r"reqable_export\335_web.hycdn.cn.txt")
OUT = Path(r"frontend\public\art\titles")
OUT.mkdir(parents=True, exist_ok=True)

text = JS.read_text(encoding="utf-8", errors="replace")
start = text.index("rP=new Map([")
end = text.index("])", start)
block = text[start:end]

pairs = re.findall(r'\["(comment_\d+)"\s*,\s*"(data:image/png;base64,[A-Za-z0-9+/=]+)"\]', block)
print("命中称号图标:", len(pairs))
for title_id, uri in pairs:
    raw = base64.b64decode(uri.split(",", 1)[1])
    (OUT / f"{title_id}.png").write_bytes(raw)
    print(f"  {title_id:<12} {len(raw):>6}B")
print("输出目录:", OUT)

