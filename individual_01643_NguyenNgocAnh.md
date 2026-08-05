# Báo cáo cá nhân — Day 9: Multi-Agent A2A

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
|---|---|
| Họ và tên | Nguyễn Ngọc Ánh |
| MSSV | 2A202601643 |
| 5 số cuối MSSV | 01643 |
| Khóa/Lớp | K3 / E402 |
| Vai trò chính | Payment & Finance — đối soát thanh toán và quyết định tài chính |
| Ngày hoàn thành | 2026-08-05 |

## 2. Phạm vi được phân công

| Module/deliverable | File phụ trách chính | Trách nhiệm |
|---|---|---|
| Payment Agent | `src/agents/payment_agent.py` | Tổng payment rows, expected total, difference và reconciliation |
| Financial contracts | Phần `PaymentFact`, `PaymentFinding`, `FinancialResolution` trong `src/schemas.py` | Kiểu dữ liệu tiền và output tài chính |
| Policy tài chính | Phối hợp phần refund trong `src/agents/policy_agent.py` | Full payment, freight refund hoặc zero refund |
| Financial validation | Phần money/refund trong `src/validation.py` | Tính độc lập từ CSV và so với output |
| Payment tests | Phần split/tolerance/financial trong `tests/test_edge_cases.py` | Case nhiều row, unavailable và zero totals |

## 3. Kết quả công việc

- `payment_value` được cộng theo từng row, không nhân `payment_installments`.
- Reconciliation dùng `abs(payment - item - freight) <= 0.10 BRL`.
- Hai hay nhiều payment row được xem là split dù cùng payment type.
- Canceled/unavailable đã thanh toán hoàn toàn bộ payment.
- Late seller/logistics hoàn tổng freight; valid split/unsupported claim hoàn 0.
- Order unavailable không có item giữ item/freight bằng `0.0` nhưng vẫn hoàn payment.

## 4. Quyết định kỹ thuật chính

Mọi phép tính sử dụng `Decimal` và chỉ quantize `0.01` sau khi cộng row. Điều này
tránh sai số float tại ngưỡng 0.10 BRL. Payment Agent chỉ tạo finding tài chính;
Policy Agent quyết định refund theo issue priority và Verifier tính lại độc lập.

Khi chạy `--llm-mode all`, `gpt-4o-mini` audit payment finding bằng source context.
Model không được thay số tiền có thể kiểm chứng từ CSV và không được tự tạo payment
row hoặc transaction ID không tồn tại.

## 5. Cách xác minh phần việc

```powershell
python -m pytest -q tests/test_edge_cases.py
python validate_outputs.py --zip submission.zip
python run_pipeline.py --llm-mode all --limit 6
```

Các invariant cần tự kiểm tra: tổng item/freight/payment đúng hai chữ số, tolerance
inclusive, recommended refund khớp issue và `case_status` khớp refund.

## 6. Hiểu biết handoff

1. Payment Agent nhận item/freight total từ `OrderSellerFinding`.
2. Agent đọc payment rows và tạo `PaymentFinding`.
3. Coordinator handoff finding sang Policy Agent cùng delivery/order finding.
4. Policy chọn refund/action theo rule priority.
5. Verifier đọc lại payment CSV và chặn mọi sai lệch trước writer.

## 7. Cam kết cá nhân

- [x] Tôi đã đọc và có thể giải thích các file được phân công.
- [x] Tôi đã tự chạy các lệnh xác minh.
- [x] Tôi có thể giải thích payment row, installment và tolerance 0.10.
- [x] Tôi xác nhận báo cáo chỉ nhận phần việc của mình.
- [x] Repo/báo cáo không chứa API key hoặc secret.

**Họ và tên:** Nguyễn Ngọc Ánh  
**Ngày xác nhận:** 2026-08-05
