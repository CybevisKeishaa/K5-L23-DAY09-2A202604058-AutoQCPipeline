"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict

import yaml

from ..common import ERROR, parse_yolo_line

DROP = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}
REMOVE = {"LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}          # + mọi mã DUP_IMAGE_*


def _clip(text):
    """Cắt box về [0,1], giữ lớp; trả dòng mới, hoặc None nếu box không còn diện tích."""
    c, x, y, w, h = parse_yolo_line(text)
    x1, x2 = max(0.0, x - w / 2), min(1.0, x + w / 2)
    y1, y2 = max(0.0, y - h / 2), min(1.0, y + h / 2)
    nw, nh = round(x2 - x1, 6), round(y2 - y1, 6)
    if nw <= 0 or nh <= 0:
        return None
    return f"{c} {(x1 + x2) / 2:.6f} {(y1 + y2) / 2:.6f} {nw:.6f} {nh:.6f}"


def fix(ds, issues, cfg):
    errs = [i for i in issues if i.severity == ERROR]
    fixes = []

    def log(image, line, action, before, after):
        fixes.append(dict(image=image, line="" if line is None else line, action=action, before=before, after=after))

    # 1) xoá ảnh (trùng / rò rỉ / hỏng / sai cỡ) trước, để bỏ qua issue dòng của ảnh đã xoá
    removed = set()
    for i in errs:
        if (i.code in REMOVE or i.code.startswith("DUP_IMAGE_")) and i.image not in removed:
            removed.add(i.image)
            img, lab = ds.image_path(i.image), ds.label_path(i.image)
            if img is None and not lab.exists():     # đã xoá ở lần chạy trước
                continue
            if img is not None:
                img.unlink()
            if lab.exists():
                lab.unlink()
            log(i.image, None, "remove_image", img.name if img else lab.name, f"(đã xoá ảnh + nhãn: {i.code})")

    # 2) ảnh chưa có nhãn: máy không bịa nhãn (kể cả file rỗng), chuyển người gán
    for i in errs:
        if i.code == "MISSING_LABEL_FILE" and i.image not in removed and not ds.label_path(i.image).exists():
            log(i.image, None, "needs_label", "(không có file)", "chuyển người gán")

    # 3) tên lớp trong data.yaml
    if any(i.code == "BAD_CLASS_NAME" for i in errs):
        want = list(cfg["classes"])
        old = ds.yaml_names()
        if [old.get(k) for k in range(len(old))] != want:
            d = (yaml.safe_load(ds.yaml_path.read_text(encoding="utf-8")) if ds.yaml_path.exists() else None) or {}
            d["names"] = want
            ds.yaml_path.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")
            log("data.yaml", None, "rename_classes", str([old[k] for k in sorted(old)]), str(want))

    # 4) sửa dòng: gom theo file, dùng số dòng GỐC (kể cả dòng trống), ghi lại MỘT lần
    by_file = defaultdict(lambda: defaultdict(set))
    for i in errs:
        if i.line is not None and (i.code in DROP or i.code == "BOX_OUT_OF_IMAGE"):
            by_file[i.image][i.line].add(i.code)
    for stem, per_line in by_file.items():
        p = ds.label_path(stem)
        if stem in removed or not p.exists():
            continue
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        drop = set()
        for n in sorted(per_line):
            if not 1 <= n <= len(lines) or not lines[n - 1].strip():
                continue
            before = lines[n - 1]
            if per_line[n] & DROP:                   # xoá thắng cắt: mỗi dòng chỉ một fix
                drop.add(n)
                log(stem, n, "drop_line", before, "(xoá dòng)")
                continue
            try:
                new = _clip(before)
            except ValueError:
                new = None
            if new is None:
                drop.add(n)
                log(stem, n, "drop_line", before, "(xoá dòng: box nằm hẳn ngoài ảnh)")
            else:
                lines[n - 1] = new
                log(stem, n, "clip_box", before, new)
        p.write_text("".join(ln + "\n" for k, ln in enumerate(lines, 1) if k not in drop), encoding="utf-8")
    return fixes
