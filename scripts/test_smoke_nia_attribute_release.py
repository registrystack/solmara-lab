from __future__ import annotations

import importlib.util
import io
import json
import os
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "smoke_nia_attribute_release",
    ROOT / "scripts" / "smoke-nia-attribute-release.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FakeResponse:
    def __init__(self, body: dict[str, object]) -> None:
        self.status = 200
        self.body = body

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.body).encode("utf-8")


class NiaAttributeReleaseSmokeTests(unittest.TestCase):
    def test_live_request_uses_the_minimized_profile_contract(self) -> None:
        response = FakeResponse(
            {
                "profile_id": "solmara-nia-userinfo",
                "profile_version": "v1",
                "claims": {
                    "individual_id": MODULE.SUBJECT,
                    "name": "Elena Dela Cruz",
                },
            }
        )
        with (
            mock.patch.dict(
                os.environ,
                {"NIA_ESIGNET_RELAY_TOKEN": "runtime-token"},
                clear=True,
            ),
            mock.patch.object(
                MODULE.urllib.request,
                "urlopen",
                return_value=response,
            ) as urlopen,
        ):
            self.assertEqual(MODULE.main(), 0)

        request = urlopen.call_args.args[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.get_header("Authorization"), "Bearer runtime-token")
        self.assertEqual(request.get_header("Data-purpose"), MODULE.PURPOSE)
        self.assertEqual(
            json.loads(request.data),
            {
                "subject": {
                    "id_type": "national_id",
                    "value": MODULE.SUBJECT,
                }
            },
        )

    def test_source_metadata_is_rejected(self) -> None:
        stderr = io.StringIO()
        with (
            mock.patch.dict(
                os.environ,
                {"NIA_ESIGNET_RELAY_TOKEN": "runtime-token"},
                clear=True,
            ),
            mock.patch.object(
                MODULE.urllib.request,
                "urlopen",
                return_value=FakeResponse(
                    {
                        "profile_id": "solmara-nia-userinfo",
                        "profile_version": "v1",
                        "claims": {
                            "individual_id": MODULE.SUBJECT,
                            "name": "Elena Dela Cruz",
                        },
                        "source": {"dataset": "population"},
                    }
                ),
            ),
            redirect_stderr(stderr),
        ):
            self.assertEqual(MODULE.main(), 1)

        self.assertIn("response disclosed source metadata", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
