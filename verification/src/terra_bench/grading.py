"""Offline deterministic grading; no calls to Terra, a model, or production processors."""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

import geopandas as gpd
import pandas as pd

from .common import Blocked, beneath, digest, read, sha, timestamp, write
from .fixtures import ROW_ID, TASK_BASE
from .lineage import record_identity_field
from .policy import identity, trusted_reuse
from .tasks import campaign_tasks


def final_claim(events):
    finals = [
        e
        for e in events
        if e.get("event_type") == "message.completed" and e.get("payload", {}).get("phase") != "commentary"
    ]
    if not finals:
        raise Blocked("No accepted final answer was published.")
    event = sorted(finals, key=lambda e: e["sequence"])[-1]
    text = event["payload"].get("content", "")
    blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)```", text)
    candidates = []
    for block in blocks:
        try:
            value = json.loads(block)
            if (
                isinstance(value, dict)
                and {"count", "unknown_count", "coverage_note", "selection"} <= value.keys()
            ):
                candidates.append(value)
        except ValueError:
            pass
    structured = event['payload'].get('structuredResult')
    if structured is not None:
        if not isinstance(structured, dict):
            raise Blocked('Accepted structured result is not an object.')
        if any(value != structured for value in candidates):
            raise Blocked('Final text and accepted structured result conflict.')
        candidates = [structured]
    if len(candidates) != 1:
        raise Blocked("Final answer lacks one unambiguous requested machine-readable result.")
    claim = candidates[0]
    if not {'count', 'unknown_count', 'coverage_note', 'selection'} <= claim.keys():
        raise Blocked('Selected final result is missing required answer fields.')
    if any(
        not isinstance(claim[k], int) or isinstance(claim[k], bool) or claim[k] < 0
        for k in ("count", "unknown_count")
    ):
        raise Blocked("Final counts must be nonnegative integers.")
    if not isinstance(claim["selection"], dict) or not str(claim["coverage_note"]).strip():
        raise Blocked("Final result omits its artifact identity or coverage qualification.")
    return claim, event, text


def check_membership(actual, expected):
    actual = [str(x) for x in actual]
    expected = [str(x) for x in expected]
    duplicates = sorted(k for k, n in Counter(actual).items() if n > 1)
    missing, extra = sorted(set(expected) - set(actual)), sorted(set(actual) - set(expected))
    return {
        "pass": not (duplicates or missing or extra),
        "duplicates": duplicates,
        "missing": missing,
        "extra": extra,
        "actualCount": len(actual),
        "expectedCount": len(expected),
    }


def check_extra_results(frame, record_field, claim, expected):
    """Frozen non-count contracts: retained measurements and actual final statistics."""
    if expected.get("unlocatedPointIds") and claim.get("unlocated_count") != len(
        expected["unlocatedPointIds"]
    ):
        raise Blocked("Final coverage disclosure omits unlocated input points.")
    if "topCountries" in expected and claim.get("top_countries") != expected["topCountries"]:
        raise Blocked("Final highest-country ranking disagrees with the independently computed rates.")
    if "values" not in expected:
        return
    column = claim.get("value_field")
    if not isinstance(column, str) or column not in frame:
        raise Blocked("Final result does not identify the retained measurement field.")
    values = pd.to_numeric(frame.set_index(record_field)[column], errors="raise")
    tolerance = expected.get("tolerance", {"absolute": 1e-6, "relative": 1e-6})

    def close(actual, reference):
        if reference is None:
            return actual is None
        return (
            isinstance(actual, (int, float))
            and not isinstance(actual, bool)
            and math.isfinite(actual)
            and math.isclose(actual, reference, abs_tol=tolerance["absolute"], rel_tol=tolerance["relative"])
        )

    for fid, value in values.items():
        reference = expected["values"][str(fid)]
        if not (pd.isna(value) if reference is None else close(float(value), reference)):
            raise Blocked("Artifact measurement values differ from the frozen source calculation.")
    if "metrics" in expected:
        metrics = claim.get("metrics")
        if not isinstance(metrics, dict) or set(metrics) != set(expected["metrics"]):
            raise Blocked("Final numeric comparison is missing or has the wrong groups.")
        if any(not close(metrics[key], value) for key, value in expected["metrics"].items()):
            raise Blocked("Final statistic differs from the independent reference calculation.")
    if "groups" in expected:
        groups = claim.get("groups")
        if (
            not isinstance(groups, dict)
            or groups != expected["groups"]
            or any(not isinstance(v, int) or isinstance(v, bool) for v in groups.values())
        ):
            raise Blocked("Final state counts differ from the independent station grouping.")


def grade_task(campaign, task):
    campaign = Path(campaign)
    folder = campaign / task
    result = {
        "taskId": task,
        "outcome": "setup-blocked",
        "computationCorrect": False,
        "answerFulfilled": False,
        "reasons": [],
        "durationSeconds": None,
    }
    if not (folder / "attempt.json").exists():
        result["reasons"] = (
            read(campaign / "preflight.json").get("issues", [])
            if (campaign / "preflight.json").exists()
            else []
        )
        result["reasons"].append("No measured attempt started.")
        return result
    attempt = read(folder / "attempt.json")
    elapsed_end = min(timestamp(attempt.get("finishedAt", attempt["startedAt"])), attempt["deadline"])
    result["durationSeconds"] = max(0, elapsed_end - timestamp(attempt["startedAt"]))
    result["outcome"] = "timeout" if attempt["status"] == "timeout" else "fail"
    if attempt.get("reason"):
        result["reasons"].append(attempt["reason"])
    if not (folder / "snapshot.json").exists():
        result["reasons"].append("No collected execution evidence.")
        return result
    snapshot = read(folder / "snapshot.json")
    frozen = read(campaign / "frozen.json")
    oracle = read(campaign / "oracle.json")
    expected = oracle["tasks"][task]
    if expected.get("family") == "qualitative-control":
        result["cohort"] = "qualitative-control"
        result["qualitativeKind"] = expected["kind"]
    result["expectedCount"] = expected["count"]
    result["expectedMetrics"] = expected.get("metrics", expected.get("groups"))
    if (
        oracle["fingerprint"] != frozen["oracleFingerprint"]
        or digest({k: v for k, v in oracle.items() if k != "fingerprint"}) != oracle["fingerprint"]
    ):
        result["reasons"].append("Frozen oracle integrity check failed.")
        return result
    if attempt["freezeHash"] != frozen["freezeHash"]:
        result["reasons"].append("Attempt belongs to a different frozen protocol.")
        return result
    scope = read(folder / "scope.json")
    result["url"] = scope["url"]
    result["tools"] = len(snapshot.get("tools", []))
    result["toolFailures"] = sum(t.get("status") == "failed" for t in snapshot.get("tools", []))
    result["jobs"] = len(snapshot.get("jobs", []))
    result["jobAttempts"] = sum(
        bool(n.get("job_id")) for w in snapshot.get("workflows", []) for n in w["nodes"]
    )
    result["workflowRevisionsExecuted"] = len(
        {w.get("manifest", {}).get("revisionId") for w in snapshot.get("workflows", [])}
    )
    # /model-calls exposes token-usage observations, not a reliable model-round count.
    result["modelRounds"] = None
    result["usageObservations"] = len(snapshot.get("modelCalls", []))
    result["errors"] = snapshot.get("errors", [])
    result["observedTools"] = sorted({t["tool_id"] for t in snapshot.get("tools", [])})
    result["recoveryLedger"] = snapshot["run"].get("working_state", {}).get("analytical_corrections", {})
    try:
        from .map_bindings import bind_evaluation_context

        snapshot = bind_evaluation_context(snapshot, scope, attempt)
        if expected.get("family") == "qualitative-control":
            from .control_grading import assess_control

            review = assess_control(expected, snapshot, folder, attempt["deadline"])
            result.update(review)
            if attempt["status"] == "timeout":
                result["outcome"] = "timeout"
            return result
        claim, event, text = final_claim(snapshot.get("events", []))
        for alternatives in expected.get("answerConcepts", []):
            if not any(
                re.search(r"\b" + re.escape(term) + r"\b", text, re.IGNORECASE) for term in alternatives
            ):
                raise Blocked(
                    "Final answer omits a material declared interpretation or limitation of the derived measurement."
                )
        result["actualCount"] = claim["count"]
        result["actualMetrics"] = claim.get("metrics", claim.get("groups"))
        result["finalAnswer"] = text
        if timestamp(event["created_at"]) > attempt["deadline"]:
            raise Blocked("Final answer was published after the task deadline.")
        if expected.get("family") == "source-overlay":
            from .overlay_grading import grade_overlay

            grade_overlay(task, claim, expected, snapshot, frozen, scope, folder, attempt["deadline"])
            result["computationCorrect"] = True
            if snapshot["run"]["status"] != "completed":
                raise Blocked("Overlay interaction did not complete.")
            result["answerFulfilled"] = True
            if result["outcome"] != "timeout":
                result["outcome"] = "pass"
            return result
        if expected.get("family") in {"county-population-density", "native-population-snow"}:
            if expected["family"] == "county-population-density":
                from .county_density import grade as grade_county_density
            else:
                from .snow_population import grade as grade_county_density

            grade_county_density(task, claim, expected, snapshot, frozen, scope, folder, attempt["deadline"])
            result["computationCorrect"] = True
            if snapshot["run"]["status"] != "completed":
                raise Blocked("County density interaction did not finish.")
            result["answerFulfilled"] = True
            if result["outcome"] != "timeout":
                result["outcome"] = "pass"
            return result
        if expected.get("family") == "raster-proximity-count":
            from .point_count import grade as grade_point_count

            grade_point_count(task, claim, expected, snapshot, frozen, scope, folder, attempt["deadline"])
            result["computationCorrect"] = True
            if snapshot["run"]["status"] != "completed" or any(
                not v for w in snapshot.get("workflows", []) for v in w.get("verifiedMapOutputs", {}).values()
            ):
                raise Blocked("Population proximity did not finish with verified claimed outputs.")
            result["answerFulfilled"] = True
            if result["outcome"] != "timeout":
                result["outcome"] = "pass"
            return result
        if expected.get("family") in {"population-density-share", "population-distance-share", "observed-flood-population"}:
            from .population_grading import grade_population

            grade_population(task, claim, expected, snapshot, frozen, scope, folder, attempt["deadline"])
            result["computationCorrect"] = True
            if snapshot["run"]["status"] != "completed" or any(
                not v for w in snapshot.get("workflows", []) for v in w.get("verifiedMapOutputs", {}).values()
            ):
                raise Blocked("Population analysis did not finish with verified claimed map outputs.")
            result["answerFulfilled"] = True
            if result["outcome"] != "timeout":
                result["outcome"] = "pass"
            return result
        if expected.get("family") == "map-series":
            from .series_grading import grade_series

            grade_series(
                task,
                claim,
                expected,
                snapshot,
                frozen,
                read(campaign / "fixtures.json"),
                scope,
                folder,
                attempt["deadline"],
            )
            result["computationCorrect"] = True
            if snapshot["run"]["status"] != "completed" or any(
                not v for w in snapshot.get("workflows", []) for v in w.get("verifiedMapOutputs", {}).values()
            ):
                raise Blocked("Map series did not finish with all claimed bindings verified.")
            result["answerFulfilled"] = True
            if result["outcome"] != "timeout":
                result["outcome"] = "pass"
            return result
        match = next(
            (a for a in snapshot.get("artifacts", []) if identity(a) == identity(claim["selection"])), None
        )
        if not match:
            raise Blocked("Final answer's selected-feature artifact was not produced and collected.")
        if not match.get("finishedAt") or timestamp(match["finishedAt"]) > attempt["deadline"]:
            raise Blocked("Selected artifact has no verified pre-deadline completion time.")
        if identity(match) not in {
            identity(a) for a in trusted_reuse(snapshot, task, scope["inputs"], for_grading=True,
                                               fixture_bounds=scope.get("fixtureBounds"))
        }:
            raise Blocked("Selected artifact lacks verified fixture-only workflow lineage.")
        path = beneath(folder, match["path"])
        if sha(path) != match["sha256"]:
            raise Blocked("Collected result checksum changed.")
        frame = gpd.read_parquet(path)
        fixtures = read(campaign / "fixtures.json")
        if expected.get("family") == "contour-map":
            from .contour_grading import grade_contour

            grade_contour(
                task,
                frame,
                claim,
                expected,
                snapshot,
                match,
                frozen,
                fixtures,
                scope,
                folder,
                attempt["deadline"],
            )
            result["computationCorrect"] = True
            if any(
                not verified
                for w in snapshot.get("workflows", [])
                for verified in w.get("verifiedMapOutputs", {}).values()
            ):
                raise Blocked("A claimed map output has no authoritative live binding.")
            if snapshot["run"]["status"] != "completed":
                raise Blocked("Interaction did not finish with an accepted result.")
            result["answerFulfilled"] = True
            if result["outcome"] != "timeout":
                result["outcome"] = "pass"
            return result
        base = TASK_BASE[task]
        record_field = record_identity_field(snapshot, claim["selection"], scope["inputs"], fixtures, base)
        result["recordIdentityField"] = record_field
        if (
            not record_field
            or record_field not in frame
            or frame.crs is None
            or frame[record_field].isna().any()
        ):
            raise Blocked("Selected output lacks original row identity or spatial reference.")
        if expected.get("family") == "clipped-line-length":
            from .snow_rail import grade as grade_snow_rail

            grade_snow_rail(frame, claim, expected, frozen["fixtureDirectory"], record_field)
            result["computationCorrect"] = True
            if snapshot["run"]["status"] != "completed" or any(
                not v for w in snapshot.get("workflows", []) for v in w.get("verifiedMapOutputs", {}).values()
            ):
                raise Blocked("Clipped-line calculation did not finish with verified claimed outputs.")
            result["answerFulfilled"] = True
            if result["outcome"] != "timeout":
                result["outcome"] = "pass"
            return result
        membership = check_membership(frame[record_field], expected["ids"])
        result["membership"] = membership
        if not membership["pass"]:
            raise Blocked("Selected feature membership differs from the independent answer.")
        source_path = Path(frozen["fixtureDirectory"]) / fixtures["assets"][base]["path"]
        if sha(source_path) != fixtures["assets"][base]["sha256"]:
            raise Blocked("Original source checksum changed after freeze.")
        source = gpd.read_parquet(source_path).set_index(ROW_ID)
        selected = frame.set_index(record_field).to_crs(source.crs)
        for fid in selected.index:
            # Point coordinates can undergo ordinary reprojection roundoff, not relocation.
            actual_geometry, source_geometry = selected.loc[fid].geometry, source.loc[fid].geometry
            # Exact-coordinate equality proves the same tolerance condition and
            # avoids quadratic Hausdorff work on unchanged detailed coastlines.
            if (
                not actual_geometry.equals_exact(source_geometry, tolerance=1e-8, normalize=True)
                and actual_geometry.hausdorff_distance(source_geometry) > 1e-8
            ):
                raise Blocked("Selected feature geometry differs from its original source.")
        check_extra_results(frame, record_field, claim, expected)
        if expected.get("selectionMapRequired"):
            from .map_bindings import verify_map_binding
            verify_map_binding(snapshot, match, claim.get("map_layer_id"))
        if expected.get("family") in {"geographic-heatmap", "county-heatmap"}:
            from .heat_grading import grade_heat

            grade_heat(task, claim, expected, snapshot, frozen, scope, folder, attempt["deadline"])
        elif expected.get("bivariate"):
            from .bivariate_oracles import check_bivariate

            check_bivariate(frame, record_field, claim, expected, snapshot, match)
        elif expected.get("mapRequired"):
            from .map_oracles import check_map

            check_map(frame, record_field, claim, expected, snapshot, match)
        result["computationCorrect"] = True
        if claim["count"] != expected["count"] or claim["unknown_count"] != len(expected["unknownIds"]):
            raise Blocked("Final count or unknown-coverage count disagrees with the computed evidence.")
        if any(
            not verified
            for w in snapshot.get("workflows", [])
            for verified in w.get("verifiedMapOutputs", {}).values()
        ):
            raise Blocked("A claimed workflow map output has no authoritative live binding.")
        if snapshot["run"]["status"] != "completed":
            raise Blocked("Interaction did not finish successfully with an accepted result.")
        result["answerFulfilled"] = True
        if result["outcome"] != "timeout":
            result["outcome"] = "pass"
    except (Blocked, OSError, ValueError, KeyError) as exc:
        result["reasons"].append(str(exc))
        if result["outcome"] != "timeout" and result["computationCorrect"]:
            result["outcome"] = "partial"
    return result


def grade(campaign):
    campaign = Path(campaign)
    results = [grade_task(campaign, task) for task in campaign_tasks(campaign)]
    output = {
        "protocol": "GeoBenchX-derived system evaluation",
        "tasks": results,
        "passed": sum(r["outcome"] == "pass" for r in results),
        "total": len(results),
    }
    write(campaign / "results.json", output)
    return output
