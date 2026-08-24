"""Milestone 33.2 Part 18: cross-language object-key contract test.

Both languages must derive the SAME object key from the SAME logical
artifact path -- a Process/Refresh run's Python writer and a member's
Node.js read must agree on where an artifact lives in the shared bucket,
or production reads would silently miss what production writes just
saved. This is the Python half; dashboard/lib/__tests__/artifactKeyContract.test.ts
is the Node half. Both read the SAME fixture file
(tests/fixtures/artifact_key_contract.json) so a case can never be added
to one side's expectations without the other -- that's the whole point
of a "contract" test.
"""

import json
from pathlib import Path

from research.artifact_storage import ARTIFACT_ROOT, to_artifact_key

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "artifact_key_contract.json"


def _load_cases():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_fixture_file_is_non_empty():
    cases = _load_cases()
    assert len(cases) >= 5


def test_to_artifact_key_matches_the_shared_contract_for_every_case():
    for case in _load_cases():
        path = ARTIFACT_ROOT.joinpath(*case["segments"])
        assert to_artifact_key(path) == case["expectedKey"], case["description"]


def test_to_artifact_key_matches_the_shared_contract_from_a_relative_path_too():
    # Confirms the key doesn't depend on whether the caller built an
    # absolute path (via ARTIFACT_ROOT, like every real persistence
    # module does) or passed an already-relative one -- both languages'
    # real callers do the former, but the function accepts either.
    for case in _load_cases():
        relative = Path(*case["segments"])
        assert to_artifact_key(relative) == case["expectedKey"], case["description"]
