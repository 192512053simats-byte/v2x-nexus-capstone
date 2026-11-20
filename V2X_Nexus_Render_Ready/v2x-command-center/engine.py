"""Reproducible, simplified V2X communication + cooperative perception laboratory.

The traffic and radio layers here are explicitly APPROXIMATIONS. Nothing in
this file is a genuine 3GPP/6G radio stack or packet-level ns-3 model.
"""
from __future__ import annotations
import hashlib
import math
import random
from typing import Any
from ai_model import model_description, score_queue

W, H = 960, 540
EVENT_LABELS = ["Road obstruction", "Sudden braking", "Pedestrian crossing", "Disabled vehicle", "Low visibility", "Debris detected"]
EVENT_TYPES = ["obstruction", "braking", "pedestrian", "breakdown", "visibility", "debris"]


def bound_float(value: Any, minimum: float, maximum: float, default: float) -> float:
    try:
        x = float(value)
        return max(minimum, min(maximum, x)) if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def bound_int(value: Any, minimum: int, maximum: int, default: int) -> int:
    try:
        return max(minimum, min(maximum, int(value)))
    except (TypeError, ValueError):
        return default


def normalize_config(raw: dict | None) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    scenario = str(raw.get("scenario", "intersection"))
    if scenario not in ("intersection", "urban", "highway"):
        scenario = "intersection"
    return {
        "scenario": scenario,
        "vehicles": bound_int(raw.get("vehicles"), 8, 54, 24),
        "load": round(bound_float(raw.get("load"), 0.0, 1.0, 0.52), 2),
        "capacity": bound_int(raw.get("capacity"), 4, 24, 11),
        "duration": bound_int(raw.get("duration"), 24, 72, 48),
        "seed": bound_int(raw.get("seed"), 1, 999999, 42),
        "source": "trace" if raw.get("source") == "trace" else "synthetic",
    }


