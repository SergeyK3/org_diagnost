from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from openai import OpenAI

from orgdiag.config import RunConfig, default_contact, require_api_key
from orgdiag.image_input import resolve_image_input
from orgdiag.llm_diagnosis import (
    run_pass1_block_analysis,
    run_pass2_admin_analysis,
    run_step1_diagnosis,
)
from orgdiag.matrix import analyze_pain
from orgdiag.paths import CACHE_DIR, HTML_OUT_DIR, REPORTS_DIR, resolve_path
from orgdiag.prompts import load_all_prompts
from orgdiag.report_html import default_html_path, generate_html_report
from orgdiag.report_pdf import generate_pdf_report
from orgdiag.structure import (
    compare_simple_structures,
    map_departments_to_blocks,
    render_sideways_tree,
    simplify_structure_llm,
)
from orgdiag.vision import (
    extract_org_json_from_image,
    load_org_json_cache,
    save_org_json_cache,
)
from orgdiag.visualize import export_visuals


@dataclass
class DiagnosisResult:
    image: Path
    org_type: str
    pain: str
    org_json: dict = field(default_factory=dict)
    hierarchy_text: str = ""
    simple_structure: str = ""
    compare_text: str = ""
    pain_analysis_text: str = ""
    causes_text: str = ""
    actions_text: str = ""
    step1_diagnosis: str | None = None
    pass1_text: str = ""
    pass2_text: str = ""
    pdf_path: Path | None = None
    html_path: Path | None = None
    cache_path: Path | None = None
    visual_paths: dict[str, Path] = field(default_factory=dict)
    block_roles: dict = field(default_factory=dict)


def default_output_path(cfg: RunConfig) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    return REPORTS_DIR / f"org_structure_report_{cfg.image_stem}.pdf"


def default_html_output_path(cfg: RunConfig) -> Path:
    HTML_OUT_DIR.mkdir(parents=True, exist_ok=True)
    return default_html_path(HTML_OUT_DIR, cfg.display_org_name)


def default_cache_path(cfg: RunConfig) -> Path:
    cache_root = cfg.cache_dir or CACHE_DIR
    cache_root.mkdir(parents=True, exist_ok=True)
    return cache_root / f"{cfg.image_stem}_org.json"


def validate_inputs(cfg: RunConfig) -> list[str]:
    errors: list[str] = []
    if not cfg.image_url and not cfg.image.exists():
        errors.append(f"Изображение не найдено: {cfg.image}")
    if not cfg.org_type.strip():
        errors.append("Не задан --org-type")
    if not cfg.pain.strip():
        errors.append("Не задан --pain")
    return errors


