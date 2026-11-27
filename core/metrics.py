"""WeVisForensics binary metrics adapted for the image scoring script."""

from __future__ import annotations

from typing import Any, Iterable


def _f1(tp: int, fp: int, fn: int) -> float | None:
    denominator = 2 * tp + fp + fn
    return 2 * tp / denominator if denominator else None


def binary_metrics(pairs: Iterable[tuple[str, str | None]]) -> dict[str, Any]:
    """``pairs`` are (label, prediction); a prediction other than real/fake is invalid.

    ``strict`` counts invalid outputs as wrong; ``valid_only`` excludes them.
    """
    pairs = list(pairs)
    valid = [(label, pred) for label, pred in pairs if pred in {"real", "fake"}]

    def block(items: list[tuple[str, str | None]]) -> dict[str, Any]:
        total = len(items)
        correct = sum(label == pred for label, pred in items)
        result: dict[str, Any] = {"n": total, "accuracy": correct / total if total else None}
        for positive in ("fake", "real"):
            tp = sum(label == positive and pred == positive for label, pred in items)
            fp = sum(label != positive and pred == positive for label, pred in items)
            fn = sum(label == positive and pred != positive for label, pred in items)
            support = sum(label == positive for label, _ in items)
            predicted = tp + fp
            result[positive] = {
                "support": support,
                "recall": tp / support if support else None,
                "precision": tp / predicted if predicted else None,
                "f1": _f1(tp, fp, fn),
            }
        return result

    return {
        "rows": len(pairs),
        "invalid": len(pairs) - len(valid),
        "strict": block(pairs),
        "valid_only": block(valid),
    }
