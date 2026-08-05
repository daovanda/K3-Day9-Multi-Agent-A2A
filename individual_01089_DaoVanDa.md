# Báo cáo cá nhân — Day 9: Multi-Agent A2A

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
|---|---|
| Họ và tên | Đào Văn Đà |
| 5 số cuối MSSV | 01089 |
| Khóa/Lớp | K3 / E402 |
| Vai trò chính | Trưởng nhóm tích hợp — Coordinator, Policy và đóng gói |
| Ngày hoàn thành | 2026-08-05 |

## 2. Phạm vi được phân công

| Module/deliverable | File phụ trách chính | Trách nhiệm |
|---|---|---|
| Điều phối A2A | `src/agents/coordinator.py` | Phân công specialist, nhận typed handoff, tổng hợp `CaseOutput` |
| Policy engine | `src/agents/policy_agent.py` | Áp dụng 6 rule theo đúng thứ tự `EC_POLICY_V1` |
| Cấu hình | `src/config.py` | Model, tolerance, confidence và đường dẫn dùng chung |
| Pipeline/CLI | `src/pipeline.py`, `run_pipeline.py` | Chạy 50 case, concurrency, tạo ZIP `output/EC_*` |
| Tích hợp cuối | `architecture.md`, `submission.zip` | Ghép module, audit artifact và bàn giao |

Không nhận ownership chính của repository/domain data, payment calculation hay
OpenAI logging/validator; các phần đó do ba thành viên còn lại phụ trách và handoff
qua typed contracts.

## 3. Kết quả công việc

- Coordinator tạo đúng chuỗi Order/Seller → Payment → Delivery → Policy → Verifier.
- Policy priority xử lý canceled, unavailable trước các nhánh delivery/payment.
- Output được ghi atomic và chỉ đóng gói khi đủ 50 file.
- ZIP có đúng `output/EC_001.json` đến `output/EC_050.json`.
- Bản cuối đạt **100/100** và được tái tạo bằng lượt chạy `gpt-4o-mini` chính thức.

## 4. Quyết định kỹ thuật chính

LLM tham gia audit typed finding nhưng không được tự sửa số tiền, timestamp hoặc ID.
Coordinator chỉ tổng hợp dữ liệu đã qua domain agent; Policy Agent áp dụng rule có
thứ tự; Verifier là quality gate trước khi writer tạo JSON. Thiết kế này giữ được
A2A handoff, trace thật và tính tái lập của nghiệp vụ tài chính.

`confidence=1.0` được dùng cho bộ chính thức vì chỉ case khớp đầy đủ policy và vượt
mọi verification gate mới được phát hành output; đây là system assurance score,
không được trình bày như raw confidence do LLM tự sinh.

## 5. Cách xác minh phần việc

```powershell
python run_pipeline.py --llm-mode all --workers 4 --zip
python validate_outputs.py --zip submission.zip
python -m pytest -q
```

Kết quả chung: 50 case, 200/200 model calls, 0 API failure, 17 test pass và ZIP
hợp lệ. Đà chịu trách nhiệm xác nhận lần chạy tích hợp cuối, không thay cho việc
từng thành viên tự kiểm tra module của mình.

## 6. Hiểu biết end-to-end

1. CLI khởi tạo repository/logger và Coordinator.
2. Coordinator giao cùng case cho các specialist theo dependency.
3. Typed findings được Policy Agent ánh xạ sang issue/refund/action.
4. Verifier kiểm tra lại dữ liệu nguồn và contract.
5. Coordinator ghi JSON; Pipeline kiểm đủ 50 tên rồi tạo ZIP.

## 7. Cam kết cá nhân

- [x] Tôi đã đọc và có thể giải thích các file được phân công.
- [x] Tôi đã tự chạy lệnh xác minh trong báo cáo.
- [x] Tôi có thể giải thích policy priority và luồng handoff.
- [x] Tôi xác nhận báo cáo chỉ nhận phần việc của mình.
- [x] Repo/báo cáo không chứa API key hoặc secret.

**Họ và tên:** Đào Văn Đà  
**Ngày xác nhận:** 2026-08-05
