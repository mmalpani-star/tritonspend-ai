"""Operator-only: make the database's Food Nearby catalog match backend/app/data/food_catalog.json.

Repeatable: matches venues and stations by stable IDs, updates changed fields, deactivates
records that left the catalog, and never deletes or invents anything (no menu items).
Requires the database to be migrated to 20261107_0005 or later. Targets whatever DATABASE_URL
and TRITONSPEND_ENV select, so check the printed target first; --dry-run changes nothing.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy.engine import make_url

from backend.app.config import get_settings
from backend.app.db import get_session_factory
from backend.app.food_catalog import load_catalog, seed_food_catalog


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="report what would change, then roll back")
    args = parser.parse_args()
    settings = get_settings()
    target = make_url(settings.database_url).render_as_string(hide_password=True)
    catalog = load_catalog()
    print(f"target: {target} ({settings.environment}); catalog {catalog['catalog_version']}")
    session = get_session_factory()()
    try:
        result = seed_food_catalog(session, catalog)
        if args.dry_run:
            session.rollback()
        else:
            session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    print(("dry run, nothing written: " if args.dry_run else "") + ", ".join(
        f"{name}={value}" for name, value in vars(result).items() if name != "deactivated_ids"
    ))
    if result.deactivated_ids:
        print("deactivated:", ", ".join(result.deactivated_ids))


if __name__ == "__main__":
    main()
