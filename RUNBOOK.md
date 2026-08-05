# Runbook

## Setup

```powershell
cd D:\All_Vin\day9\K3-Day9-Multi-Agent-A2A
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Tạo `.env` từ `.env.example` và đặt `OPENAI_API_KEY`. Không commit `.env`.
Model `gpt-4o-mini` đã được hardcode trong `src/config.py` theo yêu cầu đề.

## Test không gọi API

```powershell
python -m pytest -q
python run_pipeline.py --llm-mode off
python validate_outputs.py
```

## Smoke test OpenAI

Lệnh này xóa output cũ và chỉ tạo case đầu tiên, vì vậy phải chạy lại đủ 50 case
sau smoke test:

```powershell
python run_pipeline.py --llm-mode all --limit 1
```

## Chạy chính thức

```powershell
python run_pipeline.py --llm-mode all --workers 4 --zip
python validate_outputs.py --zip submission.zip
```

Giảm `--workers` nếu API tier gặp rate limit. Mỗi lần chạy tự động ghi đè trace và
metadata. `--llm-mode all` thực hiện 4 structured audit × 50 case.

## Artifacts

- `output/EC_001.json` … `output/EC_050.json`: kết quả chấm.
- `logging/trace.jsonl`: trace thật của lần chạy mới nhất.
- `logging/metadata.json`: provider/model/runtime/run summary.
- `submission.zip`: đúng 50 JSON ở ZIP root.
- `architecture.md`: design, quyền truy cập và handoff.

ZIP nộp bài chỉ là `submission.zip`; source, `.env`, trace và metadata không nằm
trong ZIP này. Source và audit artifacts vẫn phải commit vào repo nhóm.

## Checklist trước khi nộp

```powershell
python -m pytest -q
python validate_outputs.py --zip submission.zip
git status --short
```

Xác nhận report cá nhân đã đổi tên và điền bằng nội dung thực tế. Template mục 7
đang nhắc Crossref/vector index không thuộc lab này; hỏi giảng viên hoặc thay bằng
luồng dispute-resolution end-to-end, không bịa kết quả.
