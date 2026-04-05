from __future__ import annotations

from pathlib import Path

import numpy as np


def load_histogram_csv(path: str | Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    data = np.loadtxt(path, delimiter=",", skiprows=1)
    similarities = data[:, 0].astype(int)
    counts = data[:, 1].astype(int)
    raw = np.repeat(similarities, counts)
    return similarities, counts, raw.astype(int)


def threshold_curve(raw_scores: np.ndarray) -> np.ndarray:
    curve = []
    for threshold in range(0, 101):
        labels = np.where(raw_scores >= threshold, 1, 0)
        curve.append(labels.sum() / len(labels))
    return np.array(curve, dtype=float)


def weighted_threshold_score(raw_scores: np.ndarray) -> float:
    accuracy = threshold_curve(raw_scores)
    thresholds = np.arange(0, 101)
    return float((accuracy * thresholds / thresholds.sum()).sum() * 100.0)


def plot_benchmark_grid(root: str | Path = ".", output_path: str | Path = "benchmark_grid.png") -> None:
    import matplotlib.pyplot as plt

    base = Path(root)
    modes = ["easy", "medium", "hard"]
    models = ["Gemini1.5-pro", "GPT4o", "Llama3.3-70B", "GPTo1"]
    colors = ["#4363d8", "#3cb44b", "#e6194b", "#f58231"]
    figure, axes = plt.subplots(3, 3, figsize=(16, 9))
    flat_axes = axes.flatten()
    for mode_index, mode in enumerate(modes):
        distributions = []
        labels = []
        for model_index, model in enumerate(models):
            _, _, raw = load_histogram_csv(base / f"{mode}_dataset_figure" / f"{model}.csv")
            distributions.append(raw)
            score = weighted_threshold_score(raw)
            labels.append(f"{model}_{score:.1f}")
            flat_axes[mode_index + 3].plot(threshold_curve(raw), label=model, color=colors[model_index], linewidth=2)
        flat_axes[mode_index].hist(distributions, bins=10, range=[0, 100], density=True, histtype="bar", label=labels, color=colors)
        flat_axes[mode_index].set_title(f"Similarity Score Distribution ({mode})")
        flat_axes[mode_index + 3].set_title(f"Accuracy w.r.t Threshold ({mode})")
    for axis in flat_axes[:6]:
        axis.legend(fontsize="x-small")
    plt.tight_layout()
    plt.savefig(output_path, dpi=200)
    plt.close(figure)

