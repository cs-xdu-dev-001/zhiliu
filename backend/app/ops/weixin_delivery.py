"""Container-side outbox access; called only through docker compose exec."""
import json
import sys

from app.core.config import get_settings
from app.db import SessionLocal
from app.services.hermes_notify import acknowledge_notification, claim_notification


def main() -> None:
    action = sys.argv[1] if len(sys.argv) == 2 else ""
    with SessionLocal() as db:
        if action == "claim":
            result = claim_notification(db, get_settings())
        elif action == "ack":
            payload = json.load(sys.stdin)
            result = {"acknowledged": acknowledge_notification(
                db, int(payload["taskId"]), payload["token"], payload["status"],
            )}
        else:
            raise SystemExit("Usage: python -m app.ops.weixin_delivery claim|ack")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
