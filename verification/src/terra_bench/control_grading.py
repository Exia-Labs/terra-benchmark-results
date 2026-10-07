"""Frozen qualitative rubric; no automatic keyword-based correct-refusal score."""

from .common import Blocked, digest, read, timestamp


def assess_control(expected, snapshot, folder, deadline):
    finals = [
        e
        for e in snapshot.get("events", [])
        if e.get("event_type") == "message.completed" and e.get("payload", {}).get("phase") != "commentary"
    ]
    if not finals:
        raise Blocked("No accepted final answer for qualitative review.")
    event = max(finals, key=lambda e: e["sequence"])
    text = event.get("payload", {}).get("content", "")
    if not text.strip() or timestamp(event["created_at"]) > deadline:
        raise Blocked("Qualitative answer is empty or arrived after deadline.")
    if snapshot.get("run", {}).get("status") != "completed":
        raise Blocked("Qualitative interaction did not complete.")
    review_path = folder / "adjudication.json"
    if not review_path.exists():
        return {
            "outcome": "needs-review",
            "finalAnswer": text,
            "computationCorrect": None,
            "answerFulfilled": None,
            "reasons": [
                "Awaiting operator review against the frozen qualitative rubric; not a computed GIS result."
            ],
            "cohort": "qualitative-control",
            "qualitativeKind": expected["kind"],
        }
    review = read(review_path)
    if (
        review.get("rubricFingerprint") != digest(expected)
        or review.get("finalEventId") != event["id"]
        or review.get("finalTextHash") != digest(text)
    ):
        raise Blocked("Qualitative adjudication does not match the frozen rubric and accepted answer.")
    criteria = review.get("criteria", {})
    if (
        set(criteria) != set(expected["criteria"])
        or not review.get("reviewer")
        or not review.get("evidenceReviewed")
    ):
        raise Blocked("Qualitative adjudication is incomplete.")
    for value in criteria.values():
        if type(value.get("satisfied")) is not bool or not str(value.get("explanation", "")).strip():
            raise Blocked("Each qualitative criterion needs an explicit decision and supporting explanation.")
    correct = all(v["satisfied"] for v in criteria.values())
    return {
        "outcome": ("expected-abstention" if expected["kind"] == "absence" else "control-pass")
        if correct
        else "fail",
        "finalAnswer": text,
        "computationCorrect": None,
        "answerFulfilled": correct,
        "reasons": [] if correct else [v["explanation"] for v in criteria.values() if not v["satisfied"]],
        "cohort": "qualitative-control",
        "qualitativeKind": expected["kind"],
        "adjudication": review,
        "qualification": "Operator-adjudicated, not blinded. Reported separately from exact computed/map results.",
    }
