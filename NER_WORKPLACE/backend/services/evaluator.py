from __future__ import annotations


def partial_match_counts(gold: list[dict], pred: list[dict]) -> dict[str, int]:
    exact = partial = 0
    matched_pred: set[int] = set()
    for g in gold:
        g_span = (g["start"], g["end"], g.get("type"))
        found_partial = False
        for i, p in enumerate(pred):
            if i in matched_pred or p.get("type") != g.get("type"):
                continue
            p_span = (p["start"], p["end"], p.get("type"))
            if p_span == g_span:
                exact += 1
                matched_pred.add(i)
                found_partial = True
                break
            if not (p["end"] <= g["start"] or p["start"] >= g["end"]):
                found_partial = True
                partial += 1
                matched_pred.add(i)
                break
        if not found_partial:
            pass
    missing = max(0, len(gold) - exact - partial)
    spurious = max(0, len(pred) - len(matched_pred))
    return {"exact": exact, "partial": partial, "missing": missing, "spurious": spurious}


def simple_prf(tp: int, pred_total: int, gold_total: int) -> dict[str, float]:
    precision = tp / pred_total if pred_total else 0.0
    recall = tp / gold_total if gold_total else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}