def unit_hash(*parts) -> float:
    digest = hashlib.blake2s("|".join(map(str, parts)).encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big") / (2 ** 64)


def make_vehicle_trace(config: dict, external: list | None = None) -> list[list[dict]]:
    if external is not None:
        # Already normalized by load_trace(), frame count may be shorter.
        return external
    rand = random.Random(config["seed"])
    specs = []
    for i in range(config["vehicles"]):
        lane = i % (4 if config["scenario"] == "intersection" else 6)
        direction = 1 if lane % 2 == 0 else -1
        speed = round(rand.uniform(32, 66 if config["scenario"] == "highway" else 48), 1)
        phase = rand.uniform(0, 1060)
        specs.append((lane, direction, speed, phase))
    frames = []
    for t in range(config["duration"]):
        vehicles = []
        for i, (lane, direction, speed, phase) in enumerate(specs):
            offset = (phase + (1 if direction == 1 else -1) * speed * 0.125 * t) % 1100
            coordinate = offset - 70
            if config["scenario"] == "intersection":
                if lane < 2:
                    x, y = coordinate, (252 if lane == 0 else 286)
                    angle = 0 if direction == 1 else 180
                else:
                    x, y = (461 if lane == 2 else 500), coordinate * 0.62
                    angle = 90 if direction == 1 else -90
            elif config["scenario"] == "highway":
                x, y = coordinate, [138, 192, 246, 300, 354, 408][lane]
                angle = 0 if direction == 1 else 180
            else:
                if lane < 4:
                    x, y = coordinate, [136, 166, 376, 406][lane]
                    angle = 0 if direction == 1 else 180
                else:
                    x, y = (316 if lane == 4 else 652), coordinate * 0.62
                    angle = 90 if direction == 1 else -90
            vehicles.append({
                "id": f"V{i + 1:02d}", "x": round(x, 1), "y": round(y, 1),
                "speed": speed, "angle": angle, "connected": True,
            })
        frames.append(vehicles)
    return frames


def dist(a: dict, b: dict) -> float:
    return math.hypot(a["x"] - b["x"], a["y"] - b["y"])


def generate_hazards(trace: list[list[dict]], config: dict) -> list[dict]:
    rand = random.Random(config["seed"] + 220)
    duration = len(trace)
    start_times = list(range(3, duration - 3, 9 if config["scenario"] == "highway" else 8))
    events = []
    for j, onset in enumerate(start_times):
        frame = trace[onset]
        if len(frame) < 3:
            continue
        visible_frame = [v for v in frame if 40 < v["x"] < 920 and 35 < v["y"] < 505]
        src = rand.choice(visible_frame or frame)
        center = {"x": src["x"], "y": src["y"]}
        ordered = sorted([v for v in frame if v["id"] != src["id"]], key=lambda v: dist(center, v))
        limit = min(len(ordered), max(5, config["vehicles"] // 3))
        targets = []
        for idx, v in enumerate(ordered[:limit]):
            distance = dist(center, v)
            # Include nearby and approaching connected vehicles. Local occlusion
            # is a synthetic visibility approximation, not an optical ray trace.
            direct = distance < 45 or rand.random() < 0.16
            targets.append({"id": v["id"], "distance": round(distance), "local_visible": direct})
        if targets:
            events.append({
                "id": f"H{j+1:02d}", "onset": onset,
                "until": min(duration - 1, onset + 7),
                "x": round(center["x"], 1), "y": round(center["y"], 1),
                "label": EVENT_LABELS[j % len(EVENT_LABELS)],
                "type": EVENT_TYPES[j % len(EVENT_TYPES)],
                "severity": rand.choice([3, 4, 4, 5]), "source": src["id"],
                "targets": targets,
            })
    return events


def make_packets(trace: list[list[dict]], hazards: list[dict], config: dict) -> list[list[dict]]:
    rand = random.Random(config["seed"] + 352)
    timeline = [[] for _ in range(len(trace))]
    sequence = 0
    for t, vehicles in enumerate(trace):
        # Routine CAM-like telemetry; a byte-size abstraction, not ETSI encoding.
        for i, v in enumerate(vehicles):
            if (i + t) % 2 != 0:
                continue
            peer = vehicles[(i + 1 + t % 3) % len(vehicles)]
            sequence += 1
            timeline[t].append({
                "id": f"M{sequence}", "kind": "telemetry", "from": v["id"],
                "to": peer["id"], "created": t, "deadline": t + 12,
                "severity": 0, "distance": dist(v, peer), "bytes": 180,
                "event_id": None,
            })
    for hazard in hazards:
        for target in hazard["targets"]:
            if target["local_visible"]:
                continue
            # Retransmission opportunities are identical for both algorithms.
            for retransmit in (0, 2, 4):
                t = hazard["onset"] + retransmit
                if t >= len(timeline):
                    break
                sequence += 1
                timeline[t].append({
                    "id": f"M{sequence}", "kind": "hazard",
                    "from": hazard["source"], "to": target["id"],
                    "created": t, "deadline": hazard["onset"] + 6,
                    "severity": hazard["severity"], "distance": target["distance"],
                    "bytes": 260, "event_id": hazard["id"],
                })
    for frame in timeline:
        rand.shuffle(frame)  # Mixed stream instead of an artificially sorted input.
    return timeline


def evaluate(packets: list[list[dict]], trace: list[list[dict]], hazards: list[dict], config: dict, algorithm: str) -> dict:
    queue = []
    stats = {"generated": 0, "sent": 0, "delivered": 0, "lost": 0, "expired": 0, "bytes_sent": 0,
             "safety_generated": 0, "safety_delivered": 0}
    known = set()
    local = {(h["id"], t["id"]) for h in hazards for t in h["targets"] if t["local_visible"]}
    blind = {(h["id"], t["id"]) for h in hazards for t in h["targets"] if not t["local_visible"]}
    total_pairs = len(local) + len(blind)
    hazards_map = {h["id"]: h for h in hazards}
    latencies = []
    safety_latencies = []
    series = {"tick": [], "latency": [], "queue": [], "awareness": [], "delivery": [], "channel": []}
    snapshots = []
    logs = []
    delivered_event_targets = set()
    for tick, frame in enumerate(trace):
        created = [p.copy() for p in packets[tick]]
        queue.extend(created)
        stats["generated"] += len(created)
        stats["safety_generated"] += sum(p["kind"] == "hazard" for p in created)
        active_queue = []
        for p in queue:
            if p["deadline"] < tick:
                stats["expired"] += 1
            else:
                active_queue.append(p)
        queue = active_queue
        raw_cap = config["capacity"]
        throughput = max(2, round(raw_cap * (1 - 0.42 * config["load"])))
        channel = throughput
        if algorithm == "ai" and queue:
            scores = score_queue(queue, tick, config["load"])
            queue = [q for _, q in sorted(zip(scores, queue), key=lambda it: it[0], reverse=True)]
        scheduled, queue = queue[:throughput], queue[throughput:]
        deliveries = []
        timed_delays = []
        for p in scheduled:
            stats["sent"] += 1
            stats["bytes_sent"] += p["bytes"]
            # Deterministic per-message channel outcomes => paired experiment.
            loss_chance = 0.025 + 0.16 * config["load"]
            was_lost = unit_hash(config["seed"], p["id"], "loss") < loss_chance
            if was_lost:
                stats["lost"] += 1
                deliveries.append({"from": p["from"], "to": p["to"], "kind": p["kind"], "status": "lost"})
                continue
            jitter = int(17 + unit_hash(config["seed"], p["id"], "jitter") * 67)
            delay = int((tick - p["created"]) * 100 + jitter + config["load"] * 46)
            timed_delays.append(delay)
            latencies.append(delay)
            stats["delivered"] += 1
            if p["kind"] == "hazard":
                stats["safety_delivered"] += 1
                safety_latencies.append(delay)
                hazard = hazards_map[p["event_id"]]
                arrival_ms = tick * 100 + jitter + config["load"] * 46
                if arrival_ms <= (hazard["onset"] + 6) * 100:
                    known.add((p["event_id"], p["to"]))
                    if (p["event_id"], p["to"]) not in delivered_event_targets:
                        delivered_event_targets.add((p["event_id"], p["to"]))
                        logs.append({
                            "tick": tick, "type": "success", "message": f"{p['to']} learned about {hazard['label'].lower()} via {p['from']}",
                            "label": "HAZARD RECEIVED"
                        })
            deliveries.append({"from": p["from"], "to": p["to"], "kind": p["kind"], "status": "delivered"})
        spawned = [h for h in hazards if h["onset"] == tick]
        for h in spawned:
            logs.append({"tick": tick, "type": "warning", "message": f"{h['label']} · severity {h['severity']}/5 · observed by {h['source']}", "label": "HAZARD DETECTED"})
        if tick == 0:
            logs.append({"tick": 0, "type": "info", "message": f"{algorithm.upper()} scheduler online · {len(frame)} connected vehicles", "label": "SCENARIO START"})
        current_awareness = 100 * (len(local) + len(known)) / total_pairs if total_pairs else 100
        series["tick"].append(round(tick * 0.1, 1))
        series["latency"].append(round(sum(timed_delays) / len(timed_delays), 1) if timed_delays else None)
        series["queue"].append(len(queue))
        series["awareness"].append(round(current_awareness, 1))
        series["delivery"].append(round(stats["delivered"] / stats["generated"] * 100, 1) if stats["generated"] else 0)
        series["channel"].append(channel)
        snapshots.append({
            "tick": tick, "time": round(tick * .1, 1), "vehicles": frame,
            "hazards": [{k: h[k] for k in ("id", "x", "y", "label", "severity", "source")} for h in hazards if h["onset"] <= tick <= h["until"]],
            "transmissions": deliveries[:18], "queue": len(queue), "delivered": stats["delivered"],
            "sent": stats["sent"], "generated": stats["generated"],
            "awareness": round(current_awareness, 1), "channel": channel,
        })
    stats["pending"] = len(queue)
    awareness_pct = 100 * (len(local) + len(known)) / total_pairs if total_pairs else 100.0
    metrics = {
        "latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else 0.0,
        "safety_latency_ms": round(sum(safety_latencies) / len(safety_latencies), 1) if safety_latencies else 0.0,
        "pdr_pct": round(100 * stats["delivered"] / stats["generated"], 1) if stats["generated"] else 0,
        "safety_pdr_pct": round(100 * stats["safety_delivered"] / stats["safety_generated"], 1) if stats["safety_generated"] else 0,
        "awareness_pct": round(awareness_pct, 1),
        "blindspot_reduction_pct": round(100 * len(known) / len(blind), 1) if blind else 0,
        "timely_hazards_pct": round(100 * len(known) / len(blind), 1) if blind else 0,
        "traffic_kb": round(stats["bytes_sent"] / 1024, 1),
        "hazards_known": len(known), "blind_pairs": len(blind),
        "local_known": len(local), "total_pairs": total_pairs,
        **stats,
    }
    logs.sort(key=lambda item: item["tick"])
    return {"metrics": metrics, "series": series, "snapshots": snapshots, "logs": logs[-40:]}


def load_trace(path: str, requested_duration: int) -> list[list[dict]]:
    """Read JSON array of frames created using tools/export_sumo_trace.py."""
    import json
    from pathlib import Path
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list) or len(raw) < 8:
        raise ValueError("SUMO trace must be a JSON array of at least 8 frames")
    parsed = []
    for frame in raw[:requested_duration]:
        if not isinstance(frame, list) or len(frame) < 3:
            raise ValueError("Each SUMO trace frame must contain at least 3 vehicles")
        vehicles = []
        for v in frame[:54]:
            vehicles.append({
                "id": str(v["id"])[:35],
                "x": round(bound_float(v.get("x"), -1000, 2000, 480), 1),
                "y": round(bound_float(v.get("y"), -1000, 2000, 270), 1),
                "speed": round(bound_float(v.get("speed"), 0, 180, 35), 1),
                "angle": bound_float(v.get("angle"), -360, 360, 0),
                "connected": True
            })
        parsed.append(vehicles)
    return parsed


def run_experiment(raw: dict | None, trace_path: str | None = None) -> dict:
    config = normalize_config(raw)
    if config["source"] == "trace":
        if not trace_path:
            raise ValueError("SUMO trace isn't available. Export a trace to data/sumo_trace.json first.")
        trace = load_trace(trace_path, config["duration"])
        config["duration"] = len(trace)
        config["vehicles"] = len(trace[0])
    else:
        trace = make_vehicle_trace(config)
    hazards = generate_hazards(trace, config)
    packets = make_packets(trace, hazards, config)
    fifo = evaluate(packets, trace, hazards, config, "fifo")
    ai = evaluate(packets, trace, hazards, config, "ai")
    return {
        "config": config, "meta": {"step_ms": 100, "synthetic_network": True,
                                    "message_model": "simplified V2X queues with fixed capacity, TTL and deterministic loss",
                                    "traffic_mode": "SUMO TraCI trace" if config["source"] == "trace" else "synthetic traffic"},
        "model": model_description(), "hazard_count": len(hazards),
        "results": {"fifo": fifo, "ai": ai},
    }
