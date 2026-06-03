from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from PIL import Image

from orgdiag.paths import FONT_FILE, REFERENCE_ORG_SCHEME_IMAGE
from orgdiag.structure import (
    REFERENCE_BLOCK_FLOW,
    REFERENCE_SIDE_BLOCKS,
    RIGHT_SIMPLE_STRUCTURE,
    normalize_role_for_display,
)

_font_registered = False


def _ensure_cyrillic_font() -> str | None:
    global _font_registered
    if FONT_FILE.exists():
        font_manager.fontManager.addfont(str(FONT_FILE))
        name = font_manager.FontProperties(fname=str(FONT_FILE)).get_name()
        plt.rcParams["font.family"] = name
        _font_registered = True
        return name
    plt.rcParams["font.family"] = "DejaVu Sans"
    return None


def _parse_flow(text: str) -> list[str]:
    parts = [p.strip() for p in text.replace("→", "->").split("->") if p.strip()]
    return parts if parts else [text.strip() or "?"]


def _draw_flow_on_ax(ax, blocks: list[str], title: str, color: str) -> None:
    ax.set_title(title, fontsize=11, pad=8)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    n = len(blocks)
    if n == 0:
        return
    box_w = min(0.14, 0.85 / max(n, 1))
    gap = (0.9 - box_w * n) / max(n - 1, 1) if n > 1 else 0
    y = 0.45
    h = 0.22
    x0 = 0.05
    for i, label in enumerate(blocks):
        x = x0 + i * (box_w + gap)
        rect = FancyBboxPatch(
            (x, y),
            box_w,
            h,
            boxstyle="round,pad=0.02,rounding_size=0.02",
            linewidth=1.2,
            edgecolor=color,
            facecolor="#f0f4f8" if i % 2 == 0 else "#e8f5e9",
        )
        ax.add_patch(rect)
        ax.text(
            x + box_w / 2,
            y + h / 2,
            label,
            ha="center",
            va="center",
            fontsize=8,
            wrap=True,
        )
        if i < n - 1:
            ax.add_patch(
                FancyArrowPatch(
                    (x + box_w, y + h / 2),
                    (x + box_w + gap, y + h / 2),
                    arrowstyle="-|>",
                    mutation_scale=12,
                    color=color,
                    linewidth=1.2,
                )
            )


def _draw_reference_with_side_blocks(ax, main_flow: str, side_blocks: tuple[str, ...]) -> None:
    """Эталон: основной поток слева, боковые блоки справа (только названия блоков)."""
    ax.set_title("Эталонная упрощённая оргсхема", fontsize=11, pad=8)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    main = _parse_flow(main_flow)
    n = len(main)
    if n == 0:
        return
    box_w = min(0.11, 0.55 / max(n, 1))
    gap = (0.55 - box_w * n) / max(n - 1, 1) if n > 1 else 0
    y_main = 0.55
    h = 0.2
    x0 = 0.03
    color = "#2e7d32"
    for i, label in enumerate(main):
        x = x0 + i * (box_w + gap)
        rect = FancyBboxPatch(
            (x, y_main),
            box_w,
            h,
            boxstyle="round,pad=0.02,rounding_size=0.02",
            linewidth=1.2,
            edgecolor=color,
            facecolor="#e8f5e9",
        )
        ax.add_patch(rect)
        ax.text(x + box_w / 2, y_main + h / 2, label, ha="center", va="center", fontsize=7)
        if i < n - 1:
            ax.add_patch(
                FancyArrowPatch(
                    (x + box_w, y_main + h / 2),
                    (x + box_w + gap, y_main + h / 2),
                    arrowstyle="-|>",
                    mutation_scale=10,
                    color=color,
                    linewidth=1.0,
                )
            )

    side_x = 0.68
    side_w = 0.28
    side_h = 0.16
    for j, label in enumerate(side_blocks):
        y = 0.62 - j * 0.28
        rect = FancyBboxPatch(
            (side_x, y),
            side_w,
            side_h,
            boxstyle="round,pad=0.02,rounding_size=0.02",
            linewidth=1.2,
            edgecolor="#6a1b9a",
            facecolor="#f3e5f5",
        )
        ax.add_patch(rect)
        ax.text(
            side_x + side_w / 2,
            y + side_h / 2,
            label,
            ha="center",
            va="center",
            fontsize=7,
            wrap=True,
        )
        mid_main = x0 + (n - 1) * (box_w + gap) / 2 + box_w / 2
        ax.add_patch(
            FancyArrowPatch(
                (mid_main + box_w / 2, y_main + h / 2),
                (side_x, y + side_h / 2),
                arrowstyle="-|>",
                mutation_scale=8,
                color="#9e9e9e",
                linewidth=0.8,
                linestyle="dashed",
            )
        )


