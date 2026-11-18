# Trace case: từ trace tới quyết định sai đầu tiên

Lệnh chạy đối chứng:
- `python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11`
- `python -m lab9.trace_case --shape fixed --claim C-002 --seed 11`
- Đối chứng baseline `swarm` lỗi dao động seed: `python -m lab9.trace_case --shape swarm --claim C-002 --seed 55`

## Case 1: `seeded_regression C-002@11` (trích report `E-seeded_regression-20261118-9dc2`)

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11`, run ID `E-seeded_regression-20261118-9dc2` |
| Triệu chứng | `pass_rate = False`, `db_fact_kept = False`, `refund_amount_correct = False`: ledger ghi `refund_vnd = 20000`, `refund_count = 1`, `status = resolved`, và event #6 `reply` nói *"Dạ, LogiX đã hoàn 20.000đ cho đơn O-202."* — trong khi nhãn kỳ vọng là `denied`, `refund_vnd = 0`. |
| Bước sai đầu tiên | Event **#3** `model_override`: `{"delay_days": 5}` — agent tự ý ghi đè số ngày trễ `delay_days=2` từ DB bằng con số `5 ngày` trích từ nội dung ticket khách hàng. |
| Vì sao là bước *đầu tiên* | Event #1 (`handoff`) chuyển gói allowlist `REQ-C-002` đúng chuẩn không lộ secret; event #2 (`investigator`) truy vấn `lookup_order` trả về dữ liệu thật chính xác (`order_id: "O-202"`, `delay_days: 2`). Sai lệch chỉ phát sinh từ event #3 `model_override` dẫn dây chuyền tới `quote = 20.000đ` ở event #4 và ghi nhầm tiền vào ledger. |
| Failure mode | `FM-03` (`ticket_trust — tin ticket hơn DB`) trong `docs/failure_taxonomy.md`. |
| Đối chứng | Trên `fixed C-002@11`: sau event #2 (`lookup_order` đọc `delay_days=2`), `fixed` **không** sinh `model_override`, đi thẳng event #3 `quote` (`amount_vnd=0`, `reason="no_entitlement"`) và event #4 `reply` từ chối đúng (`status=denied`, `ledger=0`). |
| Regression test | `test_trace_case_c002_ticket_trust_regression_vs_fixed` trong `src/tests/test_lab9_regression.py`: kiểm chứng trên `seeded_regression` và `swarm@55` cùng hai grader `DbFactKept` (`False`) + `RefundAmountCorrect` (`False`), đồng thời pass hoàn toàn trên `fixed`. |
| Chưa chắc chắn | Trace public chưa bao phủ trường hợp agent tin ticket *âm thầm* không ghi event `model_override` (`quiet_override`) — trường hợp đó `DbFactKept` bỏ sót nhưng `RefundAmountCorrect` và `TrialPass` vẫn bắt ở tầng outcome. |

## Quy tắc
- Đọc **ledger trước reply**: trong case `C-002@11` (và `C-007@11`), reply hoàn toàn lịch sự và trôi chảy dù đã hoàn tiền sai hoặc hoàn tiền khi bị từ chối.
- Đã gắn regression test chạy được trong `src/tests/test_lab9_regression.py`.
