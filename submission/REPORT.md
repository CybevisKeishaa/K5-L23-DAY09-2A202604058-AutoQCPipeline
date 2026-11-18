# Báo cáo Day 09 — Trần Nguyễn Phi Long, 2A202604058

## 1. Kết luận trước
Pipeline kết luận **HOLD** (mã thoát 10). Vào **224** ảnh, cửa vào loại **22**, còn **202** ảnh. Bản xuất `clean_v1` có 202 ảnh, manifest ghi `decision=Hold`, tức là bản nháp và **chưa phát hành**.
Lý do: đã hết lỗi bắt buộc (0), nhưng **38/202 ảnh (18,8%)** còn cảnh báo mà người chưa duyệt, vượt ngưỡng 10%. Hàng đợi có 125 ảnh, ngân sách chỉ 80 ảnh, nên 45 ảnh chưa ai xem.

## 2. Lỗi và phân việc
Lấy từ `02_error_list_v1` (202 ảnh sau cửa vào; mã cửa vào lấy từ `01_intake`, trên 224 ảnh).

| Mã lỗi | Số dòng / ảnh | Ai sửa | Vì sao |
|---|---:|---|---|
| DUP_IMAGE_EXACT | 8 ảnh / 224 | máy (loại ở cửa vào) | trùng từng byte, không có rủi ro |
| DUP_IMAGE_NEAR | 4 ảnh / 224 | máy (loại) | phash ≤ 10; đã mở xem cả 4 cặp, đều đúng là trùng |
| LEAK_TEST | 5 ảnh / 224 | máy (loại) | trùng ảnh trong test/gold_val, giữ lại sẽ làm rò rỉ khi đo |
| BAD_SIZE / CORRUPT_IMAGE | 3 / 2 ảnh | máy (loại) | không dùng được để train |
| BAD_CLASS_NAME | 2 dòng / data.yaml | máy (`rename_classes`) | `Person`, `Bus` → ghi lại `names` theo cấu hình |
| BAD_CLASS_ID | 6 dòng / 6 ảnh | máy (`drop_line`) | id 93, -1, 7, 4 không có trong 0..3; máy không đoán được lớp đúng |
| BAD_FORMAT | 3 dòng / 3 ảnh | máy (`drop_line`) | nan hoặc thiếu cột |
| BOX_ZERO | 4 dòng / 4 ảnh | máy (`drop_line`) | w hoặc h = 0 |
| DUP_BOX | 7 dòng / 7 ảnh | máy (`drop_line`) | cùng lớp, IoU > 0,9 với dòng phía trên |
| BOX_OUT_OF_IMAGE | 8 dòng / 8 ảnh | máy (`clip_box`) | tràn 0,023–0,06; cắt về [0,1], giữ lớp |
| MISSING_LABEL_FILE | 6 ảnh | **người** (`needs_label`) | máy không được bịa nhãn |
| POSSIBLE_MISSING | 53 / 52 ảnh | **người** | model lớn thấy vật mà nhãn không có |
| POSSIBLE_FALSE_POS | 29 / 27 ảnh | **người** | box nhãn không khớp dự đoán nào |
| POSSIBLE_LOOSE_BOX | 28 / 24 ảnh | **người** | đúng vật, IoU < 0,5 |
| POSSIBLE_WRONG_CLASS | 18 / 18 ảnh | **người** | model nói lớp khác, IoU ≥ 0,5 |
| EMPTY_LABEL / BOX_TINY / BOX_HUGE / CLASS_RARE | 12 / 6 / 3 / 4 | **người** | quy tắc dự án, chỉ cảnh báo |

Máy ghi **35 thay đổi** trong `03_fixes.csv`: 20 `drop_line`, 8 `clip_box`, 6 `needs_label`, 1 `rename_classes`. Sau khi máy sửa (`04_error_list_v2`), chỉ còn 6 lỗi bắt buộc, đều là MISSING_LABEL_FILE.

**Hàng đợi** (`05_review_queue.csv`, 125 ảnh): điểm của mỗi ảnh = tổng trọng số các mã × (1 + conf của model). Đứng đầu là `img_0020` (11,5), vì ảnh này vừa bị máy xoá một dòng, vừa có MISSING và WRONG_CLASS. Tiếp theo là 6 ảnh `NEEDS_LABEL` (10,0): đây là lỗi bắt buộc chỉ người sửa được, nên được ưu tiên. Ngân sách 80 ảnh xử lý được 66/123 cảnh báo ngữ nghĩa (POSSIBLE_*: 123 ở v2 → 57 ở v3). Còn lại 45 ảnh chưa duyệt, trong đó 38 ảnh vẫn có cảnh báo.

## 3. Calibration (2 ngưỡng)
| Tham số | Khởi đầu | Đã chọn | P / R trên calib (trước → sau) | Lý do (đánh đổi) |
|---|---|---|---|---|
| `duplicates.phash_dist` | 2 | **10** | NEAR: 1,00/0,50 → 1,00/0,67 (EXACT giữ 1,00/1,00) | Từ 4 đến 14, P/R trên calib như nhau. Trên raw, 10 bắt thêm `img_0186`≈`img_0061` (dist 10, đã mở xem: cùng cảnh, bị cắt/dịch). Không lấy 16 (xem bên dưới). |
| `second_opinion.conf` | 0,25 | **0,6** | MISSING 0,50/1,00 → 0,57/1,00; WRONG_CLASS 0,56/0,83 → 0,62/0,83; LOOSE_BOX 0,29/0,40 → 0,20/0,20 | Đây là giá trị cao nhất mà MISSING vẫn giữ recall 1,00. Thiếu nhãn hại khi train nhiều nhất, và cảnh báo chỉ chuyển người xem chứ không xoá gì, nên ưu tiên recall. Ở 0,7–0,8, MISSING tụt còn 0,88–0,75 (bỏ sót 1–2/8 ca). Đổi lại, LOOSE_BOX giảm recall. |

