# Báo cáo cá nhân — Day 9: Multi-Agent A2A

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
|---|---|
| Họ và tên | Trương Quốc Trường |
| MSSV | 2A202601195 |
| 5 số cuối MSSV | 01195 |
| Khóa/Lớp | K3 / E402 |
| Vai trò chính | Data & Delivery — Repository, Order/Seller và Delivery Agent |
| Ngày hoàn thành | 2026-08-05 |

## 2. Phạm vi được phân công

| Module/deliverable | File phụ trách chính | Trách nhiệm |
|---|---|---|
| Data access | `src/repository.py` | Load/index CSV read-only, chuẩn hóa money và resolve evidence ID |
| Order/Seller Agent | `src/agents/order_seller_agent.py` | Order status, item/seller, shipping limit, item/freight total |
| Delivery Agent | `src/agents/delivery_agent.py` | So actual/estimate và carrier/shipping limit |
| Typed data contract | Phần `ItemFact`, `OrderSellerFinding`, `DeliveryFinding` trong `src/schemas.py` | Handoff có schema, không truyền dữ liệu tự do |
| Edge-case tests | Phần timestamp/multi-seller trong `tests/test_edge_cases.py` | Khóa các case biên delivery và seller responsibility |

## 3. Kết quả công việc

- Repository join đúng `order_id`, sắp item theo `order_item_id` và seller duy nhất.
- Order/Seller Agent tính item/freight bằng `Decimal`, không nhân sai quantity.
- Delivery Agent chỉ kết luận late khi đủ actual và estimated timestamp.
- Seller late dùng điều kiện `carrier_date > shipping_limit_date` của từng item.
- Các case cùng ngày nhưng trễ theo giờ (`EC_033`, `EC_034`, `EC_044`) được xử lý đúng.
- Case nhiều seller chỉ quy trách nhiệm seller có item vi phạm.

## 4. Quyết định kỹ thuật chính

Timestamp được so theo giá trị CSV, không đổi timezone. Missing delivery/handoff
không được mặc định là đúng hạn. Repository không đưa product/review/geolocation
vào prompt vì sáu policy không cần các bảng này. Evidence chỉ được chấp nhận khi
resolve được khóa order/item/payment/seller trong nguồn.

Order/Seller và Delivery Agent thực hiện structured audit bằng `gpt-4o-mini` khi
`--llm-mode all`, sau đó handoff finding cho Coordinator; hai agent không tự quyết
refund hoặc resolution action.

## 5. Cách xác minh phần việc

```powershell
python -m pytest -q tests/test_edge_cases.py
python validate_outputs.py
python run_pipeline.py --llm-mode all --limit 3
```

Các invariant cần tự kiểm tra: timestamp thiếu không thành on-time, handoff sau hạn
phải là seller signal, item/seller ID tồn tại, item và freight total khớp CSV.

## 6. Hiểu biết handoff

1. Repository trả order/items dưới typed facts.
2. Order/Seller Agent tạo `OrderSellerFinding`.
3. Delivery Agent nhận finding này, không tự đọc/đoán tracking ngoài dữ liệu.
4. Coordinator chuyển cả hai finding sang Policy Agent.
5. Verifier re-query CSV để kiểm chứng độc lập trước output.

## 7. Cam kết cá nhân

- [x] Tôi đã đọc và có thể giải thích các file được phân công.
- [x] Tôi đã tự chạy các lệnh xác minh.
- [x] Tôi có thể giải thích seller và logistics khác nhau thế nào.
- [x] Tôi xác nhận báo cáo chỉ nhận phần việc của mình.
- [x] Repo/báo cáo không chứa API key hoặc secret.

**Họ và tên:** Trương Quốc Trường  
**Ngày xác nhận:** 2026-08-05
