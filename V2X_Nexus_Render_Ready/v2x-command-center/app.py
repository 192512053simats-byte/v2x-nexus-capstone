"""Flask application for the local V2X Research Command Center."""
from __future__ import annotations
import os
from pathlib import Path
from flask import Flask, jsonify, render_template, request
from engine import run_experiment
from ai_model import model_description

ROOT = Path(__file__).resolve().parent
TRACE_PATH = ROOT / "data" / "sumo_trace.json"
app = Flask(__name__)
app.json.sort_keys = False
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "traffic": "SUMO trace available" if TRACE_PATH.is_file() else "synthetic traffic ready",
        "sumo_trace_available": TRACE_PATH.is_file(),
        "network": "simplified Python V2X network model (not ns-3)",
        "ai": model_description(),
    })


@app.post("/api/run")
def run():
    raw = request.get_json(silent=True)
    if raw is None or not isinstance(raw, dict):
        return jsonify({"error": "Send a JSON object with scenario settings."}), 400
    try:
        return jsonify(run_experiment(raw, str(TRACE_PATH) if TRACE_PATH.is_file() else None))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        return jsonify({"error": str(exc)}), 400


if __name__ == "__main__":
    # Local-only by default. Flask's dev server isn't production deployment.
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="127.0.0.1", port=port, debug=False)
