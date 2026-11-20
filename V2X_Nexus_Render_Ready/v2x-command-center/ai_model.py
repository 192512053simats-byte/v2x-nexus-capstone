"""Small, explainable ML message scheduler trained on explicitly synthetic labels."""
from __future__ import annotations
import random
from functools import lru_cache

FEATURE_NAMES = ("hazard_flag", "severity", "proximity", "age", "remaining_deadline", "congestion")


def features(packet: dict, tick: int, congestion: float) -> list[float]:
    hazard = packet["kind"] == "hazard"
    return [
        1.0 if hazard else 0.0,
        float(packet["severity"] if hazard else 0),
        1.0 - min(1.0, float(packet["distance"]) / 650.0),
        min(1.0, (tick - packet["created"]) / 10.0),
        max(0.0, min(1.0, (packet["deadline"] - tick) / 12.0)),
        float(congestion),
    ]


@lru_cache(maxsize=1)
def get_model():
    """Supervised RF with *generated rule labels*, not external real-world training data."""
    try:
        from sklearn.ensemble import RandomForestClassifier
    except ImportError:
        return None
    rand = random.Random(1177)
    samples, labels = [], []
    for _ in range(2600):
        hazard = 1 if rand.random() < 0.43 else 0
        severity = rand.randint(1, 5) if hazard else 0
        proximity = rand.random()
        age = rand.random()
        remaining = rand.random()
        congestion = rand.random()
        row = [hazard, severity, proximity, age, remaining, congestion]
        # Teachers are transparent synthetic policy labels. This is a research
        # prototype, not evidence of a model trained on real roadway data.
        policy_score = (
            0.55 * hazard + 0.065 * severity + 0.16 * proximity
            + 0.13 * age + 0.15 * (1 - remaining) + 0.08 * congestion
        )
        threshold = 0.71 + rand.uniform(-0.10, 0.10)
        samples.append(row)
        labels.append(int(policy_score > threshold))
    model = RandomForestClassifier(
        n_estimators=64, max_depth=9, min_samples_leaf=4,
        random_state=1177, n_jobs=1
    )
    model.fit(samples, labels)
    return model


def score_queue(queue: list[dict], tick: int, congestion: float) -> list[float]:
    if not queue:
        return []
    rows = [features(p, tick, congestion) for p in queue]
    model = get_model()
    if model is not None:
        probabilities = model.predict_proba(rows)
        positive_index = list(model.classes_).index(1)
        return [
            float(probabilities[i][positive_index])
            + (0.12 if packet["kind"] == "hazard" else 0)
            + 0.04 * min(1, (tick - packet["created"]) / 8)
            for i, packet in enumerate(queue)
        ]
    # Clear fallback when scikit-learn is absent.
    return [
        (0.55 if p["kind"] == "hazard" else 0)
        + 0.075 * p["severity"]
        + 0.12 * (1 - min(1, p["distance"] / 650))
        + 0.07 * min(1, (tick - p["created"]) / 8)
        for p in queue
    ]


def model_description() -> dict:
    return {
        "name": "Synthetic-label Random Forest" if get_model() is not None else "Transparent heuristic fallback",
        "kind": "supervised-synthetic" if get_model() is not None else "heuristic",
        "features": list(FEATURE_NAMES),
        "disclaimer": "Trained using generated rule-based labels, not validated on real V2X datasets."
    }
