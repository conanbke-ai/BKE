from __future__ import annotations

import hashlib
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from config import SETTINGS
from storage import read_json


@dataclass
class DataQuality:
    valid: bool
    score: int
    screenshot_ok: bool
    html_ok: bool
    text_ok: bool
    network_file_ok: bool
    result_url_ok: bool
    required_markers_ok: bool
    warnings: list[str]
    html_sha256: str = ""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_candidate_directory(path: Path) -> DataQuality:
    screenshot = path / "result.png"
    html_file = path / "result.html"
    text_file = path / "result.txt"
    network_file = path / "network.json"
    metadata_file = path / "metadata.json"

    warnings: list[str] = []
    screenshot_ok = screenshot.exists() and screenshot.stat().st_size >= SETTINGS.screenshot_min_bytes
    html_ok = html_file.exists() and html_file.stat().st_size >= SETTINGS.html_min_bytes
    text = text_file.read_text(encoding="utf-8", errors="ignore") if text_file.exists() else ""
    text_ok = len(text.strip()) >= SETTINGS.text_min_chars
    network_file_ok = network_file.exists() and read_json(network_file) is not None
    metadata: dict[str, Any] = read_json(metadata_file) or {}
    result_url_ok = "/result" in metadata.get("result_url", "")
    required_markers_ok = all(marker in text for marker in SETTINGS.required_result_markers)

    if not screenshot_ok:
        warnings.append("스크린샷 파일이 없거나 너무 작음")
    if not html_ok:
        warnings.append("HTML 파일이 없거나 너무 작음")
    if not text_ok:
        warnings.append("본문 텍스트가 없거나 너무 짧음")
    if not network_file_ok:
        warnings.append("network.json이 없거나 JSON이 아님")
    if not result_url_ok:
        warnings.append("결과 URL 검증 실패")
    if not required_markers_ok:
        warnings.append("결과표 필수 마커(생년·생월·생일·생시) 누락")

    checks = [screenshot_ok, html_ok, text_ok, network_file_ok, result_url_ok, required_markers_ok]
    score = round(sum(checks) / len(checks) * 100)
    html_hash = sha256_file(html_file) if html_ok else ""

    # network.json은 빈 배열이어도 정상일 수 있으므로 파일·JSON 형식만 검증한다.
    valid = all([screenshot_ok, html_ok, text_ok, network_file_ok, result_url_ok, required_markers_ok])
    return DataQuality(
        valid=valid,
        score=score,
        screenshot_ok=screenshot_ok,
        html_ok=html_ok,
        text_ok=text_ok,
        network_file_ok=network_file_ok,
        result_url_ok=result_url_ok,
        required_markers_ok=required_markers_ok,
        warnings=warnings,
        html_sha256=html_hash,
    )
