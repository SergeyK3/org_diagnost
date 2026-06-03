from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np
import pandas as pd
from openai import OpenAI

from orgdiag.config import require_api_key
from orgdiag.paths import MATRIX_FILE


@dataclass
class PainAnalysis:
    text: str
    causes_text: str
    actions_text: str


def load_defects_matrix(path=None) -> pd.DataFrame:
    matrix_path = path or MATRIX_FILE
    return pd.read_csv(matrix_path, sep="\t")


def get_embedding(text: str, *, model: str = "text-embedding-3-small", client: OpenAI | None = None) -> list[float]:
    require_api_key()
    client = client or OpenAI()
    response = client.embeddings.create(input=[text], model=model)
    return response.data[0].embedding


def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    v1 = np.array(vec1)
    v2 = np.array(vec2)
    return float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)))


def analyze_pain(
    pain_text: str,
    *,
    df_defects: pd.DataFrame | None = None,
    embedding_model: str = "text-embedding-3-small",
    top_n: int = 3,
    min_threshold: float = 0.2,
    client: OpenAI | None = None,
) -> PainAnalysis:
    df = df_defects if df_defects is not None else load_defects_matrix()
    client = client or OpenAI()

    pain_emb = get_embedding(pain_text, model=embedding_model, client=client)
    similarities: list[float] = []
    for symptom in df["Симптом"]:
        try:
            emb = get_embedding(str(symptom), model=embedding_model, client=client)
            similarities.append(cosine_similarity(pain_emb, emb))
        except Exception:
            similarities.append(0.0)

    top_idx = np.argsort(similarities)[-top_n:][::-1]
    top_scores = [similarities[i] for i in top_idx]
    final_idx = [i for i, score in zip(top_idx, top_scores) if score >= min_threshold]
    if not final_idx and len(top_idx) > 0:
        final_idx = [top_idx[0]]

    fragments = [f"Боль: {pain_text}"]
    causes: set[str] = set()
    actions: set[str] = set()

    if not final_idx:
        fragments.append("Нет системных причин и управленческих действий в матрице дефектов.")
    else:
        for i in final_idx:
            row = df.iloc[i]
            cause = str(row["Системная причина"]).strip()
            if cause and cause.lower() != "nan":
                causes.add(cause)
            actions_raw = str(row["Управленческие действия (P1/P2/P3)"])
            actions_clean = re.sub(r"P[1-3]:\s*", "", actions_raw)
            for act in actions_clean.split("\n"):
                act = act.strip()
                if act and act.lower() != "nan":
                    actions.add(act)

        if causes:
            fragments.append("Системные причины:")
            for cause in causes:
                fragments.append(f"- {cause}")
        else:
            fragments.append("Системные причины: не определены")

        if actions:
            fragments.append("Рекомендуемые управленческие действия:")
            for action in actions:
                fragments.append(f"- {action}")
        else:
            fragments.append("Рекомендуемые управленческие действия: не определены")

    text = "\n".join(fragments)
    causes_text = "\n".join(f"- {c}" for c in sorted(causes))
    actions_text = "\n".join(f"- {a}" for a in sorted(actions))
    return PainAnalysis(text=text, causes_text=causes_text, actions_text=actions_text)
