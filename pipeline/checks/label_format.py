"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |

Gợi ý
- Mép trái = x - w/2, mép phải = x + w/2 (xem câu hỏi "dòng YOLO nào lỗi?" trong slide).
- Một dòng hỏng (BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO) thì `continue`, đừng kiểm tiếp hình học của dòng đó.
- Dòng thiếu cột làm script của slide dừng giữa chừng: đây là lý do phải `try/except`.
- `iou_xywh(a, b)` có sẵn trong common.py.
- Ngưỡng nằm trong `cfg["label_format"]` — đừng viết cứng số vào code.
"""
from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line


def run(ds, cfg):
    c = cfg["label_format"]
    tol, min_px, max_frac, dup_iou = c["overflow_tol"], c["min_box_px"], c["max_box_frac"], c["dup_box_iou"]
    n_cls = len(ds.classes)
    issues = []
    for img in ds.image_files():
        stem = img.stem
        lines = ds.read_label_lines(stem)
        if lines is None:                      # thiếu file nhãn: missing_labels báo
            continue
        size = ds.image_size(stem)

        def add(sev, code, n, msg, **extra):
            issues.append(Issue("label_format", sev, code, stem, msg, n, extra))

        seen = []                              # (lớp, box) của các dòng hợp lệ phía trên, để bắt DUP_BOX
        for n, text in lines:
            try:
                cls, x, y, w, h = parse_yolo_line(text)
            except ValueError as e:
                add(ERROR, "BAD_FORMAT", n, f"dòng hỏng: {e}")
                continue
            if not 0 <= cls < n_cls:
                add(ERROR, "BAD_CLASS_ID", n, f"id lớp {cls} ngoài 0..{n_cls - 1}", id=cls)
                continue
            if w <= 0 or h <= 0:
                add(ERROR, "BOX_ZERO", n, f"box rỗng w={w} h={h}")
                continue
            over = max(0.0, -(x - w / 2), x + w / 2 - 1, -(y - h / 2), y + h / 2 - 1)
            if over > tol:
                add(ERROR, "BOX_OUT_OF_IMAGE", n, f"box tràn ảnh {over:.4f}", overflow=round(over, 6))
            box = (x, y, w, h)
            if any(pc == cls and iou_xywh(pb, box) > dup_iou for pc, pb in seen):
                add(ERROR, "DUP_BOX", n, "box lặp với một dòng phía trên (cùng lớp)")
            seen.append((cls, box))
            short = min(w * size[0], h * size[1]) if size else None
            if short is not None and short < min_px:
                add(WARN, "BOX_TINY", n, f"cạnh ngắn {short:.1f}px < {min_px}px", short_px=round(short, 1))
            if w * h > max_frac:
                add(WARN, "BOX_HUGE", n, f"box chiếm {w * h:.2f} diện tích ảnh")
    return issues
