#!/usr/bin/env python3
"""
grader.py — C-Lab Autograder (local runner)

Two modes (run separately):
  compile-run  Compile each .c, run binary, compare stdout to expected output
  rubric       Score rubric items (static / llm / test) per submission

Usage:
    python3 grader.py --mode compile-run
    python3 grader.py --mode rubric
    python3 grader.py --config config.json --mode compile-run
"""

from __future__ import annotations

import argparse
import csv
import difflib
import json
import os
import re
import subprocess
import sys
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


# ── Compile & run ─────────────────────────────────────────────────────────────

def _build_output_dir(config: dict) -> Path:
    """Directory where gcc writes executables (kept after grading)."""
    return Path(config.get("build_output_dir", "./output")).expanduser().resolve()


def compile_c_file(
    c_file: Path,
    compile_timeout: int,
    config: dict,
) -> tuple[bool, str, Path | None]:
    """
    Run gcc with a named executable matching the source stem:

        gcc <absolute_path_to/IDNumber.c> -o <build_output_dir>/IDNumber -w -lm

    Example: submissions/2025A5PS0838H.c → output/2025A5PS0838H (no .c extension).
    The binary is left on disk under build_output_dir for inspection.
    """
    build_dir = _build_output_dir(config)
    build_dir.mkdir(parents=True, exist_ok=True)

    src = c_file.resolve()
    binary = build_dir / c_file.stem
    if binary.exists():
        binary.unlink()

    try:
        result = subprocess.run(
            ["gcc", str(src), "-o", str(binary), "-w", "-lm"],
            capture_output=True,
            text=True,
            timeout=compile_timeout,
        )
        if result.returncode == 0:
            try:
                os.chmod(binary, 0o755)
            except OSError:
                pass
            return True, "", binary
        if binary.exists():
            binary.unlink()
        return False, result.stderr.strip(), None
    except subprocess.TimeoutExpired:
        if binary.exists():
            binary.unlink()
        return False, "Compilation timed out.", None
    except FileNotFoundError:
        print("\n[ERROR] gcc not found. Install with: sudo apt-get install gcc\n")
        sys.exit(1)


def run_binary(binary: Path, stdin_text: str, run_timeout: int) -> tuple[str, str, str | None]:
    """Returns (stdout, stderr, error_message_or_None)."""
    try:
        result = subprocess.run(
            [str(binary)],
            input=stdin_text or "",
            capture_output=True, text=True, timeout=run_timeout,
        )
        return result.stdout or "", result.stderr or "", None
    except subprocess.TimeoutExpired:
        return "", "", "Run timed out."
    except Exception as e:
        return "", "", str(e)


def normalize_output(s: str) -> str:
    """Normalize for comparison: CRLF → LF, strip trailing blank lines, rstrip each line."""
    if s is None:
        return ""
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in s.split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def score_execution_match(actual: str, expected: str, max_marks: int) -> tuple[int, float, str]:
    """
    Full marks if normalized strings match exactly.
    Otherwise partial marks proportional to SequenceMatcher ratio (0–1).
    """
    if max_marks <= 0:
        return 0, 0.0, "Execution marks set to 0."

    na = normalize_output(actual)
    ne = normalize_output(expected)

    if not ne.strip():
        return 0, 0.0, "No expected output configured — execution not scored."

    if na == ne:
        return max_marks, 100.0, "Exact match (after normalization)."

    ratio = difflib.SequenceMatcher(None, na, ne).ratio()
    marks = max(0, min(max_marks, round(max_marks * ratio)))
    pct = round(ratio * 100, 1)
    return marks, pct, f"Similarity {pct}% vs expected (partial credit)."


# ── Static / LLM / test scorers (unchanged logic) ─────────────────────────────

