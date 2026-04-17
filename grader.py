#!/usr/bin/env python3
"""
grader.py — C-Lab Autograder (local runner)

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


# ── Config ────────────────────────────────────────────────────────────────────

DEFAULT_CONFIG = "config.json"


def load_config(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def load_rubric(path: str) -> list[dict]:
    """Load rubric items from a rubric.json saved by the web editor."""
    with open(path) as f:
        data = json.load(f)
    return data.get("items", [])


# ── Student ID extraction ─────────────────────────────────────────────────────

def extract_student_id(filename: str, strategy: str, regex_pattern: str = None) -> str:
    """
    Extract student ID from a .c filename (without extension).

    Strategies:
      before_first_underscore  →  "2025A5PS0838H_lab1"  →  "2025A5PS0838H"
      after_last_underscore    →  "lab1_2025A5PS0838H"  →  "2025A5PS0838H"
      whole_filename           →  "2025A5PS0838H"       →  "2025A5PS0838H"
      regex                    →  first capture group of regex_pattern
    """
    stem = Path(filename).stem  # strip .c extension

    if strategy == "before_first_underscore":
        return stem.split("_")[0]

    if strategy == "after_last_underscore":
        return stem.rsplit("_", 1)[-1]

    if strategy == "whole_filename":
        return stem

    if strategy == "regex":
        pattern = regex_pattern or r"^([^_]+)"
        m = re.match(pattern, stem)
        if m:
            return m.group(1)
        return stem

    # fallback
    return stem


# ── Compiler ──────────────────────────────────────────────────────────────────

def compile_c_file(c_file: Path, compile_timeout: int) -> tuple[bool, str, Path | None]:
    """
    Compile a .c file using gcc.

    Returns:
        (success: bool, error_output: str, binary_path: Path | None)

    The binary is written to a temp directory.  The caller is responsible
    for cleaning up the temp dir.
    """
    tmp_dir = tempfile.mkdtemp(prefix="clint_")
    binary = Path(tmp_dir) / "a.out"

    try:
        result = subprocess.run(
            ["gcc", str(c_file), "-o", str(binary), "-w", "-lm"],
            capture_output=True,
            text=True,
            timeout=compile_timeout,
        )
        if result.returncode == 0:
            return True, "", binary
        else:
            return False, result.stderr.strip(), None
    except subprocess.TimeoutExpired:
        return False, "Compilation timed out.", None
    except FileNotFoundError:
        print("\n[ERROR] gcc not found. Please install gcc:\n  sudo apt-get install gcc\n")
        sys.exit(1)


# ── Main grading pipeline ─────────────────────────────────────────────────────

def grade_all(config: dict, rubric_items: list[dict]) -> list[dict]:
    submissions_dir = Path(config["submissions_dir"])
    id_cfg = config.get("id_extraction", {})
    strategy = id_cfg.get("strategy", "before_first_underscore")
    regex_pat = id_cfg.get("regex")
    compile_timeout = config.get("compile_timeout_seconds", 10)

    c_files = sorted(submissions_dir.glob("**/*.c"))

    if not c_files:
        print(f"[WARN] No .c files found in '{submissions_dir}'")
        return []

    print(f"Found {len(c_files)} submission(s) in '{submissions_dir}'\n")

    results = []

    for i, c_file in enumerate(c_files, 1):
        student_id = extract_student_id(c_file.name, strategy, regex_pat)
        print(f"[{i:>3}/{len(c_files)}] {student_id:<25} ", end="", flush=True)

        compiles, compile_error, binary = compile_c_file(c_file, compile_timeout)

        if compiles:
            print("✓ Compiles", flush=True)
        else:
            short_err = compile_error.splitlines()[0] if compile_error else "unknown error"
            print(f"✗ Compile error — {short_err}", flush=True)

        row = {
            "Student_ID": student_id,
            "File": c_file.name,
            "Compiles": "Y" if compiles else "N",
            "Compile_Error": "" if compiles else compile_error,
        }

        # Placeholder score columns for each rubric item (0 until grading engine is added)
        for item in rubric_items:
            row[item["name"]] = ""

        if rubric_items:
            row["Total_Score"] = ""
        row["Feedback_Summary"] = ""
        row["Feedback_Detail"] = ""

        results.append(row)

        # clean up binary
        if binary and binary.exists():
            binary.unlink()
            binary.parent.rmdir()

    return results


# ── CSV export ────────────────────────────────────────────────────────────────

def export_csv(results: list[dict], output_path: str, rubric_items: list[dict]):
    if not results:
        print("[WARN] No results to write.")
        return

    fixed_cols = ["Student_ID", "File", "Compiles", "Compile_Error"]
    rubric_cols = [item["name"] for item in rubric_items]
    trailing_cols = ["Total_Score", "Feedback_Summary", "Feedback_Detail"] if rubric_items else []
    fieldnames = fixed_cols + rubric_cols + trailing_cols

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)

    print(f"\nResults written to: {output_path}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="C-Lab Autograder — local GCC-based grader"
    )
    parser.add_argument("--config",      default=DEFAULT_CONFIG, help="Path to config.json")
    parser.add_argument("--submissions", help="Override submissions directory")
    parser.add_argument("--rubric",      help="Override rubric JSON file")
    parser.add_argument("--output",      help="Override output CSV path")
    args = parser.parse_args()

    # Load config
    if not Path(args.config).exists():
        print(f"[WARN] Config file '{args.config}' not found — using defaults.")
        config = {
            "submissions_dir": "./submissions",
            "rubric_file": "./rubric.json",
            "output_csv": "./results.csv",
            "id_extraction": {"strategy": "before_first_underscore"},
            "compile_timeout_seconds": 10,
            "run_timeout_seconds": 2,
        }
    else:
        config = load_config(args.config)

    # CLI overrides
    if args.submissions:
        config["submissions_dir"] = args.submissions
    if args.rubric:
        config["rubric_file"] = args.rubric
    if args.output:
        config["output_csv"] = args.output

    # Validate submissions dir
    submissions_dir = Path(config["submissions_dir"])
    if not submissions_dir.exists():
        print(f"[ERROR] Submissions directory not found: '{submissions_dir}'")
        print("  Create it and drop student .c files inside, then re-run.")
        sys.exit(1)

    # Load rubric (optional — grader works without it, just adds compile flag)
    rubric_items = []
    rubric_path = Path(config["rubric_file"])
    if rubric_path.exists():
        rubric_items = load_rubric(str(rubric_path))
        print(f"Rubric loaded: {len(rubric_items)} item(s) from '{rubric_path}'")
    else:
        print(f"[INFO] No rubric file found at '{rubric_path}' — only compile flag will be recorded.")

    print(f"ID extraction strategy: {config.get('id_extraction', {}).get('strategy', 'before_first_underscore')}\n")

    # Grade
    results = grade_all(config, rubric_items)

    # Summary
    if results:
        compiles_count = sum(1 for r in results if r["Compiles"] == "Y")
        print(f"\nSummary: {compiles_count}/{len(results)} files compiled successfully.")

    # Export
    export_csv(results, config["output_csv"], rubric_items)


if __name__ == "__main__":
    main()
