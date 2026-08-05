# Báo cáo cá nhân — Day 9: Multi-Agent A2A

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
|---|---|
| Họ và tên | Nguyễn Hoàng Vĩnh Phong |
| MSSV | 2A202601265 |
| 5 số cuối MSSV | 01265 |
| Khóa/Lớp | K3 / E402 |
| Vai trò chính | LLM Integration & Quality — OpenAI, trace, verifier và validation |
| Ngày hoàn thành | 2026-08-05 |

## 2. Phạm vi được phân công

| Module/deliverable | File phụ trách chính | Trách nhiệm |
|---|---|---|
| OpenAI client | `src/llm_client.py` | Structured Outputs, retry/error handling và agent identity checks |
| Audit logging | `src/trace_logger.py` | JSONL lifecycle/API/handoff events, metadata và secret redaction |
| Verifier Agent | `src/agents/verifier_agent.py` | Re-query CSV, kiểm tra entity, money, evidence, refund và status |
| Independent validator | `src/validation.py`, `validate_outputs.py` | Kiểm 50 output, trace, deliverable và ZIP contract |
| QA/runbook | `tests/test_pipeline.py`, `RUNBOOK.md` | Regression suite và quy trình chạy chính thức |

## 3. Kết quả công việc

- Model được khóa là `gpt-4o-mini`, đã được giảng viên xác nhận cho phép.
- Lượt chạy chính thức có 200/200 structured model calls và 0 API failure.
- Trace mới nhất có `run_id`, sequence, case, actor/target và usage/latency.
- Logger không ghi `.env`, authorization, API key, token hoặc prompt chứa secret.
- Verifier chặn invalid ID, financial mismatch, sai refund/status và missing policy evidence.
- Validator xác nhận 50 entry `output/EC_*`, 17 test pass và ZIP hợp lệ.

## 4. Quyết định kỹ thuật chính

Structured Outputs/Pydantic được dùng để model trả `AgentAudit` đúng schema. API
refusal, invalid response, identity mismatch hoặc exception làm run fail rõ ràng,
không âm thầm bỏ qua. Logger dùng lock để giữ sequence an toàn khi chạy nhiều worker.

Verifier là deterministic quality gate: model có thể cảnh báo nhưng không được ghi
đè dữ liệu nguồn. `--llm-mode off` chỉ dành cho test; trace bàn giao phải được tạo
bằng `--llm-mode all` để chứng minh bốn audit/case.

## 5. Cách xác minh phần việc

```powershell
python run_pipeline.py --llm-mode all --workers 4 --zip
python validate_outputs.py --zip submission.zip
python -m pytest -q
```

Sau khi chạy, kiểm tra metadata có `model=gpt-4o-mini`, `llm_mode=all`, 200 calls,
50 processed cases; trace không có `llm_call_failed` hoặc `verification_failed`.

## 6. Hiểu biết handoff

1. Mỗi specialist gọi OpenAI riêng và log structured audit.
2. Finding được handoff về Coordinator, sau đó sang Policy/Verifier.
3. Verifier kiểm tra output bằng dữ liệu nguồn, không tin riêng model response.
4. Pipeline chỉ đóng gói sau khi đủ tên file và validator pass.
5. Trace/metadata ở repo; ZIP nộp điểm chỉ chứa 50 output JSON.

## 7. Cam kết cá nhân

- [x] Tôi đã đọc và có thể giải thích các file được phân công.
- [x] Tôi đã tự chạy các lệnh xác minh.
- [x] Tôi có thể giải thích Structured Outputs, trace và quality gate.
- [x] Tôi xác nhận báo cáo chỉ nhận phần việc của mình.
- [x] Repo/báo cáo không chứa API key hoặc secret.

**Họ và tên:** Nguyễn Hoàng Vĩnh Phong  
**Ngày xác nhận:** 2026-08-05