def score_static(item: dict, code: str) -> tuple[int, str]:
    max_marks = item.get("max_marks", 0)
    patterns = item.get("patterns", [])

    if not patterns:
        words = re.findall(r"[\w\.]+", item.get("condition", ""))
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

    matched, missed = [], []
    for pat in patterns:
        try:
            if re.search(pat, code, re.IGNORECASE | re.MULTILINE):
                matched.append(pat)
            else:
                missed.append(pat)
        except re.error:
            if pat.lower() in code.lower():
                matched.append(pat)
            else:
                missed.append(pat)

    if len(matched) == len(patterns):
        return max_marks, f"All {len(patterns)} pattern(s) matched."
    if matched:
        marks = round(max_marks * len(matched) / len(patterns))
        return marks, f"{len(matched)}/{len(patterns)} patterns matched. Missing: {', '.join(missed[:3])}."
    return 0, f"No patterns matched. Expected: {', '.join(patterns[:3])}."


def score_llm(item: dict, code: str, llm_config: dict) -> tuple[int, str]:
    try:
        import litellm
    except ImportError:
        return 0, "litellm not installed — run: pip install litellm"

    model = llm_config.get("llm_model", "claude-3-haiku-20240307")
    api_key = llm_config.get("llm_api_key", "")
    max_marks = item.get("max_marks", 0)

    if not api_key:
        return 0, "No LLM API key configured — set llm_api_key in config.json."

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
        raw = re.sub(r"^```[a-z]*\n?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        result = json.loads(raw)
        marks = max(0, min(int(result.get("marks", 0)), max_marks))
        return marks, result.get("reason", "")
    except json.JSONDecodeError as e:
        return 0, f"LLM returned invalid JSON: {e}"
    except Exception as e:
        return 0, f"LLM error: {e}"


def score_test(item: dict, binary: Path, tests_dir: Path, run_timeout: int) -> tuple[int, str]:
    max_marks = item.get("max_marks", 0)
    test_key = item.get("test_case", "test_1")
    test_path = tests_dir / test_key

    if not test_path.exists():
        return 0, f"Test folder not found: {test_path}"

    inputs = sorted(test_path.glob("input_*.txt"))
    if not inputs:
        return 0, f"No input_*.txt files in {test_path}"

    passed, details = 0, []
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

    marks = round(max_marks * passed / total)
    return marks, f"{passed}/{total} tests passed. {' '.join(details)}."


# ── Phase: compile + run + execution score ────────────────────────────────────

def compile_run_file(c_file: Path, config: dict) -> dict:
    compile_timeout = config.get("compile_timeout_seconds", 10)
    run_timeout = config.get("run_timeout_seconds", 2)
    stdin_text = config.get("stdin_for_run", "") or ""
    expected = config.get("expected_output", "") or ""
    exec_max = int(config.get("execution_max_marks", 10) or 10)
    compile_max = int(config.get("compilation_max_marks", 5) or 5)

    compiles, compile_error, binary = compile_c_file(c_file, compile_timeout, config)
    compilation_marks = compile_max if compiles else 0

    stdout, stderr, run_err = "", "", None
    exec_marks, match_pct, exec_note = 0, 0.0, ""

    if compiles and binary:
        stdout, stderr, run_err = run_binary(binary, stdin_text, run_timeout)
        if run_err:
            exec_note = run_err
            exec_marks, match_pct = 0, 0.0
        else:
            exec_marks, match_pct, exec_note = score_execution_match(stdout, expected, exec_max)

    return {
        "compiles": compiles,
        "compile_error": compile_error,
        "compilation_marks": compilation_marks,
        "compilation_max": compile_max,
        "stdout": stdout,
        "stderr": stderr,
        "run_error": run_err or "",
        "execution_marks": exec_marks,
        "execution_max": exec_max,
        "match_pct": match_pct,
        "execution_note": exec_note,
    }


def compile_run_all(config: dict) -> list[dict]:
    submissions_dir = Path(config["submissions_dir"])
    id_cfg = config.get("id_extraction", {})
    strategy = id_cfg.get("strategy", "before_first_underscore")
    regex_pat = id_cfg.get("regex")

    c_files = sorted(submissions_dir.glob("**/*.c"))
    if not c_files:
        print(f"[WARN] No .c files found in '{submissions_dir}'")
        return []

    exec_max = int(config.get("execution_max_marks", 10) or 10)
    compile_max = int(config.get("compilation_max_marks", 5) or 5)
    build_dir = _build_output_dir(config)
    print(f"Found {len(c_files)} submission(s) in '{submissions_dir}'")
    print(f"gcc output dir: {build_dir}  (executable name = .c stem, e.g. IDNumber.c → IDNumber)")
    print(f"Compile & run phase — compilation max: {compile_max}, execution max: {exec_max}")
    print()

    rows = []
    for idx, c_file in enumerate(c_files, 1):
        sid = extract_student_id(c_file.name, strategy, regex_pat)
        print(f"[{idx:>3}/{len(c_files)}] {sid:<25} ", end="", flush=True)

        r = compile_run_file(c_file, config)
        cm, cx = r["compilation_marks"], r["compilation_max"]
        bin_rel = ""
        if r["compiles"] and (build_dir / c_file.stem).exists():
            try:
                bin_rel = str((build_dir / c_file.stem).relative_to(Path.cwd()))
            except ValueError:
                bin_rel = str(build_dir / c_file.stem)
        if r["compiles"] and r["run_error"]:
            flag = f"✓ Compiles  ✗ Run error  compile {cm}/{cx}"
        elif r["compiles"]:
            flag = (
                f"✓ Compiles  compile {cm}/{cx}  "
                f"exec {r['execution_marks']}/{exec_max} ({r['match_pct']}% match)"
            )
        else:
            flag = f"✗ No compile  compile {cm}/{cx}"
        print(flag, flush=True)

        rows.append({
            "Student_ID": sid,
            "File": c_file.name,
            "Compiles": "Y" if r["compiles"] else "N",
            "Compile_Error": "" if r["compiles"] else r["compile_error"],
            "Compilation_Marks": r["compilation_marks"],
            "Compilation_Max": r["compilation_max"],
            "Binary_Path": bin_rel,
            "Stdout": r["stdout"],
            "Stderr": r["stderr"],
            "Run_Error": r["run_error"] or "",
            "Execution_Marks": r["execution_marks"] if r["compiles"] and not r["run_error"] else "",
            "Execution_Max": exec_max,
            "Match_Pct": f"{r['match_pct']}%" if r["compiles"] and not r["run_error"] else "",
            "Execution_Note": r["execution_note"],
        })
    return rows


def export_compile_csv(results: list[dict], output_path: str):
    if not results:
        print("[WARN] No compile-run results to write.")
        return
    fieldnames = [
        "Student_ID", "File", "Compiles", "Compile_Error",
        "Compilation_Marks", "Compilation_Max", "Binary_Path",
        "Stdout", "Stderr", "Run_Error",
        "Execution_Marks", "Execution_Max", "Match_Pct", "Execution_Note",
    ]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(results)
    print(f"\nCompile & execution report written to: {output_path}")


# ── Phase: rubric only ────────────────────────────────────────────────────────

def grade_rubric_file(c_file: Path, rubric_items: list[dict], config: dict) -> dict:
    compile_timeout = config.get("compile_timeout_seconds", 10)
    run_timeout = config.get("run_timeout_seconds", 2)
    tests_dir = Path(config.get("tests_dir", "./test_cases"))
    llm_config = config

    compiles, compile_error, binary = compile_c_file(c_file, compile_timeout, config)
    code = c_file.read_text(errors="replace")

    scores, feedback = {}, []
    for n, item in enumerate(rubric_items, 1):
        col_key = f"Rubric_{n}"
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

        scores[col_key] = marks
        feedback.append(f"Rubric {n} — {item['name']} ({marks}/{max_marks}): {reason}")

    total = sum(scores.values())

    return {
        "compiles": compiles,
        "compile_error": compile_error,
        "scores": scores,
        "total": total,
        "feedback": "\n".join(feedback),
    }


def grade_rubric_all(config: dict, rubric_items: list[dict]) -> list[dict]:
    submissions_dir = Path(config["submissions_dir"])
    id_cfg = config.get("id_extraction", {})
    strategy = id_cfg.get("strategy", "before_first_underscore")
    regex_pat = id_cfg.get("regex")

    c_files = sorted(submissions_dir.glob("**/*.c"))
    if not c_files:
        print(f"[WARN] No .c files found in '{submissions_dir}'")
        return []

    print(f"Found {len(c_files)} submission(s) in '{submissions_dir}'")
    print(f"Rubric phase — {len(rubric_items)} item(s)")
    print()

    rows = []
    max_total = sum(i.get("max_marks", 0) for i in rubric_items)
    for idx, c_file in enumerate(c_files, 1):
        sid = extract_student_id(c_file.name, strategy, regex_pat)
        print(f"[{idx:>3}/{len(c_files)}] {sid:<25} ", end="", flush=True)

        r = grade_rubric_file(c_file, rubric_items, config)
        flag = "✓ Compiles" if r["compiles"] else "✗ No compile"
        print(f"{flag}  rubric {r['total']}/{max_total}", flush=True)

        row = {
            "Student_ID": sid,
            "File": c_file.name,
        }
        row.update(r["scores"])
        if rubric_items:
            row["Total_Score"] = r["total"]
            row["Max_Score"] = max_total
        row["Feedback"] = r["feedback"]
        rows.append(row)
    return rows


def export_rubric_csv(results: list[dict], output_path: str, rubric_items: list[dict]):
    if not results:
        print("[WARN] No rubric results to write.")
        return
    fixed = ["Student_ID", "File"]
    rubric_cols = [f"Rubric_{n}" for n in range(1, len(rubric_items) + 1)]
    trailing = (["Total_Score", "Max_Score", "Feedback"] if rubric_items else ["Feedback"])
    fieldnames = fixed + rubric_cols + trailing
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(results)
    print(f"\nRubric report written to: {output_path}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="C-Lab Autograder")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--submissions", help="Override submissions directory")
    parser.add_argument("--rubric", help="Override rubric JSON file")
    parser.add_argument(
        "--mode",
        choices=("compile-run", "rubric"),
        required=True,
        help="compile-run: compile + execute + output match. rubric: rubric items only.",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"[ERROR] Config not found: {args.config}")
        sys.exit(1)

    config = load_config(str(config_path))
    if args.submissions:
        config["submissions_dir"] = args.submissions
    if args.rubric:
        config["rubric_file"] = args.rubric

    submissions_dir = Path(config["submissions_dir"])
    if not submissions_dir.exists():
        print(f"[ERROR] Submissions directory not found: '{submissions_dir}'")
        sys.exit(1)

    out_compile = config.get("output_compile_csv", "./results_compile.csv")
    out_rubric = config.get("output_rubric_csv", "./results_rubric.csv")

    if args.mode == "compile-run":
        results = compile_run_all(config)
        if results:
            ok = sum(1 for r in results if r["Compiles"] == "Y")
            print(f"Summary: {ok}/{len(results)} compiled successfully.")
        export_compile_csv(results, out_compile)

    else:  # rubric
        rubric_path = Path(config.get("rubric_file", "./rubric.json"))
        if not rubric_path.exists():
            print(f"[ERROR] Rubric file not found: {rubric_path}")
            sys.exit(1)
        rubric_items = load_rubric(str(rubric_path))
        print(f"Rubric loaded: '{rubric_path}'")
        results = grade_rubric_all(config, rubric_items)
        if results and rubric_items:
            avg = sum(r.get("Total_Score", 0) for r in results) / len(results)
            mx = sum(i.get("max_marks", 0) for i in rubric_items)
            print(f"Average rubric score: {avg:.1f} / {mx}")
        export_rubric_csv(results, out_rubric, rubric_items)


if __name__ == "__main__":
    main()
