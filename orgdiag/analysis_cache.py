from __future__ import annotations

import hashlib
import json
from pathlib import Path


def analysis_artifact_dir(cache_root: Path, image_stem: str) -> Path:
    return cache_root / image_stem


def pass1_cache_path(cache_root: Path, image_stem: str) -> Path:
    return analysis_artifact_dir(cache_root, image_stem) / "pass1.txt"


def pass2_cache_path(cache_root: Path, image_stem: str) -> Path:
    return analysis_artifact_dir(cache_root, image_stem) / "pass2.txt"


def analysis_meta_path(cache_root: Path, image_stem: str) -> Path:
    return analysis_artifact_dir(cache_root, image_stem) / "analysis_meta.json"


def analysis_input_fingerprint(
    *,
    org_type: str,
    pain: str,
    hierarchy_text: str,
    simple_structure: str,
) -> str:
    payload = json.dumps(
        {
            "org_type": org_type.strip(),
            "pain": pain.strip(),
            "hierarchy": hierarchy_text.strip(),
            "simple_structure": simple_structure.strip(),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def save_analysis_meta(
    cache_root: Path,
    image_stem: str,
    *,
    fingerprint: str,
) -> None:
    path = analysis_meta_path(cache_root, image_stem)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"fingerprint": fingerprint}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def save_cached_pass1(cache_root: Path, image_stem: str, text: str) -> Path:
    path = pass1_cache_path(cache_root, image_stem)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip(), encoding="utf-8")
    return path


def save_cached_pass2(cache_root: Path, image_stem: str, text: str) -> Path:
    path = pass2_cache_path(cache_root, image_stem)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip(), encoding="utf-8")
    return path