**Chỗ calibration đánh lừa:**
1. Trên calib, `phash_dist=16` có F1 NEAR cao nhất (0,91). Nhưng calib chỉ có 6 cặp trùng gần đúng, nên mỗi cặp đổi recall 0,17. Chạy trên raw với 16 thì LEAK_TEST nhảy từ 5 lên 11, và `img_0011` (tennis) bị coi là trùng với `img_0008` (trượt tuyết), dist 16. Tôi đã mở xem: hai ảnh khác hẳn nhau. Với 20, có 105 ảnh bị coi là rò rỉ test.
2. Với `conf=0,8`, pipeline ra **Release** (16/202 = 7,9%). Nhưng đó là do model cảnh báo ít đi, chứ nhãn không sạch hơn: trên calib, recall MISSING giảm từ 1,00 xuống 0,75. Tôi không chọn giá trị này chỉ để "đạt" Release.

## 4. Cửa chặn và điều pipeline KHÔNG bắt được
(a) **Gate chặn thật.** Chạy `python -m pipeline.run --budget 0 --work work/run_nb --reports work/rep_nb --export-dir work/exp_nb`: không có người duyệt nên 6 ảnh MISSING_LABEL_FILE vẫn còn. Kết quả: **REWORK — còn 6 lỗi bắt buộc** (112/202 ảnh còn cảnh báo), **mã thoát 20**, log in "KHÔNG xuất: còn lỗi bắt buộc", và thư mục `work/exp_nb/` **không được tạo**. Trong lần chạy thật, người gán đủ 6 ảnh này nên lỗi bắt buộc về 0, pipeline chỉ còn Hold.

(b) **Điểm mù** (bằng chứng từ calib, cấu hình đã chọn):
- **Box lỏng nhẹ:** POSSIBLE_LOOSE_BOX bắt được 1/5 ca (recall 0,20). Box lệch vừa phải vẫn có IoU ≥ 0,5 với dự đoán nên không bị cờ.
- **Trùng gần đúng biến đổi mạnh:** DUP_IMAGE_NEAR bỏ sót 2/6 cặp (recall 0,67). Nếu nới ngưỡng để bắt được, sẽ loại nhầm ảnh khác (mục 3).
- **Nhầm lớp mà model lớn cũng nhầm:** WRONG_CLASS sót 1/6. Model và nhãn sai giống nhau thì không có tín hiệu nào.
- POSSIBLE_FALSE_POS có precision chỉ 0,31 (11 báo nhầm / 16). Cảnh báo này tốn nhiều công người duyệt.
- Sửa máy có thể sinh cảnh báo mới: sau `clip_box`/`drop_line`, BOX_TINY tăng 6 → 7 dòng và EMPTY_LABEL tăng 12 → 15 ảnh (ảnh bị xoá hết dòng). Các ảnh này đều vào hàng đợi người.

## 5. Train: raw vs clean (tùy chọn, chấm riêng)
**Chưa chạy.** Phần này cần Colab GPU, chưa thực hiện trong buổi này nên chưa có số liệu để so sánh. Không đưa ra kết luận "clean tốt hơn raw".

## 6. Quyết định và ghi chú

**(a) Quyết định: Hold.** Để thành Release, cần người duyệt thêm ít nhất 18 trong 38 ảnh còn cảnh báo (≤ 20/202 < 10%), bắt đầu từ đầu phần còn lại của `05_review_queue.csv`, rồi chạy `--resume-after-review`. Không được hạ cảnh báo bằng cách tăng `conf`.

**(b) Quá trình triển khai và kiểm chứng:**
- **Triển khai:** Tự hoàn thiện 4 module dựa trên yêu cầu trong docstring của từng stub và file test tương ứng. Các ngưỡng được đọc từ `cfg`, không sửa `data/raw` và không viết cứng tên ảnh.
- **Kiểm tra:** Đọc lại từng hàm để kiểm soát các thao tác có thể xóa dữ liệu (chỉ `autofix` được phép xóa file trong `ds`); chạy `pytest` đạt 79/79 test; chạy calibration để đối chiếu P/R với đáp án và mở xem trực tiếp các cặp ảnh bị đánh dấu trùng.
- **Điều chỉnh:** Không chọn `phash_dist=16` dù có F1 cao nhất trên calibration, vì kiểm tra trên raw phát hiện ngưỡng này loại nhầm hai ảnh khác nhau. Chọn ngưỡng 10 để cân bằng giữa khả năng phát hiện trùng và rủi ro loại nhầm. Ngoài ra, nhận thấy `clip_box` có thể tạo box mới quá nhỏ (BOX_TINY tăng từ 6 lên 7); đây là cảnh báo để người duyệt xử lý, không phải lỗi chặn pipeline.