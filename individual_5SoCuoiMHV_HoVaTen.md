# Báo cáo cá nhân — Day 9: Multi-Agent A2A

> Bản nháp kỹ thuật đã điền theo implementation hiện tại. Người nộp phải thay
> tên file, Họ tên, MSSV, lớp và chỉ giữ những phần việc mình thực sự sở hữu.

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
|---|---|
| Họ và tên | [CẦN ĐIỀN] |
| MSSV | [CẦN ĐIỀN] |
| Khóa/Lớp | K3 / [CẦN ĐIỀN] |
| Vai trò chính | Multi-agent orchestration, verification và audit logging |
| Ngày hoàn thành | 2026-08-05 |

## 2. Vai trò và phạm vi công việc

| Module/deliverable | File/hàm phụ trách | Input | Output | Trạng thái |
|---|---|---|---|---|
| Orchestration | `src/agents/coordinator.py` | Case + specialist findings | Verified `CaseOutput` | Hoàn thành |
| Policy/data agents | `src/agents/*.py` | Indexed CSV facts | Typed handoffs | Hoàn thành |
| Verification | `src/agents/verifier_agent.py`, `src/validation.py` | Output + source CSV | Pass/fail + lỗi cụ thể | Hoàn thành |
| Audit logging | `src/trace_logger.py` | Agent/API/runtime events | JSONL trace + metadata | Hoàn thành |
| Execution/package | `run_pipeline.py`, `src/pipeline.py` | 50 inputs | 50 JSON + ZIP | Hoàn thành |

Việc tích hợp bổ sung: xây smoke test OpenAI Structured Outputs, kiểm tra log không
chứa key, đối chiếu ZIP root và viết architecture/runbook.

## 3. Kết quả theo vai trò

| Nhiệm vụ | Artifact | Kết quả | Cách xác minh |
|---|---|---|---|
| Xử lý 50 case | `output/EC_001.json`–`EC_050.json` | Đủ 6 policy branch | `python validate_outputs.py` |
| Multi-agent trace thật | `logging/trace.jsonl` | 200 model calls, 200 handoff, 50 verified case | Group event type trong JSONL |
| Đóng gói | `submission.zip` | 50 JSON tại ZIP root | `python validate_outputs.py --zip submission.zip` |
| Regression tests | `tests/test_pipeline.py` | 6 test pass | `python -m pytest -q` |

Phân bố kết quả: canceled 8, unavailable 8, late seller 8, late logistics 8,
valid split 9 và unsupported late claim 9.

## 4. Giải thích kỹ thuật

### Vấn đề cần giải quyết

Một claim không đủ để kết luận. Pipeline phải join order–item–payment–seller,
phân biệt seller/logistics, đối soát tiền và tạo evidence có thể resolve trực tiếp.

### Cách triển khai

`DataRepository` index CSV read-only. Coordinator giao việc cho Order/Seller,
Payment và Delivery Agent. Ba typed finding được Policy Agent xử lý theo priority
`EC_POLICY_V1`. Verifier đọc lại CSV, tính lại tiền bằng `Decimal`, kiểm tra entity,
evidence, refund, status và schema trước atomic write. Mỗi agent có OpenAI
Structured Output call riêng khi chạy `--llm-mode all`; model không được phép thay
thế deterministic financial/policy logic.

### Input, output và contract

| Thành phần | Mô tả |
|---|---|
| Input | `CaseInput`, `claimed_order_id`, CSV rows |
| Output | `CaseOutput` đúng schema README |
| Module phụ thuộc | repository, specialist agents, Pydantic schemas |
| Module dùng output | verifier, writer, submission packager |
| Lỗi xử lý | Missing order, unmatched policy, API/refusal, invalid evidence/schema |

### Cách xác minh

```powershell
python -m pytest -q
python validate_outputs.py --zip submission.zip
```

- Kết quả mong đợi: 6 test pass, 50 file hợp lệ, ZIP hợp lệ.
- Kết quả thực tế: 6 test pass; validator trả `file_count: 50` và đúng phân bố.
- Artifact/log: `logging/trace.jsonl`, `logging/metadata.json`.

## 5. Quyết định kỹ thuật quan trọng

- Bối cảnh: LLM có thể sai số học, timestamp hoặc tạo evidence không tồn tại.
- Phương án cân nhắc: để model sinh output cuối; hoặc model tham gia agent handoff
  nhưng code deterministic là authority.
- Phương án chọn: typed multi-agent handoff + deterministic policy/verifier.
- Lý do: tái lập, giảm hallucination, vẫn chứng minh orchestration và model calls.
- Bằng chứng: validator độc lập suy lại issue/totals từ CSV; 50/50 case pass.

## 6. Một lỗi đã xử lý

- Triệu chứng: audit model tự mâu thuẫn, ví dụ tổng 119.90 + 12.04 = 131.94 nhưng
  vẫn đánh dấu không reconcile.
- Tái hiện: chạy `python run_pipeline.py --llm-mode all --limit 6` và inspect trace.
- Root cause: boolean “agree/disagree” yêu cầu model đánh giá lại phép tính đã được
  code xác minh, tạo thêm nguồn sai không cần thiết.
- Cách xử lý: đưa source context vào domain review, đổi model response thành typed
  handoff acknowledgement; giữ Verifier/validator làm correctness authority.
- Xác minh: full run có 200/200 structured calls, 0 API failure; 50 output pass.
- Bài học: không giao phép tính/evidence quyết định cho probabilistic component khi
  có thể kiểm chứng hoàn toàn bằng dữ liệu nguồn.

## 7. Hiểu biết luồng end-to-end

1. Coordinator đọc case và dùng `claimed_order_id` để lấy order/items/payments.
2. Specialist agents phân tích riêng domain và handoff typed finding.
3. Policy Agent áp dụng sáu rule theo priority, không tin claim hơn dữ liệu CSV.
4. Verifier re-query nguồn, kiểm tra totals, refund, IDs, evidence và schema.
5. Coordinator atomic-write JSON; logger tự ghi lifecycle, API usage và handoff.
6. Validator kiểm tra toàn bộ 50 file; packager chỉ tạo ZIP khi tên file đầy đủ.

Quality gate thành công dựa trên: 50 JSON schema-valid, issue/totals/refund suy lại
khớp CSV, evidence resolve được, 50 verification pass và ZIP đúng 50 entry.

## 8. Cam kết

- [ ] Tôi đã cá nhân hóa đúng phần việc thực sự của mình.
- [ ] Tôi có thể giải thích luồng end-to-end và policy priority.
- [ ] Tôi đã tự chạy các lệnh xác minh ghi trong báo cáo.
- [ ] Báo cáo/repo không chứa `.env`, API key, token hoặc secret.
- [ ] Tôi đã đổi `5SoCuoiMHV_HoVaTen` thành MSSV và họ tên thật.

**Họ và tên:** [CẦN ĐIỀN]  
**Ngày xác nhận:** [CẦN ĐIỀN]
