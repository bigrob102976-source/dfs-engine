"""CLI entry point: prints a single JSON line describing external
projection status for a date -- what the dashboard's provider status
card and Settings page render. Never prints an API key or any other
secret (this script never even reads BLUECOLLAR_API_KEY; only
BlueCollarProvider.is_configured() would, and that always returns False
today regardless -- see external_projections/bluecollar_provider.py).

    python scripts/external_projection_status.py --date YYYY-MM-DD
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from external_projections.persistence import (  # noqa: E402
    load_latest_adjusted_snapshot,
    load_latest_baseline_snapshot,
)
from external_projections.registry import PROVIDER_FACTORIES, get_configured_provider  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Report external projection provider/baseline/adjusted status for one date.")
    parser.add_argument("--date", required=True)
    args = parser.parse_args()

    provider, reason, source = get_configured_provider()

    provider_status = {
        "configured_source": source,  # "unconfigured" | "explicit" | "unknown"
        "reason": reason,
        "provider_key": provider.name if provider else None,
        "provider_name": provider.provider_name() if provider else None,
        "provider_version": provider.provider_version() if provider else None,
        "is_mock": provider.is_mock if provider else None,
        "is_configured": provider.is_configured() if provider else False,
        "available_providers": sorted(PROVIDER_FACTORIES),
    }

    baseline = load_latest_baseline_snapshot(args.date)
    baseline_status = {
        "exists": baseline is not None,
        "provider_name": baseline.get("provider_name") if baseline else None,
        "is_mock": baseline.get("is_mock") if baseline else None,
        "retrieved_at": baseline.get("retrieved_at") if baseline else None,
        "player_count": baseline.get("player_count") if baseline else None,
    }

    adjusted = load_latest_adjusted_snapshot(args.date)
    adjusted_status = {
        "exists": adjusted is not None,
        "generated_at": adjusted.get("generated_at") if adjusted else None,
        "record_count": adjusted.get("record_count") if adjusted else None,
        "adjustment_model_version": adjusted.get("adjustment_model_version") if adjusted else None,
    }

    print(json.dumps({
        "slate_date": args.date,
        "provider": provider_status,
        "baseline": baseline_status,
        "adjusted": adjusted_status,
    }))


if __name__ == "__main__":
    main()
