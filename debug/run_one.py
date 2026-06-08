import argparse
import importlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from systems import run_agent, strip_reasoning
from evals.judge import run_judge

DIVIDER = "=" * 60

def get_text(response, version: str = "v1") -> str:
    for block in response.content:
        if block.type == "text":
            return strip_reasoning(block.text) if version == "v3" else block.text
    return ""

def print_result(label: str, version: str, result: dict, judge_result: dict = None):
    print(DIVIDER)
    print("{label} — prompts/{version}.py".format(label=label, version=version))
    print(DIVIDER)
    print("Response:")
    for line in get_text(result["response"], version).splitlines():
        print("  " + line)
    print()
    print("Wikipedia calls: {n}".format(n=result["tool_calls"]))
    print("Latency:         {latency}s".format(latency=result["latency_s"]))
    print("Input tokens:    {tokens}".format(tokens=result["input_tokens"]))
    print("Output tokens:   {tokens}".format(tokens=result["output_tokens"]))
    if judge_result:
        passed_label = "PASS" if judge_result["passed"] else "FAIL"
        print()
        print("Judge Score:     {score}/2  [{label}]".format(score=judge_result["final_score"], label=passed_label))
        print("Primary metric:  {metric} → {score}".format(
            metric=judge_result["primary_metric"],
            score=judge_result["scores"][judge_result["primary_metric"]],
        ))
        print("Hallucination:   {s}  |  Formatting: {f}".format(
            s=judge_result["scores"]["hallucination_check"],
            f=judge_result["scores"]["formatting"],
        ))
        if judge_result["scores"].get("information_gain") is not None:
            print("Information gain: {s}".format(s=judge_result["scores"]["information_gain"]))
        print("Hard fail:       {reason}".format(reason=judge_result["hard_fail_reason"] or "None"))
        print("Routing penalty: {penalty}".format(penalty=judge_result["routing_penalty"]))
        print()
        print("Judge Reasoning:")
        for line in judge_result["reasoning"].splitlines():
            print("  " + line)
    print()

def main():
    parser = argparse.ArgumentParser(description="Run a single test case and compare baseline vs. agent.")
    parser.add_argument("--id", required=True, help="Test case ID from test_cases.json")
    parser.add_argument("--version", default="v1", help="Prompt version module (default: v1)")
    #parser.add_argument("--split", default="validation_cases.json", help="Test case set")

    args = parser.parse_args()

    data_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "evals", "data", "validation_cases.json")
    with open(data_path) as f:
        test_cases = json.load(f)

    test_case = next((tc for tc in test_cases if tc["id"] == args.id), None)
    if not test_case:
        print("Test case '{id}' not found.".format(id=args.id))
        sys.exit(1)

    try:
        prompts = importlib.import_module("prompts.{version}".format(version=args.version))
    except ModuleNotFoundError:
        print("Prompt version '{version}' not found. Make sure prompts/{version}.py exists.".format(version=args.version))
        sys.exit(1)

    question = test_case["question"]
    print("\nTest Case #{id} — {category}".format(id=test_case["id"], category=test_case["category"]))
    print("Question: {question}\n".format(question=question))

    print("Running baseline...")
    baseline_result = run_agent(question, prompts.BASELINE_PROMPT, use_tools=False)

    print("Running agent with Wikipedia tool...")
    agent_result = run_agent(question, prompts.AGENT_PROMPT, use_tools=True)

    print("Running judge...")
    baseline_judge = run_judge(test_case, get_text(baseline_result["response"], args.version), tool_calls_made=baseline_result["tool_calls"])
    agent_judge = run_judge(test_case, get_text(agent_result["response"], args.version), tool_calls_made=agent_result["tool_calls"])

    print()
    print_result("BASELINE (no tools)", args.version, baseline_result, judge_result=baseline_judge)
    print_result("AGENT (Wikipedia)", args.version, agent_result, judge_result=agent_judge)

if __name__ == "__main__":
    main()
