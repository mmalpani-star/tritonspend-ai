"""Operator-only local invite creation.

Run this script directly on a trusted operator machine; it never exposes an
invite-generation HTTP endpoint.
"""

from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.config import get_settings
from backend.app.db import get_session_factory
from backend.app.models import InviteToken
from backend.app.security import hash_secret, make_secret, utc_now


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=int, default=72)
    args = parser.parse_args()
    settings = get_settings()
    raw_token = make_secret()
    now = utc_now()
    with get_session_factory().begin() as session:
        session.add(
            InviteToken(
                token_hash=hash_secret(raw_token, settings.session_secret),
                created_at=now,
                expires_at=now + timedelta(hours=args.hours),
            )
        )
    print(raw_token)


if __name__ == "__main__":
    main()
