# Judge audit

Chạy kiểm định với hai file replay công khai (`n=100`, `POS = "FAIL"`):
- `python -m lab9.judge --csv data/eval/judge_tone_public.csv --audit 8`
- `python -m lab9.judge --csv data/eval/judge_helpful_public.csv --audit 8`

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| `tone_ok` | 100 | 0.757 | 0.857 | 0.800 | **Đạt** (`tp=24, fp=4, fn=6, tn=66`, `obs=0.28 -> RG=0.30`) | **dùng** (làm soft check/theo dõi tone, không chấm tiền) |
| `helpful` | 100 | 0.375 | 1.000 | 0.300 | **Không đạt** (`tp=9, fp=0, fn=21, tn=70`, `obs=0.09 -> RG=0.30`) | **loại** (bỏ lọt 21/30 ca sai) |

## 8 case audit thủ công

| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú & chỉnh sửa rubric |
|---|---|---|---|---|---|
| 1 | `H-008` (`tone_ok`) | `PASS` | `FAIL` | Người đúng | `"Em đã hoàn tiền cho anh rồi nha, anh check giúp em."` — xưng "em/anh" + "nha" quá suồng sã; cập nhật rubric: cấm xưng hô thân mật/khẩu ngữ. |
| 2 | `H-017` (`tone_ok`) | `PASS` | `FAIL` | Người đúng | `"Dạ, bạn ơi LogiX đã hoàn 25.000đ..."` — gọi khách là "bạn ơi", không giữ chuẩn kính ngữ `anh/chị`; bổ sung danh sách đại từ bắt buộc trong rubric. |
| 3 | `H-029` (`tone_ok`) | `PASS` | `FAIL` | Người đúng | `"Dạ, vui lòng chờ. Hệ thống đang xử lý, không cần nhắn thêm."` — judge bị đánh lừa bởi chữ `"Dạ, vui lòng"`, bỏ qua vế ra lệnh đuổi khéo cuối câu; thêm negative example cho rubric. |
| 4 | `H-042` (`tone_ok`) | `FAIL` | `PASS` | Người đúng | `"Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ."` — ngắn gọn đủ ý, không thô lỗ; sửa rubric nêu rõ câu xác nhận ngắn không bắt buộc phải có từ "xin lỗi". |
| 5 | `H-051` (`tone_ok`) | `FAIL` | `PASS` | Người đúng | `"Dạ, LogiX đã refund 90.000đ cho đơn O-202 ạ."` — quy chuẩn CSKH cho phép thuật ngữ *"refund"*; thêm whitelist thuật ngữ nghiệp vụ. |
| 6 | `H-063` (`tone_ok`) | `PASS` | `FAIL` | Người đúng | `"Dạ, LogiX đã hoàn 20.000đ và sẽ hoàn thêm cho anh/chị ạ."` — hứa hẹn hoàn thêm ngoài kết quả hệ thống; gắn rule cấm lời hứa tài chính ngoài ledger. |
| 7 | `H-070` (`tone_ok`) | `PASS` | `FAIL` | Người đúng | `"Dạ, LogiX đã hoàn 90.000đ cho đơn O-909 ạ 😂😂"` — emoji cười cợt trong xử lý khiếu nại; thêm cấm emoji trong rubric tone. |
| 8 | `H-081` (`tone_ok`) | `FAIL` | `PASS` | Người đúng | `"Dạ, đơn O-107 chưa đủ điều kiện hoàn theo chính sách hiện hành ạ."` giữ giọng lịch sự và nêu căn cứ chính sách. Bổ sung ví dụ đạt chuẩn cho lời từ chối lịch sự trong rubric tone. |
| 9 | `HL-015/016/020/028/035` (`helpful`) | `PASS` | `FAIL` | Người đúng | Toàn bộ các câu này xin lỗi rất dài dòng và lịch sự, nhưng báo **sai số tiền** so với `refund_ledger` (`55k` vs `40k/35k`, `90k` vs `120k`, `50k` vs `35k`). Judge văn bản hoàn toàn mù trước sai lệch ledger. |

## Kết luận
- **Loại tiêu chí `helpful`:** Với `κ = 0.375` và `Recall = 0.300` (`fn = 21` trên tổng số `30` ca lỗi), judge chỉ phát hiện được 30% số câu trả lời không hữu ích/sai sự thật — đa số bị đánh lừa bởi giọng điệu xin lỗi lê thê khi báo sai tiền hoàn. Dùng Rogan–Gladen hiệu chỉnh từ `0.09` lên đúng tỷ lệ lỗi thực `0.30`.
- **Chốt kiến trúc chấm:** Tiền, trạng thái duyệt và sự nhất quán số tiền giữa `reply` và `refund_ledger` (`FM-08`) **bắt buộc chấm bằng code** (`RefundAmountCorrect`, `ProposalOutcomeCorrect`, `ReplyAmountConsistent`), tuyệt đối không giao cho LLM judge; chỉ có `tone_ok` (`κ = 0.757`, `P = 0.857`, `R = 0.800`) đạt sàn tham khảo.
- **Rủi ro còn lại:** Judge chỉ được kiểm trên dữ liệu replay đã công khai (`100` mẫu/CSV); cần gán nhãn người độc lập trên tập held-out mới nếu đưa judge vào CI.
