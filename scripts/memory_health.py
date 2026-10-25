"""Read-only memory health observations; explicit --fix only updates install evidence metadata."""
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid

import automation_contract as ac
import install
import memory_capture as mc
import memory_recall as mr
import project_memory as pm

MAX_AGE = 86400  # runtime evidence is an observation, not a perpetual health claim
LOCK_AGE = 900
UNSET = object()


def age(value):
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("timezone required")
    seconds = (datetime.now(timezone.utc) - stamp).total_seconds()
    if seconds < -5:
        raise ValueError("future observation")
    return max(0, seconds)


def smoke_test(root):
    """Synthetic data never enters the project, recall sources, or install evidence."""
    with tempfile.TemporaryDirectory(prefix="dreamdocs-smoke-") as folder:
        isolated = Path(folder)
        for name in ("memory/config.json",):
            target = isolated / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(pm.confined(root, name), target)
        for category in ("episodes", "facts", "procedural", "contradictions", "archive", "dreamer"):
            (isolated / "memory" / category).mkdir()
        marker = "smoke-" + uuid.uuid4().hex
        binding = {"version": 1, "project_id": "dreamdocs-smoke", "adapters": ["codex"]}
        pm.atomic(isolated / "memory/automation.json", binding)
        event = {"version": 1, "kind": "task_outcome", "adapter": "codex", "session_id": marker,
                 "turn_id": "smoke", "project_id": "dreamdocs-smoke", "worktree": "smoke", "agent": "smoke",
                 "occurred_at": pm.now(), "privacy": "project", "task": None,
                 "outcome": {"status": "success", "summary": marker, "lessons": [], "evidence": ["ref:synthetic-local-smoke"]}}
        saved = mc.capture(isolated, event)["saved"]
        recalled = mr.recall(isolated)
        return {"saved": saved, "retrieved": marker in recalled["context"], "scope": "isolated local engine only"}


def observed(root, entry, kind, record, installed_at, receipts):
    """Validate explicitly supplied observations; a source hash is integrity, not independent testimony."""
    try:
        if not isinstance(entry, dict) or entry.get("kind") != kind:
            return False
        allowed = {"kind", "observed_at", "client_version", "command_sha256", "source", "sha256"}
        if kind == "fresh-session-recall":
            allowed |= {"client", "event_id", "marker", "capture_session", "recall_session"}
        if set(entry) != allowed or ac.SECRET.search(ac.canonical(entry)):
            return False
        if age(entry["observed_at"]) > MAX_AGE or age(entry["observed_at"]) > age(installed_at):
            return False
        if entry["command_sha256"] != install.command_digest(record) or entry["client_version"] != record["version"]:
            return False
        source = pm.confined(root, entry["source"])
        if pm.bounded_digest(source) != entry["sha256"]:
            return False
        if kind == "fresh-session-recall":
            receipt = receipts[entry["event_id"]]
            episode = pm.confined(root, receipt["episode"])
            text = episode.read_text(encoding="utf-8")
            refs = pm.metadata(text)["source"]
            # A different session and an observed marker from the persisted episode are required.
            if not entry["marker"] or entry["marker"] not in text or entry["marker"] not in source.read_text(encoding="utf-8"):
                return False
            if entry["capture_session"] == entry["recall_session"] or not entry["recall_session"]:
                return False
            if not any(r.startswith(f"ref:{entry['client']}/{entry['capture_session']}/") for r in refs):
                return False
        return True
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


