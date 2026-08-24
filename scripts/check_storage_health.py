"""CLI diagnostic: prints artifact-storage readiness as one JSON line --
the Python-side counterpart to the Admin System page's Object Storage
card (dashboard/lib/systemReadiness.ts::getObjectStorageReadiness()).
Never destructive, never prints a credential/endpoint value.

Usage:
    python scripts/check_storage_health.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from research.artifact_storage import check_artifact_storage_health


def main() -> None:
    print(json.dumps(check_artifact_storage_health()))


if __name__ == "__main__":
    main()
