"""
Generate plots from eval report JSONs in reports/.

Outputs (saved to plots/):
  1. score_vs_latency.png  — scatter plot of latency vs score, grouped by system
  2. category_scores.png   — grouped bar chart of avg score per category per system

Run from repo root:
    python debug/plot_results.py
"""

import json
import os
import sys
from collections import defaultdict

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORTS_DIR = os.path.join(REPO_ROOT, "reports")
PLOTS_DIR = os.path.join(REPO_ROOT, "plots")

# ── global style ──────────────────────────────────────────────────────────────
plt.style.use("seaborn-v0_8-whitegrid")
mpl.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Inter", "Helvetica Neue", "Arial", "DejaVu Sans"],
    "axes.titlesize": 15,
    "axes.titleweight": "bold",
    "axes.labelsize": 12,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "legend.fontsize": 10,
    "legend.framealpha": 0.9,
    "figure.dpi": 180,
})

_PALETTE = [
    "#4C72B0", "#DD8452", "#55A868", "#C44E52",
    "#8172B3", "#937860", "#DA8BC3", "#8C8C8C",
    "#CCB974", "#64B5CD",
]


def load_reports():
    if not os.path.isdir(REPORTS_DIR):
        print("reports/ directory not found at {path}".format(path=REPORTS_DIR))
        sys.exit(1)
    reports = []
    for filename in sorted(os.listdir(REPORTS_DIR)):
        if filename.endswith(".json"):
            with open(os.path.join(REPORTS_DIR, filename)) as f:
                reports.append(json.load(f))
    if not reports:
        print("No report JSON files found in {path}".format(path=REPORTS_DIR))
        sys.exit(1)
    return reports


def build_dataset(reports):
    """
    Returns dict: system_name -> list of {score, latency_s, category}.
    System names are formatted as baseline_v1, agent_v1, agent_v2, etc.
    """
    data = defaultdict(list)
    for report in reports:
        version = report["meta"]["version"]
        for case in report["cases"]:
            category = case["category"]
            for role in ("baseline", "agent"):
                result = case.get(role)
                if result is None:
                    continue
                score = result.get("final_score")
                if score is None:
                    continue
                data["{role}_{version}".format(role=role, version=version)].append({
                    "score": score,
                    "latency_s": result.get("latency_s"),
                    "category": category,
                })
    return data


def assign_colors(system_names):
    return {name: _PALETTE[i % len(_PALETTE)] for i, name in enumerate(sorted(system_names))}


def plot_score_vs_latency(data, colors, output_path):
    fig, ax = plt.subplots(figsize=(10, 7))

    for name in sorted(data.keys()):
        points = [(p["score"], p["latency_s"]) for p in data[name] if p["latency_s"] is not None]
        if not points:
            continue
        scores, latencies = zip(*points)
        n = len(points)
        color = colors[name]

        label = "{name}  (n={n})".format(name=name, n=n)
        ax.scatter(scores, latencies, alpha=0.35, s=50, color=color, label=label, zorder=3)

        mean_score = float(np.mean(scores))
        mean_lat = float(np.mean(latencies))
        ax.scatter([mean_score], [mean_lat], s=240, color=color, marker="D",
                   edgecolors="white", linewidths=1.5, zorder=5)
        ax.annotate(
            "  {name}\n  ({score:.2f}, {lat:.1f}s)".format(
                name=name, score=mean_score, lat=mean_lat
            ),
            xy=(mean_score, mean_lat),
            fontsize=8.5,
            color=color,
            va="center",
            fontweight="semibold",
        )

    ax.set_xlabel("Final Score (0–2)", fontsize=12)
    ax.set_ylabel("Latency (s)", fontsize=12)
    ax.set_title("Latency vs Eval Score by System", fontsize=15, pad=12)
    ax.set_xticks([0, 1, 2])
    ax.legend(loc="upper left", framealpha=0.9, edgecolor="#cccccc")
    ax.grid(True, alpha=0.3, linewidth=0.7)

    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)

    fig.tight_layout()
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    print("Saved: {path}".format(path=output_path))


def plot_category_bars(data, colors, output_path):
    categories = sorted({p["category"] for points in data.values() for p in points})
    systems = sorted(data.keys())
    n_sys = len(systems)
    n_cat = len(categories)

    avg_scores = {}
    run_counts = {}
    for name in systems:
        by_cat = defaultdict(list)
        for p in data[name]:
            by_cat[p["category"]].append(p["score"])
        avg_scores[name] = [
            float(np.mean(by_cat[cat])) if by_cat.get(cat) else 0.0
            for cat in categories
        ]
        run_counts[name] = [len(by_cat[cat]) for cat in categories]

    x = np.arange(n_cat)
    group_width = 0.72
    bar_width = group_width / n_sys

    fig, ax = plt.subplots(figsize=(13, 6))
    for i, name in enumerate(systems):
        offset = (i - n_sys / 2 + 0.5) * bar_width
        total_n = sum(run_counts[name])
        label = "{name}  (n={n})".format(name=name, n=total_n)
        ax.bar(x + offset, avg_scores[name], bar_width,
               label=label, color=colors[name], edgecolor="white", linewidth=0.8, zorder=3)

    ax.set_xticks(x)
    ax.set_xticklabels(categories, rotation=30, ha="right", fontsize=10)
    ax.set_ylabel("Average Final Score (0–2)", fontsize=12)
    ax.set_title("Average Score by Category and System", fontsize=15, pad=12)
    ax.set_ylim(0, 2.3)
    ax.axhline(y=2.0, color="#888888", linestyle="--", linewidth=0.9, alpha=0.6, zorder=2)
    ax.legend(loc="upper right", framealpha=0.9, edgecolor="#cccccc")
    ax.grid(True, axis="y", alpha=0.3, linewidth=0.7)

    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)

    fig.tight_layout()
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    print("Saved: {path}".format(path=output_path))


def main():
    os.makedirs(PLOTS_DIR, exist_ok=True)

    reports = load_reports()
    data = build_dataset(reports)

    if not data:
        print("No case data found in reports.")
        sys.exit(1)

    print("Systems found: {s}".format(s=", ".join(sorted(data.keys()))))
    for name in sorted(data.keys()):
        n = len(data[name])
        has_latency = sum(1 for p in data[name] if p["latency_s"] is not None)
        print("  {name}: {n} cases, {lat} with latency".format(
            name=name, n=n, lat=has_latency
        ))
    print()

    colors = assign_colors(data.keys())
    plot_score_vs_latency(data, colors, os.path.join(PLOTS_DIR, "score_vs_latency.png"))
    plot_category_bars(data, colors, os.path.join(PLOTS_DIR, "category_scores.png"))


if __name__ == "__main__":
    main()
