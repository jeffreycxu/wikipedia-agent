import argparse
import importlib
import json
import os
import sys
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from systems import run_agent, strip_reasoning
from evals.judge import run_judge
from tool.wikipedia_tool import WikipediaRateLimitError

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(REPO_ROOT, "evals", "data")
REPORTS_DIR = os.path.join(REPO_ROOT, "reports")


def get_text(response) -> str:
    for block in response.content:
        if block.type == "text":
            return block.text
    return ""


def compute_summary(results: list[dict]) -> dict:
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    scores = [r["final_score"] for r in results]
    hard_fails = sum(1 for r in results if r["hard_fail_reason"])
    routing_penalties = sum(1 for r in results if r["routing_penalty"])

    by_category: dict = defaultdict(lambda: {"passed": 0, "total": 0, "scores": []})
    for r in results:
        cat = r["category"]
        by_category[cat]["total"] += 1
        by_category[cat]["scores"].append(r["final_score"])
        if r["passed"]:
            by_category[cat]["passed"] += 1

    return {
        "overall_pass_rate": round(passed / total, 3) if total else 0,
        "overall_avg_score": round(sum(scores) / total, 2) if total else 0,
        "passed": passed,
        "total": total,
        "hard_fails": hard_fails,
        "routing_penalties": routing_penalties,
        "by_category": {
            cat: {
                "passed": v["passed"],
                "total": v["total"],
                "avg_score": round(sum(v["scores"]) / v["total"], 2),
            }
            for cat, v in sorted(by_category.items())
        },
    }


def print_summary(split: str, version: str, baseline_summary: dict, agent_summary: dict, report_path: str):
    print("\n=== RESULTS ({split} / {version}) ===\n".format(split=split, version=version))

    categories = sorted(
        set(baseline_summary["by_category"]) | set(agent_summary["by_category"])
    )

    print("{:<24} {:<20} {:<20}".format("Category", "Baseline", "Agent"))
    print("{:<24} {:<20} {:<20}".format("", "Pass    Avg", "Pass    Avg"))
    print("-" * 64)

    for cat in categories:
        b = baseline_summary["by_category"].get(cat, {"passed": 0, "total": 0, "avg_score": 0.0})
        a = agent_summary["by_category"].get(cat, {"passed": 0, "total": 0, "avg_score": 0.0})
        b_pass = "{p}/{t}".format(p=b["passed"], t=b["total"])
        a_pass = "{p}/{t}".format(p=a["passed"], t=a["total"])
        print("{:<24} {:<8} {:<12.1f} {:<8} {:.1f}".format(
            cat, b_pass, b["avg_score"], a_pass, a["avg_score"]
        ))

    print("-" * 64)
    b_pass = "{p}/{t}".format(p=baseline_summary["passed"], t=baseline_summary["total"])
    a_pass = "{p}/{t}".format(p=agent_summary["passed"], t=agent_summary["total"])
    print("{:<24} {:<8} {:<12.1f} {:<8} {:.1f}".format(
        "OVERALL",
        b_pass, baseline_summary["overall_avg_score"],
        a_pass, agent_summary["overall_avg_score"],
    ))

    print()
    print("Hard fails:        baseline={b}  agent={a}".format(
        b=baseline_summary["hard_fails"], a=agent_summary["hard_fails"]
    ))
    print("Routing penalties: baseline={b}  agent={a}".format(
        b=baseline_summary["routing_penalties"], a=agent_summary["routing_penalties"]
    ))
    print()
    print("Report saved → {path}".format(path=report_path))


def run_case(test_case: dict, prompts, version: str, idx: int, total: int, max_retries: int = 3) -> dict:
    question = test_case["question"]

    for attempt in range(max_retries):
        try:
            baseline_run = run_agent(question, prompts.BASELINE_PROMPT, use_tools=False)
            agent_run = run_agent(question, prompts.AGENT_PROMPT, use_tools=True)

            def clean(run):
                t = get_text(run["response"])
                return strip_reasoning(t) if version == "v3" else t

            baseline_judge = run_judge(test_case, clean(baseline_run), baseline_run["tool_calls"])
            agent_judge = run_judge(test_case, clean(agent_run), agent_run["tool_calls"])

            short_q = question[:52] + "..." if len(question) > 52 else question
            b_label = "PASS" if baseline_judge["passed"] else "FAIL"
            a_label = "PASS" if agent_judge["passed"] else "FAIL"
            retry_tag = " [retry {a}]".format(a=attempt) if attempt > 0 else ""
            print("[{idx}/{total}]{tag} {cat}: \"{q}\"".format(
                idx=idx, total=total, tag=retry_tag, cat=test_case["category"], q=short_q
            ))
            print("  baseline → {b} ({bs})   agent → {a} ({as_})".format(
                b=b_label, bs=baseline_judge["final_score"],
                a=a_label, as_=agent_judge["final_score"],
            ))

            return {
                "test_id": test_case["id"],
                "question": question,
                "category": test_case["category"],
                "expected_routing": test_case["eval"]["expected_routing"],
                "baseline": {**baseline_judge, "latency_s": baseline_run["latency_s"]},
                "agent": {**agent_judge, "latency_s": agent_run["latency_s"]},
            }

        except WikipediaRateLimitError:
            if attempt < max_retries - 1:
                print("[{idx}/{total}] Wikipedia 429 — restarting case with clean latency (attempt {a}/{n})...".format(
                    idx=idx, total=total, a=attempt + 1, n=max_retries
                ))
            else:
                print("[{idx}/{total}] Wikipedia 429 — max retries exhausted, skipping case.".format(
                    idx=idx, total=total
                ))
                raise


def main():
    parser = argparse.ArgumentParser(description="Run evals on a test split for baseline and agent.")
    parser.add_argument("--split", default="test", choices=["test", "validation"])
    parser.add_argument("--version", default="v1", help="Prompt version (default: v1)")
    args = parser.parse_args()

    data_file = os.path.join(DATA_DIR, "{split}_cases.json".format(split=args.split))
    with open(data_file) as f:
        test_cases = json.load(f)

    try:
        prompts = importlib.import_module("prompts.{version}".format(version=args.version))
    except ModuleNotFoundError:
        print("Prompt version '{v}' not found.".format(v=args.version))
        sys.exit(1)

    os.makedirs(REPORTS_DIR, exist_ok=True)

    total = len(test_cases)
    print("Running {total} cases ({split} / {version})\n".format(
        total=total, split=args.split, version=args.version
    ))

    cases_output = []
    for i, tc in enumerate(test_cases):
        cases_output.append(run_case(tc, prompts, args.version, i + 1, total))

    baseline_results = [c["baseline"] for c in cases_output]
    agent_results = [c["agent"] for c in cases_output]

    baseline_summary = compute_summary(baseline_results)
    agent_summary = compute_summary(agent_results)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_filename = "eval_{split}_{version}_{ts}.json".format(
        split=args.split, version=args.version, ts=timestamp
    )
    report_path = os.path.join(REPORTS_DIR, report_filename)

    report = {
        "meta": {
            "split": args.split,
            "version": args.version,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "total_cases": total,
        },
        "summary": {
            "baseline": baseline_summary,
            "agent": agent_summary,
        },
        "cases": cases_output,
    }

    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    print_summary(args.split, args.version, baseline_summary, agent_summary, report_path)


if __name__ == "__main__":
    main()