def _draw_admin_blocks_on_ax(
    ax,
    block_roles: dict[str, list[dict[str, Any]]],
    title: str,
) -> None:
    ax.set_title(title, fontsize=11, pad=8)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    blocks = list(block_roles.keys())
    n = len(blocks)
    if n == 0:
        return
    box_w = min(0.16, 0.9 / max(n, 1))
    gap = (0.92 - box_w * n) / max(n - 1, 1) if n > 1 else 0
    x0 = 0.04
    for i, block in enumerate(blocks):
        x = x0 + i * (box_w + gap)
        entries = block_roles.get(block) or []
        lines = [block]
        if not entries:
            lines.append("(руководитель не указан)")
        else:
            for e in entries[:4]:
                role = normalize_role_for_display(
                    e.get("role_label") or "",
                    e.get("dept_label") or "",
                    block,
                )
                person = (e.get("person_name") or "").strip()
                if person:
                    lines.append(f"{role}\n{person}")
                else:
                    lines.append(role)
            if len(entries) > 4:
                lines.append(f"+{len(entries) - 4}…")
        label = "\n".join(lines)
        h = 0.35
        y = 0.32
        rect = FancyBboxPatch(
            (x, y),
            box_w,
            h,
            boxstyle="round,pad=0.02,rounding_size=0.02",
            linewidth=1.2,
            edgecolor="#1565c0",
            facecolor="#e3f2fd",
        )
        ax.add_patch(rect)
        ax.text(
            x + box_w / 2,
            y + h / 2,
            label,
            ha="center",
            va="center",
            fontsize=6,
        )
        if i < n - 1:
            ax.add_patch(
                FancyArrowPatch(
                    (x + box_w, y + h / 2),
                    (x + box_w + gap, y + h / 2),
                    arrowstyle="-|>",
                    mutation_scale=10,
                    color="#1565c0",
                    linewidth=1.0,
                )
            )