def doctor(root, fix=False, smoke=False, evidence=UNSET, checkpoints=None):
    evidence_supplied = evidence is not UNSET
    if not evidence_supplied:
        evidence = None
    root = Path(root).resolve()
    findings, clients, receipts = [], {}, {}

    def finding(code, scope, action, component="memory"):
        findings.append({"code": code, "scope": scope, "component": component, "next_action": action,
                         "resume_condition": "Recheck after the stated action; never bypass owner pauses or active writers.",
                         "next_check": "Run doctor again after resolving this finding."})

    def load(relative, default=None):
        try:
            path = pm.confined(root, relative)
            return pm.read_json(path) if path.is_file() else default
        except (OSError, ValueError):
            finding("invalid_json", relative, "Inspect the file locally; restore valid JSON without discarding user data.")
            return default

    try:
        manifest_raw = install.read(root, install.MANIFEST)
    except (OSError, ValueError):
        manifest_raw = ""  # unavailable metadata remains invalid and is never written
    manifest_valid = False
    try:
        manifest = install.validate_manifest(json.loads(manifest_raw))
        age(manifest["installed_at"])
        manifest_valid = True
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        manifest = {}
        finding("invalid_manifest" if manifest_raw is not None else "not_installed", install.MANIFEST,
                "Inspect the install manifest shape locally; restore valid metadata or run setup preview. No health metadata was written.", "setup")
    if manifest.get("package", {}).get("version") != install.PACKAGE_VERSION:
        finding("package_version_changed", "package", "Review the selected package and upgrade plan; do not mark a new version installed from file presence alone.", "setup")
    for relative, expected in manifest.get("package_files", {}).items():
        try:
            actual = pm.digest(pm.confined(root, relative).read_bytes())
        except (OSError, ValueError):
            actual = None
        if actual != expected:
            finding("package_file_changed", relative, "Review the local edit/missing package asset against the installed baseline before setup or upgrade.", "setup")
    schema = "valid"
    try:
        pm.settings(root)
        pm.records(root)
        bound = load("memory/automation.json")
        ac.validate_binding(bound)
    except (OSError, ValueError, TypeError, AttributeError):
        schema = "invalid"
        finding("invalid_schema", "memory", "Run project_memory.py validate and correct reported schema errors.")
    for relative in ("memory/dreamer/command.lock", "memory/dreamer/lock.json"):
        path = pm.confined(root, relative)
        if path.exists():
            value = load(relative, {})
            try:
                seconds = age(value.get("acquired_at") or value["started_at"])
                code = "aged_lock" if seconds > LOCK_AGE else "writer_lock"
            except (ValueError, TypeError, KeyError, AttributeError):
                seconds, code = None, "malformed_lock"
            finding(code, relative, "Confirm the owning process/run has stopped; use explicit Dreamer recovery only when safe. Lock retained.", "writer")
    for folder, label in ((mc.PENDING, "pending"), ("memory/automation/events", "event")):
        path = pm.confined(root, folder)
        if not path.is_dir():
            continue
        for item in sorted(path.glob("*.json")):
            relative = item.relative_to(root).as_posix()
            try:
                value = pm.read_json(pm.confined(root, relative))
                if label == "event":
                    ac.validate_event(value)
                else:
                    if not isinstance(value, dict) or set(value) != mc.PLAN_FIELDS or value["version"] != 1:
                        raise ValueError("invalid pending plan")
                    if not ac.SHA256.fullmatch(value["payload_sha256"]) or not isinstance(value["event_id"], str):
                        raise ValueError("invalid pending identity")
                seconds = max(0, datetime.now(timezone.utc).timestamp() - item.stat().st_mtime)
                code = "aged_pending" if label == "pending" and seconds > LOCK_AGE else "pending_capture" if label == "pending" else "leftover_event"
            except (OSError, ValueError, TypeError, KeyError, AttributeError):
                code = "malformed_pending" if label == "pending" else "leftover_event"
            finding(code, relative, "Inspect locally; after writers stop, retry memory reconcile (pending) or a SessionStart hook (events). Malformed files stay in place.", "capture")
    readback, last = "unknown", None
    path = pm.confined(root, mc.RECEIPTS)
    if path.is_dir():
        for item in sorted(path.glob("*.json")):
            try:
                receipt = pm.read_json(pm.confined(root, item.relative_to(root).as_posix()))
                ac.validate_receipt(receipt)
                if item.stem != receipt["event_id"]:
                    raise ValueError("receipt identity mismatch")
                age(receipt["recorded_at"])
                if receipt["status"] == "persisted":
                    episode = pm.confined(root, receipt["episode"])
                    if pm.digest(episode.read_bytes()) != receipt["episode_sha256"]:
                        raise ValueError("readback mismatch")
                receipts[receipt["event_id"]] = receipt
                last = max(last or receipt["recorded_at"], receipt["recorded_at"])
            except (OSError, ValueError, TypeError, KeyError, AttributeError):
                readback = "mismatch"
                finding("readback_mismatch", item.name, "Inspect receipt and episode; restore the acknowledged bytes before retrying. Do not synthesize a successful receipt.", "capture")
        if receipts and readback != "mismatch":
            readback = "verified"
    if last is None:
        finding("capture_unknown", "receipts", "Observe a real completed client turn and check its capture/readback. No receipt does not prove no work happened.", "capture")
    elif age(last) > MAX_AGE:
        finding("stale_capture", "receipts", "Observe the next expected real turn; old receipts prove historical persistence only.", "capture")
    if checkpoints is not None and (not isinstance(checkpoints, list) or not all(isinstance(c, dict) for c in checkpoints)):
        raise ValueError("checkpoints must be an explicit array of checkpoint objects")
    for task in checkpoints or []:
        if task.get("status") in {"paused", "backlog", "future"}:
            continue
        try:
            stamp = datetime.fromisoformat(task["expected_at"].replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                raise ValueError("timezone required")
            due = stamp <= datetime.now(timezone.utc)
        except (ValueError, TypeError, KeyError, AttributeError):
            finding("invalid_checkpoint", task.get("task_id", "unknown"), "Supply an explicit timezone-aware expected save checkpoint.")
            continue
        if not due:
            continue
        try:
            event = task["event"]
            ac.validate_event(event)
            ac.validate_binding(bound)
            if (event["project_id"] != bound["project_id"] or event["adapter"] not in bound["adapters"]
                    or event["kind"] != "task_outcome" or not event["task"] or event["task"]["id"] != task["task_id"]):
                raise ValueError("checkpoint identity mismatch")
            eid = ac.event_id(event)
            payload_sha = pm.digest(ac.canonical(event).encode())
        except (ValueError, TypeError, KeyError, AttributeError):
            finding("invalid_checkpoint", task.get("task_id", "unknown"), "Supply the exact expected outcome event matching this task, project and installed adapter; an event ID alone cannot prove task persistence.")
            continue
        matched = eid in receipts and receipts[eid]["payload_sha256"] == payload_sha
        if matched and receipts[eid]["status"] == "receipt_only":
            finding("checkpoint_receipt_only_unverified", task["task_id"], "A receipt-only outcome has no persisted task episode to cross-check. Inspect the exact event and task evidence; do not infer task completion.", "continuity")
        elif matched:
            try:
                meta = pm.metadata(pm.confined(root, receipts[eid]["episode"]).read_text(encoding="utf-8"))
                matched = (meta["project"] == event["project_id"] and meta["scope"] == "task:" + task["task_id"]
                           and f"ref:{event['adapter']}/{event['session_id']}/{event['turn_id']}" in meta["source"])
            except (OSError, ValueError, TypeError, KeyError):
                matched = False
        if not matched:
            finding("missing_save", task.get("task_id", "unknown"), "Reconcile the authoritative task outcome with its event/receipt; retry exact local capture only. Never repeat an uncertain external operation.", "continuity")
    TRUST_KEYS = {"kind", "observed_at", "client_version", "command_sha256", "source", "sha256"}
    RECALL_KEYS = TRUST_KEYS | {"client", "event_id", "marker", "capture_session", "recall_session"}
    is_valid_obs = lambda k, v: isinstance(v, dict) and set(v) == (TRUST_KEYS if k == "trust" else RECALL_KEYS)
    evidence_valid = (not evidence_supplied or (isinstance(evidence, dict) and set(evidence) == {"version", "clients"}
                      and type(evidence["version"]) is int and evidence["version"] == 1 and isinstance(evidence["clients"], dict)
                      and set(evidence["clients"]) <= set(install.CLIENTS)
                      and all(isinstance(v, dict) and set(v) <= {"trust", "recall"} and all(is_valid_obs(k, o) for k, o in v.items()) for v in evidence["clients"].values())))
    if not evidence_valid:
        finding("invalid_evidence", "evidence", "Supply version 1 with a clients object and per-client trust/recall observation objects. No metadata was written.", "doctor")
    supplied = evidence["clients"] if evidence_supplied and evidence_valid else {}
    for client, record in manifest.get("clients", {}).items():
        if client not in install.CLIENTS or not isinstance(record, dict):
            finding("unknown_adapter", client, "Install a supported adapter or remove the invalid manifest entry explicitly.", "adapter")
            continue
        spec = install.CLIENTS[client]
        hooks = load(spec["hook_file"])
        intact = True
        if hooks is None:
            intact = False
            finding("hook_missing", client, "Review setup preview and reinstall project hooks.", "adapter")
        else:
            try:
                for event in record["events"]:
                    entries = [h for g in hooks["hooks"].get(event, []) for h in g.get("hooks", []) if install.is_ours(h, spec["script"])]
                    if len(entries) != 1 or entries[0] != install.handler(client, root, event):
                        intact = False
                stop = [h for g in hooks["hooks"].get("Stop", []) for h in g.get("hooks", []) if install.is_ours(h, spec["script"])]
                if len(stop) != 1 or pm.digest(json.dumps(stop[0], sort_keys=True).encode()) != install.command_digest(record):
                    intact = False
            except (ValueError, KeyError, TypeError, AttributeError):
                intact = False
            if not intact:
                finding("hook_changed", client, "Review changed/duplicate/moved handlers; run setup preview and renew client trust after repair.", "adapter")
        version = install.codex_version() if client == "codex" else install.claude_version()
        same_version = version is not None and version == record.get("version")
        if not same_version:
            finding("client_version_changed", client, "Verify installed client compatibility and repeat real trust/recall probes.", "adapter")
        observations = supplied.get(client, record.get("health", {}).get("observations", {}))
        if not isinstance(observations, dict):
            observations = {}
        trust = intact and same_version and observed(root, observations.get("trust"), "client-trust", record, manifest["installed_at"], receipts)
        recall_entry = observations.get("recall", {})
        recall = (intact and same_version and isinstance(recall_entry, dict) and recall_entry.get("client") == client
                  and observed(root, recall_entry, "fresh-session-recall", record, manifest["installed_at"], receipts))
        clients[client] = {"hook_config": "intact" if intact else "missing_or_changed", "installed_version": record.get("version"),
                           "current_version": version, "compatibility": ac.SUPPORT[client]["state"],
                           "trust": "reported_trusted" if trust else "unknown", "recall": "reported_observed" if recall else "unknown",
                           "provenance": "Explicit local source-backed client observations; not independently authenticated by doctor."}
        if not trust:
            finding("trust_unknown", client, spec["trust"], "adapter")
        if not recall:
            finding("recall_unknown", client, "Observe saved content in a different real client session and supply its source-backed recall observation.", "recall")
        if fix:
            record["trust"] = "trusted" if trust else "changed" if not intact else "pending"
            record["probe"] = "verified" if recall else "pending"
            accepted = {key: observations[key] for key, valid in (("trust", trust), ("recall", recall)) if valid}
            record["health"] = {"observations": accepted, "capture_readback": readback, "checked_at": pm.now()}
    try:
        git = subprocess.run(["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"], capture_output=True, timeout=5)
        in_git = git.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        in_git = False
    if not in_git:
        finding("non_git_project", "project", "Review the client's directory trust rules; Codex may require git init or explicit trust.", "adapter")
    cfg = load("memory/config.json", {})
    schedule = cfg.get("schedule", {}) if isinstance(cfg, dict) else {}
    configured = all(schedule.get(k) for k in ("timezone", "local_time", "owner"))
    dreamer = {"schedule": "configured_only" if configured else "unconfigured", "scheduler": "unverified", "executor": "unconfigured",
               "checkpoint": load("memory/dreamer/state.json"), "active_run": pm.confined(root, "memory/dreamer/lock.json").exists()}
    import dreamer_executor as de
    if pm.confined(root, de.CONFIG).is_file():
        observation = de.status(root)
        dreamer["executor_observation"] = observation
        dreamer["executor"] = observation["state"]
        if observation["exit"]:
            finding("executor_unverified", "dreamer", "Inspect explicit executor configuration and the last run/result/checkpoint readback; no live execution is inferred.", "dreamer")
        import dreamer_schedule as ds
        if pm.confined(root, ds.INSTALL).is_file():
            scheduling = ds.manage(root, "status")
            dreamer["scheduler_observation"] = scheduling
            dreamer["scheduler"] = scheduling["state"]
    if dreamer["scheduler"] != "observed_success":
        finding("scheduler_unverified", "dreamer", "Scheduling requires separate explicit opt-in and live trigger/executor/checkpoint evidence; configured fields are not runtime proof.", "dreamer")
    import materials_index as mi
    materials = mi.status(root)
    if materials["exit"]:
        finding("materials_unavailable", "human-materials", "Fix human_materials settings or the material index, then rerun doctor.", "materials")
    elif materials["state"] == "off" and materials["unindexed"]:
        finding("materials_indexing_off", "human-materials", "Files have no index row. With owner consent run 'dreamdocs.py materials mode summarize' (or inventory).", "materials")
    elif materials["state"] != "off" and (materials["unindexed"] or materials["rows_by_status"].get("unread")):
        finding("materials_pending", "human-materials", "Unindexed or unsummarized files wait for the next session start or Dreamer run; run 'dreamdocs.py materials index --apply' to process now.", "materials")
    if materials.get("proposals_for_reviewed_rows"):
        finding("materials_review_proposals", "human-materials", "A reviewed file changed; compare the stored AI proposal in .dreamdocs/human-materials-state.json and update the row.", "materials")
    result = {"exit": 2 if not evidence_valid or manifest_raw is not None and not manifest_valid else 1 if findings else 0, "schema": schema, "installed_package": manifest.get("package"),
              "clients": clients, "capture": {"readback": readback, "last_persisted_at": last, "receipts": len(receipts), "trigger_delivery": "unknown"},
              "dreamer": dreamer, "human_materials": materials, "findings": findings, "notification": "local report only; no external reporting or background monitor",
              "applied": False, "limits": "Configuration, receipts, smoke and source-backed reported observations prove different things; no process, product or schedule is started."}
    if smoke:
        result["smoke"] = smoke_test(root)
        if not all(result["smoke"][k] for k in ("saved", "retrieved")):
            finding("smoke_failed", "local-engine", "Inspect isolated capture/recall failure before enabling hooks.")
            result["exit"] = 1
    if fix and manifest_valid and evidence_valid and not any(f["component"] == "writer" for f in findings):
        with pm.operation(root):
            if pm.confined(root, "memory/dreamer/lock.json").exists():
                raise ValueError("Dreamer run active; evidence metadata not changed")
            if install.read(root, install.MANIFEST) != manifest_raw:
                finding("manifest_changed_during_scan", install.MANIFEST, "Install metadata changed after observation; rerun doctor against the new revision. No metadata was overwritten.", "setup")
                result["exit"] = 1
            else:
                current = json.loads(manifest_raw)
                for client, record in manifest.get("clients", {}).items():
                    for key in ("trust", "probe", "health"):
                        current["clients"][client][key] = record[key]
                pm.atomic(pm.confined(root, install.MANIFEST), current)
                result["applied"] = True
    return result
