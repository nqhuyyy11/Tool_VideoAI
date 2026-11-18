"""Đổi file kịch bản Markdown thành dict giống kịch bản do AI viết.

Quy ước file .md:
    # Tiêu đề video            (tuỳ chọn, dòng # đầu tiên)
    Câu thoại cảnh 1 | english keywords
    Câu thoại cảnh 2
Mỗi dòng không rỗng là 1 cảnh; sau dấu | là từ khoá tiếng Anh để tìm video nền
(bỏ trống thì dùng cảnh thiên nhiên). Các dòng ##, ---, và dấu đầu dòng (-, *, 1.) bị bỏ qua/gỡ.
"""
import re

from .errors import UserError

MAX_SCENES = 30
MAX_SCENE_CHARS = 500


NARRATION = re.compile(r"^\*\*Lời đọc:?\*\*:?\s*(.+)$")


def parse(md: str) -> dict:
    title, scenes = None, []
    lines = md.splitlines()
    # File prompt kiểu "**Lời đọc:** ..." cho mỗi cảnh: chỉ lấy các dòng lời đọc làm thoại.
    narrations = [m.group(1) for m in (NARRATION.match(l.strip()) for l in lines) if m]
    if narrations:
        first = next((l for l in lines if re.match(r"#\s", l)), "")
        script: dict = {"scenes": [{"text": t.strip(), "keywords": ""} for t in narrations]}
        if first:
            script["title"] = first.lstrip("#").strip()[:200]
        return _check(script)
    for line in lines:
        line = line.strip()
        if line.startswith("#"):
            if title is None and re.match(r"#\s", line):
                title = line.lstrip("#").strip()[:200]
            continue
        line = re.sub(r"^(?:[-*+>]|\d+[.)])\s+", "", line)
        line = re.sub(r"[*_`]", "", line).strip()
        if not line or set(line) <= set("-=_ "):
            continue
        text, _, keywords = line.partition("|")
        text = text.strip()
        if text:
            scenes.append({"text": text, "keywords": keywords.strip()})
    script: dict = {"scenes": scenes}
    if title:
        script["title"] = title
    return _check(script)


def _check(script: dict) -> dict:
    scenes = script["scenes"]
    if not scenes:
        raise UserError("File kịch bản không có dòng thoại nào.")
    if len(scenes) > MAX_SCENES or any(len(s["text"]) > MAX_SCENE_CHARS for s in scenes):
        raise UserError(f"Kịch bản tối đa {MAX_SCENES} cảnh, mỗi cảnh tối đa {MAX_SCENE_CHARS} ký tự.")
    return script


if __name__ == "__main__":
    s = parse("# Tiêu đề\n\n## Cảnh\n- Xin chào | hello world\n---\n1. Tạm biệt\n")
    assert s["title"] == "Tiêu đề"
    assert s["scenes"] == [{"text": "Xin chào", "keywords": "hello world"},
                           {"text": "Tạm biệt", "keywords": ""}], s
    print("ok")