def save_source_image(source: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    return dest.resolve()


def render_block_analyzed(simple_structure: str, dest: Path) -> Path:
    """Упрощённая структура (факт) — только блоки."""
    _ensure_cyrillic_font()
    dest.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 3), facecolor="white")
    _draw_flow_on_ax(
        ax,
        _parse_flow(simple_structure),
        "Проанализированная упрощённая структура",
        "#1565c0",
    )
    fig.savefig(dest, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return dest.resolve()


def render_block_reference(
    dest: Path,
    main_flow: str = REFERENCE_BLOCK_FLOW,
    side_blocks: tuple[str, ...] = REFERENCE_SIDE_BLOCKS,
) -> Path:
    """Эталон — рисунок из docs/Упрощ оргсхема.pdf (reference_org_scheme.png)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if REFERENCE_ORG_SCHEME_IMAGE.exists():
        shutil.copy2(REFERENCE_ORG_SCHEME_IMAGE, dest)
        return dest.resolve()
    _ensure_cyrillic_font()
    fig, ax = plt.subplots(figsize=(12, 2.5), facecolor="white")
    blocks = _parse_flow(main_flow)
    _draw_flow_on_ax(ax, blocks, "Эталонная упрощённая оргсхема", "#2e7d32")
    fig.savefig(dest, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return dest.resolve()


def render_admin_roles_diagram(
    block_roles: dict[str, list[dict[str, Any]]],
    dest: Path,
) -> Path:
    _ensure_cyrillic_font()
    dest.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(12, 4), facecolor="white")
    _draw_admin_blocks_on_ax(
        ax,
        block_roles,
        "Структура с административными должностями (руководители)",
    )
    fig.savefig(dest, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return dest.resolve()


def render_result_diagram(
    *,
    hierarchy_text: str,
    simple_structure: str,
    ideal_structure: str = RIGHT_SIMPLE_STRUCTURE,
    org_type: str = "",
    dest: Path,
) -> Path:
    _ensure_cyrillic_font()
    dest.parent.mkdir(parents=True, exist_ok=True)

    fig = plt.figure(figsize=(12, 9), facecolor="white")
    title = "Итог диагностики"
    if org_type:
        title += f" ({org_type})"
    fig.suptitle(title, fontsize=13, y=0.98)

    ax_tree = fig.add_axes([0.06, 0.52, 0.88, 0.42])
    ax_tree.axis("off")
    ax_tree.set_title("Извлечённая иерархия (по изображению)", fontsize=11, loc="left")
    ax_tree.text(
        0.01,
        0.95,
        hierarchy_text,
        transform=ax_tree.transAxes,
        va="top",
        ha="left",
        fontsize=9,
        family="monospace",
    )

    ax_real = fig.add_axes([0.06, 0.06, 0.42, 0.38])
    ax_ideal = fig.add_axes([0.52, 0.06, 0.42, 0.38])
    _draw_flow_on_ax(
        ax_real,
        _parse_flow(simple_structure),
        "Упрощённая структура (факт)",
        "#1565c0",
    )
    _draw_reference_with_side_blocks(ax_ideal, ideal_structure, REFERENCE_SIDE_BLOCKS)

    fig.savefig(dest, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return dest.resolve()


def render_side_by_side(
    source: Path,
    result_diagram: Path,
    dest: Path,
) -> Path:
    _ensure_cyrillic_font()
    dest.parent.mkdir(parents=True, exist_ok=True)

    src_img = Image.open(source).convert("RGB")
    res_img = Image.open(result_diagram).convert("RGB")

    sw, sh = src_img.size
    rw, rh = res_img.size
    target_h = max(sh, rh, 600)
    src_scale = target_h / sh
    res_scale = target_h / rh
    src_resized = src_img.resize(
        (int(sw * src_scale), target_h), Image.Resampling.LANCZOS
    )
    res_resized = res_img.resize(
        (int(rw * res_scale), target_h), Image.Resampling.LANCZOS
    )

    gap = 20
    total_w = src_resized.width + gap + res_resized.width
    canvas = Image.new("RGB", (total_w, target_h), "white")
    canvas.paste(src_resized, (0, 0))
    canvas.paste(res_resized, (src_resized.width + gap, 0))

    fig, axes = plt.subplots(1, 2, figsize=(16, 8), facecolor="white")
    axes[0].imshow(src_resized)
    axes[0].set_title("Исходная оргструктура", fontsize=12)
    axes[0].axis("off")
    axes[1].imshow(res_resized)
    axes[1].set_title("Итог (иерархия + поток vs эталон)", fontsize=12)
    axes[1].axis("off")
    fig.tight_layout()
    fig.savefig(dest, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return dest.resolve()


def export_block_visuals(
    *,
    source_image: Path,
    simple_structure: str,
    block_roles: dict[str, list[dict[str, Any]]],
    out_dir: Path,
    stem: str,
) -> dict[str, Path]:
    """Четыре PNG для HTML-отчёта по плану."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "block_source": out_dir / f"{stem}_block_source.png",
        "block_analyzed": out_dir / f"{stem}_block_analyzed.png",
        "block_reference": out_dir / f"{stem}_block_reference.png",
        "admin_roles": out_dir / f"{stem}_admin_roles.png",
    }
    save_source_image(source_image, paths["block_source"])
    render_block_analyzed(simple_structure, paths["block_analyzed"])
    render_block_reference(paths["block_reference"])
    render_admin_roles_diagram(block_roles, paths["admin_roles"])
    return paths


def export_visuals(
    *,
    source_image: Path,
    hierarchy_text: str,
    simple_structure: str,
    org_type: str,
    out_dir: Path,
    stem: str,
    ideal_structure: str = RIGHT_SIMPLE_STRUCTURE,
    block_roles: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Path]:
    """
    Сохраняет PNG: новые block_* + legacy _01/_02/_03 при необходимости.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, Path] = {}

    if block_roles is not None:
        result.update(
            export_block_visuals(
                source_image=source_image,
                simple_structure=simple_structure,
                block_roles=block_roles,
                out_dir=out_dir,
                stem=stem,
            )
        )

    p_source = out_dir / f"{stem}_01_source.png"
    p_result = out_dir / f"{stem}_02_result.png"
    p_compare = out_dir / f"{stem}_03_compare.png"

    save_source_image(source_image, p_source)
    render_result_diagram(
        hierarchy_text=hierarchy_text,
        simple_structure=simple_structure,
        ideal_structure=ideal_structure,
        org_type=org_type,
        dest=p_result,
    )
    render_side_by_side(p_source, p_result, p_compare)

    result.update({"source": p_source, "result": p_result, "compare": p_compare})
    return result
