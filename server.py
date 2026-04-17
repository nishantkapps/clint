#!/usr/bin/env python3
"""
server.py — C-Lab Autograder local companion server

Runs on http://localhost:5001 and lets the GitHub Pages UI
trigger the grader, stream live progress, and fetch results.

Usage:
    python3 server.py
    python3 server.py --port 5001 --config config.json
"""

import argparse
import csv
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from flask import Flask, Response, jsonify, request, stream_with_context
from flask_cors import CORS

# ── App setup ─────────────────────────────────────────────────────────────────

app = Flask(__name__)
CORS(app, origins="*")  # allow GitHub Pages and localhost to call this

DEFAULT_CONFIG = "config.json"
BASE_DIR = Path(__file__).parent

# ── Grader run state ──────────────────────────────────────────────────────────

_run_lock = threading.Lock()
_run_state = {
    "running": False,
    "log":     [],        # list of log line strings
    "done":    False,
    "error":   None,
    "summary": {},
}


def _reset_state():
    _run_state["running"] = False
    _run_state["log"] = []
    _run_state["done"] = False
    _run_state["error"] = None
    _run_state["summary"] = {}


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/api/ping")
def ping():
    """Health check — lets the UI confirm the server is running."""
    return jsonify({"ok": True, "message": "C-Lab grader server is running."})


@app.route("/api/config", methods=["GET"])
def get_config():
    """Return current config so the UI can show paths."""
    cfg_path = BASE_DIR / request.args.get("config", DEFAULT_CONFIG)
    if cfg_path.exists():
        with open(cfg_path) as f:
            return jsonify(json.load(f))
    return jsonify({"error": "config.json not found"}), 404


@app.route("/api/config", methods=["POST"])
def save_config():
    """Update config.json from the UI."""
    data = request.get_json(force=True)
    cfg_path = BASE_DIR / DEFAULT_CONFIG
    # Preserve any keys already in the file that the UI doesn't know about
    existing = {}
    if cfg_path.exists():
        with open(cfg_path) as f:
            existing = json.load(f)
    existing.update(data)
    with open(cfg_path, "w") as f:
        json.dump(existing, f, indent=2)
    return jsonify({"ok": True})


@app.route("/api/run", methods=["POST"])
def run_grader():
    """
    Trigger the grader in a background thread and stream live output
    back to the browser using Server-Sent Events (SSE).

    The browser connects with EventSource('/api/run') — each graded
    file emits an event, and a final 'done' event closes the stream.
    """
    if _run_state["running"]:
        return jsonify({"error": "Grader is already running."}), 409

    with _run_lock:
        _reset_state()
        _run_state["running"] = True

    # Extract request data before entering the background thread
    req_cfg = request.get_json(force=True, silent=True) or {}

    def _run_in_background():
        try:
            cmd = [sys.executable, str(BASE_DIR / "grader.py")]
            if req_cfg.get("config"):
                cmd += ["--config", req_cfg["config"]]
            if req_cfg.get("submissions"):
                cmd += ["--submissions", req_cfg["submissions"]]
            if req_cfg.get("rubric"):
                cmd += ["--rubric", req_cfg["rubric"]]
            if req_cfg.get("output"):
                cmd += ["--output", req_cfg["output"]]

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(BASE_DIR),
            )
            for line in proc.stdout:
                line = line.rstrip("\n")
                _run_state["log"].append(line)
            proc.wait()
            _run_state["done"] = True
            _run_state["running"] = False

            # Parse summary line
            for line in _run_state["log"]:
                if line.startswith("Summary:"):
                    _run_state["summary"]["text"] = line
                if line.startswith("Results written to:"):
                    _run_state["summary"]["output"] = line.split(":", 1)[1].strip()

        except Exception as e:
            _run_state["error"] = str(e)
            _run_state["done"] = True
            _run_state["running"] = False

    thread = threading.Thread(target=_run_in_background, daemon=True)
    thread.start()
    return jsonify({"ok": True, "message": "Grader started."})


@app.route("/api/stream")
def stream_log():
    """
    SSE endpoint — browser connects here after POST /api/run
    and receives log lines as they appear.
    """
    def generate():
        sent = 0
        while True:
            lines = _run_state["log"]
            while sent < len(lines):
                line = lines[sent]
                yield f"data: {json.dumps({'line': line})}\n\n"
                sent += 1

            if _run_state["done"]:
                summary = _run_state.get("summary", {})
                yield f"data: {json.dumps({'done': True, 'summary': summary, 'error': _run_state.get('error')})}\n\n"
                break

            time.sleep(0.15)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.route("/api/rubric")
def get_rubric():
    """Return rubric items so the UI can display a legend."""
    cfg_path = BASE_DIR / DEFAULT_CONFIG
    rubric_file = "./rubric.json"
    if cfg_path.exists():
        with open(cfg_path) as f:
            rubric_file = json.load(f).get("rubric_file", rubric_file)
    rubric_path = BASE_DIR / rubric_file
    if not rubric_path.exists():
        return jsonify({"items": []})
    with open(rubric_path) as f:
        data = json.load(f)
    return jsonify({"lab": data.get("lab", ""), "items": data.get("items", [])})


@app.route("/api/results")
def get_results():
    """Return the results CSV as JSON rows."""
    cfg_path = BASE_DIR / DEFAULT_CONFIG
    output_csv = "./results.csv"

    if cfg_path.exists():
        with open(cfg_path) as f:
            cfg = json.load(f)
            output_csv = cfg.get("output_csv", output_csv)

    csv_path = BASE_DIR / output_csv
    if not csv_path.exists():
        return jsonify({"error": "results.csv not found — run the grader first."}), 404

    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        for row in reader:
            rows.append(dict(row))

    return jsonify({"headers": headers, "rows": rows})


@app.route("/api/status")
def status():
    """Return current run state."""
    return jsonify({
        "running": _run_state["running"],
        "done":    _run_state["done"],
        "error":   _run_state["error"],
        "summary": _run_state["summary"],
        "log_lines": len(_run_state["log"]),
    })


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="C-Lab grader companion server")
    parser.add_argument("--port",   type=int, default=5001, help="Port to listen on (default 5001)")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="Path to config.json")
    args = parser.parse_args()

    print("=" * 56)
    print("  C-Lab Autograder — Local Companion Server")
    print("=" * 56)
    print(f"  Listening on:  http://localhost:{args.port}")
    print(f"  Config file:   {args.config}")
    print(f"  Submissions:   {BASE_DIR / 'submissions'}")
    print()
    print("  Keep this terminal open while using the web app.")
    print("  Press Ctrl+C to stop.")
    print("=" * 56)

    app.run(host="127.0.0.1", port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
