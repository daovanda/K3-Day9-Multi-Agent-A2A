from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from src.agents.coordinator import Coordinator
from src.config import INPUT_DIR, LOGGING_DIR, OUTPUT_DIR
from src.repository import DataRepository
from src.trace_logger import TraceLogger, install_exception_hook


EXPECTED_CASE_NAMES = {f"EC_{number:03d}.json" for number in range(1, 51)}


def clear_generated_outputs(output_dir: Path = OUTPUT_DIR) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    resolved_output = output_dir.resolve()
    if resolved_output.name.lower() != "output":
        raise ValueError(f"Refusing to clean unexpected output directory: {resolved_output}")
    for path in output_dir.glob("EC_*.json"):
        if path.is_file() and path.parent.resolve() == resolved_output:
            path.unlink()
    for path in output_dir.glob("*.tmp"):
        if path.is_file() and path.parent.resolve() == resolved_output:
            path.unlink()


def build_submission_zip(
    output_dir: Path = OUTPUT_DIR,
    destination: Path | None = None,
) -> Path:
    destination = destination or output_dir.parent / "submission.zip"
    files = sorted(output_dir.glob("EC_*.json"))
    names = {path.name for path in files}
    if names != EXPECTED_CASE_NAMES:
        missing = sorted(EXPECTED_CASE_NAMES - names)
        extra = sorted(names - EXPECTED_CASE_NAMES)
        raise ValueError(f"Cannot package output: missing={missing}, extra={extra}")
    with ZipFile(destination, "w", compression=ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, arcname=path.name)
    return destination


def run_pipeline(
    *,
    llm_mode: str = "all",
    limit: int | None = None,
    create_zip: bool = False,
    workers: int = 1,
) -> Counter:
    if llm_mode not in {"off", "policy", "all"}:
        raise ValueError("llm_mode must be one of: off, policy, all")
    if workers < 1 or workers > 8:
        raise ValueError("workers must be between 1 and 8")
    logger = TraceLogger(LOGGING_DIR, llm_mode=llm_mode)
    install_exception_hook(logger)
    processed = 0
    try:
        repository = DataRepository(input_dir=INPUT_DIR)
        cases = repository.load_cases()
        if len(cases) != 50:
            raise ValueError(f"Expected 50 cases, found {len(cases)}")
        if limit is not None:
            if limit < 1 or limit > 50:
                raise ValueError("limit must be between 1 and 50")
            cases = cases[:limit]
        clear_generated_outputs()
        coordinator = Coordinator(repository, logger, OUTPUT_DIR, llm_mode)
        counts: Counter = Counter()
        if workers == 1:
            outputs = (coordinator.process(case) for case in cases)
            for output in outputs:
                processed += 1
                counts[output.assessment.primary_issue] += 1
        else:
            logger.event(
                "parallel_execution_started",
                actor="coordinator",
                details={"workers": workers, "case_count": len(cases)},
            )
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="case-worker") as pool:
                for output in pool.map(coordinator.process, cases):
                    processed += 1
                    counts[output.assessment.primary_issue] += 1
        if create_zip:
            if len(cases) != 50:
                raise ValueError("Submission ZIP can only be created for a complete 50-case run")
            destination = build_submission_zip()
            logger.event(
                "submission_packaged",
                actor="coordinator",
                target="filesystem",
                details={"path": destination.name, "file_count": 50},
            )
        logger.finish(processed=processed, failed=0, issue_counts=dict(sorted(counts.items())))
        return counts
    except Exception as exc:
        logger.fail(exc, processed=processed)
        raise
