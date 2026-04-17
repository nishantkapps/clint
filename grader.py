#!/usr/bin/env python3
"""
grader.py — C-Lab Autograder (local runner)

Scoring tiers:
  static  → regex pattern matching (fast, free, deterministic)
  llm     → LLM API evaluation     (nuanced, requires API key)
  test    → compile + run vs. expected output

Usage:
    python3 grader.py
    python3 grader.py --config config.json
    python3 grader.py --submissions ./submissions --rubric rubric.json --output results.csv
"""

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


# ── Config & rubric ───────────────────────────────────────────────────────────

def load_config(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def load_rubric(path: str) -> list[dict]:
    with open(path) as f:
        data = json.load(f)
    return data.get("items", [])


# ── Student ID extraction ─────────────────────────────────────────────────────

def extract_student_id(filename: str, strategy: str, regex_pattern: str = None) -> str:
    stem = Path(filename).stem
    if strategy == "before_first_underscore":
        return stem.split("_")[0]
    if strategy == "after_last_underscore":
        return stem.rsplit("_", 1)[-1]
    if strategy == "whole_filename":
        return stem
    if strategy == "regex":
        m = re.match(regex_pattern or r"^([^_]+)", stem)
        return m.group(1) if m else stem
    return stem


# ── Compile ───────────────────────────────────────────────────────────────────

def compile_c_file(c_file: Path, compile_timeout: int) -> tuple[bool, str, Path | None]:
    tmp_dir = tempfile.mkdtemp(prefix="clint_")
    binary = Path(tmp_dir) / "a.out"
    try:
        result = subprocess.run(
            ["gcc", str(c_file), "-o", str(binary), "-w", "-lm"],
            capture_output=True, text=True, timeout=compile_timeout,
        )
        if result.returncode == 0:
            return True, "", binary
        return False, result.stderr.strip(), None
    except subprocess.TimeoutExpired:
        return False, "Compilation timed out.", None
    except FileNotFoundError:
        print("\n[ERROR] gcc not found. Install with: sudo apt-get install gcc\n")
        sys.exit(1)


# ── Static scorer (regex patterns) ───────────────────────────────────────────

def score_static(item: dict, code: str) -> tuple[int, str]:
    """
    Award marks proportionally: each pattern that matches = (max_marks / total_patterns).
    If no patterns are defined, fall back to keyword scan from the condition text.
    Full marks only if ALL patterns match.
    """
    max_marks = item.get("max_marks", 0)
    patterns  = item.get("patterns", [])

    if not patterns:
        # Fallback: extract C identifiers / filenames from condition and check presence
        words = re.findall(r'[\w\.]+', item.get("condition", ""))
        c_keywords = {"include", "int", "char", "float", "double", "void",
                      "return", "if", "else", "for", "while", "struct", "pointer"}
        candidates = [w for w in words if w not in c_keywords and len(w) > 2]
        if not candidates:
            return 0, "No patterns and no keywords to match."
        matched = [c for c in candidates if c.lower() in code.lower()]
        frac = len(matched) / len(candidates)
        marks = round(max_marks * frac)
        reason = f"Keyword scan: {len(matched)}/{len(candidates)} terms found ({', '.join(matched[:4])})."
        return marks, reason

    matched = []
    missed  = []
    for pat in patterns:
        try:
            if re.search(pat, code, re.IGNORECASE | re.MULTILINE):
                matched.append(pat)
            else:
                missed.append(pat)
        except re.error:
            # Treat invalid regex as a plain-text search
            if pat.lower() in code.lower():
                matched.append(pat)
            else:
                missed.append(pat)

    if len(matched) == len(patterns):
        marks  = max_marks
        reason = f"All {len(patterns)} pattern(s) matched."
    elif matched:
        marks  = round(max_marks * len(matched) / len(patterns))
        reason = f"{len(matched)}/{len(patterns)} patterns matched. Missing: {', '.join(missed[:3])}."
    else:
        marks  = 0
        reason = f"No patterns matched. Expected: {', '.join(patterns[:3])}."

    return marks, reason


# ── LLM scorer ───────────────────────────────────────────────────────────────

def score_llm(item: dict, code: str, llm_config: dict) -> tuple[int, str]:
    """Call an LLM to score this rubric item. Returns (marks, reason)."""
    try:
        import litellm
    except ImportError:
        return 0, "litellm not installed — run: pip install litellm"

    model   = llm_config.get("llm_model", "claude-3-haiku-20240307")
    api_key = llm_config.get("llm_api_key", "")
    max_marks = item.get("max_marks", 0)

    if not api_key:
        return 0, "No LLM API key configured — set llm_api_key in config.json."

    # Set key for litellm
    provider = llm_config.get("llm_provider", "anthropic")
    if provider == "anthropic":
        os.environ["ANTHROPIC_API_KEY"] = api_key
    elif provider == "openai":
        os.environ["OPENAI_API_KEY"] = api_key

    prompt = f"""You are a C programming teacher grading a student submission.

Rubric criterion : {item['name']}
Description      : {item.get('condition', '')}
Maximum marks    : {max_marks}

Student C code:
```c
{code[:4000]}
```

Award an integer between 0 and {max_marks} for this specific criterion only.
Reply with ONLY valid JSON — no extra text:
{{"marks": <integer 0-{max_marks}>, "reason": "<one concise sentence>"}}"""

    try:
        response = litellm.completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=120,
            temperature=0,
        )
        raw = response.choices[0].message.content.strip()
        # Strip markdown fences if present
        raw = re.sub(r"^```[a-z]*\n?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        result = json.loads(raw)
        marks = max(0, min(int(result.get("marks", 0)), max_marks))
        return marks, result.get("reason", "")
    except json.JSONDecodeError as e:
        return 0, f"LLM returned invalid JSON: {e}"
    except Exception as e:
        return 0, f"LLM error: {e}"


# ── Test scorer (run binary vs expected output) ───────────────────────────────

def score_test(item: dict, binary: Path, tests_dir: Path, run_timeout: int) -> tuple[int, str]:
    """
    Looks for test_cases/<test_case_key>/input_*.txt + expected_*.txt pairs.
    Awards marks proportionally based on how many test cases pass.
    """
    max_marks  = item.get("max_marks", 0)
    test_key   = item.get("test_case", "test_1")
    test_path  = tests_dir / test_key

    if not test_path.exists():
        return 0, f"Test folder not found: {test_path}"

    inputs   = sorted(test_path.glob("input_*.txt"))
    if not inputs:
        return 0, f"No input_*.txt files in {test_path}"

    passed = 0
    details = []
    for inp in inputs:
        idx = inp.stem.replace("input_", "")
        exp_file = test_path / f"expected_{idx}.txt"
        if not exp_file.exists():
            continue
        expected = exp_file.read_text().strip()
        try:
            result = subprocess.run(
                [str(binary)],
                input=inp.read_text(),
                capture_output=True, text=True, timeout=run_timeout,
            )
            actual = result.stdout.strip()
            if actual == expected:
                passed += 1
                details.append(f"test_{idx}:pass")
            else:
                details.append(f"test_{idx}:fail")
        except subprocess.TimeoutExpired:
            details.append(f"test_{idx}:timeout")
        except Exception as e:
            details.append(f"test_{idx}:error({e})")

    total = len(inputs)
    if total == 0:
        return 0, "No valid test pairs found."

    marks  = round(max_marks * passed / total)
    reason = f"{passed}/{total} tests passed. {' '.join(details)}."
    return marks, reason


# ── Per-file grader ───────────────────────────────────────────────────────────

def grade_file(
    c_file: Path,
    rubric_items: list[dict],
    config: dict,
) -> dict:
    compile_timeout = config.get("compile_timeout_seconds", 10)
    run_timeout     = config.get("run_timeout_seconds", 2)
    tests_dir       = Path(config.get("tests_dir", "./test_cases"))
    llm_config      = config  # pass full config so llm scorer can read keys

    # ── Compile ──
    compiles, compile_error, binary = compile_c_file(c_file, compile_timeout)
    code = c_file.read_text(errors="replace")

    scores   = {}
    reasons  = {}
    feedback = []

    for item in rubric_items:
        name      = item["name"]
        item_type = item.get("type", "static")
        max_marks = item.get("max_marks", 0)

        if item_type == "static":
            marks, reason = score_static(item, code)

        elif item_type == "llm":
            marks, reason = score_llm(item, code, llm_config)

        elif item_type == "test":
            if compiles and binary:
                marks, reason = score_test(item, binary, tests_dir, run_timeout)
            else:
                marks, reason = 0, "Did not compile — test not run."

        else:
            marks, reason = 0, f"Unknown type: {item_type}"

        scores[name]  = marks
        reasons[name] = reason
        feedback.append(f"{name} ({marks}/{max_marks}): {reason}")

    total = sum(scores.values())

    # cleanup binary
    if binary and binary.exists():
        binary.unlink()
        try:
            binary.parent.rmdir()
        except OSError:
            pass

    return {
        "compiles":      compiles,
        "compile_error": compile_error,
        "scores":        scores,
        "reasons":       reasons,
        "total":         total,
        "feedback":      "\n".join(feedback),
    }


# ── Batch processor ───────────────────────────────────────────────────────────

def grade_all(config: dict, rubric_items: list[dict]) -> list[dict]:
    submissions_dir = Path(config["submissions_dir"])
    id_cfg   = config.get("id_extraction", {})
    strategy = id_cfg.get("strategy", "before_first_underscore")
    regex_pat= id_cfg.get("regex")

    c_files = sorted(submissions_dir.glob("**/*.c"))
    if not c_files:
        print(f"[WARN] No .c files found in '{submissions_dir}'")
        return []

    print(f"Found {len(c_files)} submission(s) in '{submissions_dir}'")
    if rubric_items:
        print(f"Rubric: {len(rubric_items)} item(s) — "
              f"{sum(1 for i in rubric_items if i.get('type')=='static')} static, "
              f"{sum(1 for i in rubric_items if i.get('type')=='llm')} LLM, "
              f"{sum(1 for i in rubric_items if i.get('type')=='test')} test")
    print()

    results = []

    for idx, c_file in enumerate(c_files, 1):
        student_id = extract_student_id(c_file.name, strategy, regex_pat)
        print(f"[{idx:>3}/{len(c_files)}] {student_id:<25} ", end="", flush=True)

        result = grade_file(c_file, rubric_items, config)

        compile_flag = "✓ Compiles" if result["compiles"] else "✗ No compile"
        score_str    = f"  Score: {result['total']}" if rubric_items else ""
        print(f"{compile_flag}{score_str}", flush=True)

        row = {
            "Student_ID":    student_id,
            "File":          c_file.name,
            "Compiles":      "Y" if result["compiles"] else "N",
            "Compile_Error": "" if result["compiles"] else result["compile_error"],
        }
        row.update(result["scores"])

        if rubric_items:
            row["Total_Score"] = result["total"]
            row["Max_Score"]   = sum(i.get("max_marks", 0) for i in rubric_items)
        row["Feedback"] = result["feedback"]

        results.append(row)

    return results


# ── CSV export ────────────────────────────────────────────────────────────────

def export_csv(results: list[dict], output_path: str, rubric_items: list[dict]):
    if not results:
        print("[WARN] No results to write.")
        return

    fixed   = ["Student_ID", "File", "Compiles", "Compile_Error"]
    rubric  = [item["name"] for item in rubric_items]
    trailing= (["Total_Score", "Max_Score", "Feedback"] if rubric_items
                else ["Feedback"])
    fieldnames = fixed + rubric + trailing

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)

    print(f"\nResults written to: {output_path}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="C-Lab Autograder — local GCC grader")
    parser.add_argument("--config",      default="config.json")
    parser.add_argument("--submissions", help="Override submissions directory")
    parser.add_argument("--rubric",      help="Override rubric JSON file")
    parser.add_argument("--output",      help="Override output CSV path")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"[WARN] Config '{args.config}' not found — using defaults.")
        config = {
            "submissions_dir": "./submissions",
            "rubric_file": "./rubric.json",
            "output_csv": "./results.csv",
            "tests_dir": "./test_cases",
            "id_extraction": {"strategy": "before_first_underscore"},
            "compile_timeout_seconds": 10,
            "run_timeout_seconds": 2,
        }
    else:
        config = load_config(str(config_path))

    if args.submissions: config["submissions_dir"] = args.submissions
    if args.rubric:      config["rubric_file"]     = args.rubric
    if args.output:      config["output_csv"]      = args.output

    submissions_dir = Path(config["submissions_dir"])
    if not submissions_dir.exists():
        print(f"[ERROR] Submissions directory not found: '{submissions_dir}'")
        sys.exit(1)

    rubric_items = []
    rubric_path  = Path(config.get("rubric_file", "./rubric.json"))
    if rubric_path.exists():
        rubric_items = load_rubric(str(rubric_path))
        print(f"Rubric loaded: '{rubric_path}'")
    else:
        print(f"[INFO] No rubric file at '{rubric_path}' — only compile flag recorded.")

    results = grade_all(config, rubric_items)

    if results:
        compiles = sum(1 for r in results if r["Compiles"] == "Y")
        print(f"Summary: {compiles}/{len(results)} files compiled successfully.")
        if rubric_items:
            avg = sum(r.get("Total_Score", 0) for r in results) / len(results)
            print(f"Average score: {avg:.1f} / {sum(i.get('max_marks',0) for i in rubric_items)}")

    export_csv(results, config["output_csv"], rubric_items)


if __name__ == "__main__":
    main()