def run_diagnosis(cfg: RunConfig) -> DiagnosisResult:
    errors = validate_inputs(cfg)
    if errors:
        raise ValueError("\n".join(errors))

    if cfg.dry_run:
        return DiagnosisResult(
            image=cfg.image,
            org_type=cfg.org_type,
            pain=cfg.pain,
        )

    require_api_key()
    client = OpenAI()
    prompts = load_all_prompts()

    cache_root = cfg.cache_dir or CACHE_DIR
    cache_root.mkdir(parents=True, exist_ok=True)

    image_for_vision = resolve_image_input(
        image_path=cfg.image,
        image_url=cfg.image_url,
        cache_dir=cache_root / "normalized",
    )
    cfg.image = image_for_vision

    cache_path = default_cache_path(cfg)

    if cfg.skip_vision and cache_path.exists():
        org_json = load_org_json_cache(cache_path)
    elif cfg.use_cache and cache_path.exists() and not cfg.skip_vision:
        org_json = load_org_json_cache(cache_path)
    else:
        org_json = extract_org_json_from_image(
            image_for_vision,
            model=cfg.vision_model,
            system_prompt=prompts["vision"],
            client=client,
        )
        save_org_json_cache(cache_path, org_json)

    hierarchy_text = render_sideways_tree(org_json).strip()
    simple_structure = simplify_structure_llm(
        hierarchy_text,
        org_type=cfg.org_type,
        model=cfg.simplify_model,
        client=client,
    )
    compare_text = compare_simple_structures(simple_structure)
    pain = analyze_pain(cfg.pain, embedding_model=cfg.embedding_model, client=client)

    block_roles = map_departments_to_blocks(
        org_json,
        simple_structure,
        org_type=cfg.org_type,
        model=cfg.simplify_model,
        client=client,
    )

    contact = cfg.contact or default_contact()
    pass1_text = ""
    pass2_text = ""
    step1_text = None

    if cfg.with_block_analysis and prompts.get("pass1"):
        pass1_text = run_pass1_block_analysis(
            system_prompt=prompts["system"],
            pass1_prompt=prompts["pass1"],
            org_type=cfg.org_type,
            pain=cfg.pain,
            hierarchy_text=hierarchy_text,
            simple_structure=simple_structure,
            compare_text=compare_text,
            pain_analysis_text=pain.text,
            model=cfg.simplify_model,
            client=client,
        )
        (cache_root / cfg.image_stem / "pass1.txt").parent.mkdir(parents=True, exist_ok=True)
        (cache_root / cfg.image_stem / "pass1.txt").write_text(pass1_text, encoding="utf-8")

    if cfg.with_admin_analysis and prompts.get("pass2"):
        pass2_text = run_pass2_admin_analysis(
            system_prompt=prompts["system"],
            pass2_prompt=prompts["pass2"],
            org_type=cfg.org_type,
            pain=cfg.pain,
            hierarchy_text=hierarchy_text,
            simple_structure=simple_structure,
            block_roles=block_roles,
            org_json=org_json,
            model=cfg.simplify_model,
            client=client,
        )
        (cache_root / cfg.image_stem / "pass2.txt").write_text(pass2_text, encoding="utf-8")

    if cfg.with_llm_diagnosis or cfg.with_pain_matrix:
        step1_text = run_step1_diagnosis(
            system_prompt=prompts["system"],
            step1_prompt=prompts["step1"],
            org_type=cfg.org_type,
            pain=cfg.pain,
            hierarchy_text=hierarchy_text,
            simple_structure=simple_structure,
            compare_text=compare_text,
            pain_analysis_text=pain.text,
            model=cfg.simplify_model,
            client=client,
        )
        diag_path = cache_root / f"{cfg.image_stem}_step1.txt"
        diag_path.write_text(step1_text, encoding="utf-8")

    artifacts_dir = cache_root / cfg.image_stem
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    visual_paths: dict[str, Path] = {}
    if cfg.save_visuals:
        visual_paths = export_visuals(
            source_image=image_for_vision,
            hierarchy_text=hierarchy_text,
            simple_structure=simple_structure,
            org_type=cfg.org_type,
            out_dir=artifacts_dir,
            stem=cfg.image_stem,
            block_roles=block_roles,
        )

    pdf_path = None
    html_path = None

    if cfg.output_format in ("pdf", "both"):
        out_pdf = cfg.output or default_output_path(cfg)
        conclusion = pass1_text or step1_text or ""
        pdf_path = generate_pdf_report(
            out_pdf,
            profile_text=cfg.org_type,
            org_structure_text=hierarchy_text,
            simple_structure_text=simple_structure,
            compare_text=compare_text,
            pain_text=cfg.pain,
            pain_analysis_text=pain.text,
            causes_text=pain.causes_text,
            actions_text=pain.actions_text,
            conclusion_text=conclusion,
        )

    if cfg.output_format in ("html", "both"):
        out_html = cfg.html_output or default_html_output_path(cfg)
        html_path = generate_html_report(
            out_html,
            org_name=cfg.display_org_name,
            org_type=cfg.org_type,
            visual_paths=visual_paths,
            pass1_text=pass1_text,
            pass2_text=pass2_text,
            contact=contact,
        )

    (artifacts_dir / "summary.json").write_text(
        json.dumps(
            {
                "image": str(image_for_vision),
                "org_type": cfg.org_type,
                "org_name": cfg.display_org_name,
                "pain": cfg.pain,
                "hierarchy": hierarchy_text,
                "simple_structure": simple_structure,
                "compare": compare_text,
                "pain_analysis": pain.text,
                "pass1": pass1_text[:500] if pass1_text else "",
                "pass2": pass2_text[:500] if pass2_text else "",
                "html": str(html_path) if html_path else None,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return DiagnosisResult(
        image=image_for_vision,
        org_type=cfg.org_type,
        pain=cfg.pain,
        org_json=org_json,
        hierarchy_text=hierarchy_text,
        simple_structure=simple_structure,
        compare_text=compare_text,
        pain_analysis_text=pain.text,
        causes_text=pain.causes_text,
        actions_text=pain.actions_text,
        step1_diagnosis=step1_text,
        pass1_text=pass1_text,
        pass2_text=pass2_text,
        pdf_path=pdf_path,
        html_path=html_path,
        cache_path=cache_path,
        visual_paths=visual_paths,
        block_roles=block_roles,
    )
