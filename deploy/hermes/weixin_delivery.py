#!/usr/bin/env python3
"""Host worker: claim from the container, send with the host Hermes account.

Requires only Python's standard library, Docker Compose, and the existing
Hermes CLI. No extra HTTP service, database mount, or iLink credentials.
"""
import argparse
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import time

LOG = logging.getLogger("zhiliu.weixin")


def outbox(action: str, payload: dict | None = None):
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "backend", "python", "-m", "app.ops.weixin_delivery", action],
        cwd=os.environ.get("ZHILIU_ROOT", "/opt/zhiliu"),
        input=json.dumps(payload) if payload is not None else "",
        capture_output=True, text=True, encoding="utf-8", timeout=30, check=True,
    )
    return json.loads(result.stdout)


def send(message: str) -> str:
    # Defense in depth: these strings are data, not Hermes attachment tags.
    message = re.sub(r"MEDIA\s*:", "MEDIA：", message, flags=re.IGNORECASE)
    message = re.sub(r"\[\[[^]\n]*\]\]", "", message)
    try:
        result = subprocess.run(
            [os.environ.get("HERMES_CLI_PATH", "/root/.local/bin/hermes"),
             "send", "--to", "weixin", "--json", "--file", "-"],
            input=message, capture_output=True, text=True, encoding="utf-8",
            timeout=60, check=False,
        )
    except subprocess.TimeoutExpired:
        return "unknown"
    except OSError:
        return "failed"
    output = (result.stdout + "\n" + result.stderr).casefold()
    if any(marker in output for marker in ("session not ready", "prepare failed", "re-pair")):
        return "session_not_ready"
    try:
        payload = json.loads(result.stdout)
    except ValueError:
        return "unknown"
    if not isinstance(payload, dict):
        return "unknown"
    if result.returncode == 0 and payload.get("success") is True and not payload.get("error") and not payload.get("skipped"):
        return "sent"
    return "failed"


def deliver_one() -> bool:
    job = outbox("claim")
    if job is None:
        return False
    status = send(job["message"])
    receipt = {"taskId": job["taskId"], "token": job["token"], "status": status}
    # Retry only the receipt if the backend restarts after a successful send.
    for attempt in range(3):
        try:
            acknowledged = outbox("ack", receipt)
            if not acknowledged.get("acknowledged"):
                LOG.warning("task=%s stale receipt; no resend", job["taskId"])
            else:
                LOG.info("task=%s delivery=%s", job["taskId"], status)
            return True
        except (subprocess.SubprocessError, OSError, ValueError):
            if attempt < 2:
                time.sleep(2)
    LOG.error("task=%s receipt unavailable; check Weixin before retrying", job["taskId"])
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Process at most one notification and exit")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if not Path(os.environ.get("ZHILIU_ROOT", "/opt/zhiliu")).is_dir():
        raise SystemExit("ZHILIU_ROOT does not exist")
    while True:
        try:
            delivered = deliver_one()
        except (subprocess.SubprocessError, OSError, ValueError, KeyError, TypeError):
            LOG.error("Outbox unavailable; check backend and Docker Compose")
            delivered = False
        if args.once:
            return
        time.sleep(2 if delivered else 10)


if __name__ == "__main__":
    main()
