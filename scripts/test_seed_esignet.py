from __future__ import annotations

import importlib.util
import json
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('seed_esignet', Path(__file__).with_name('seed-esignet.py'))
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SeedEsignetTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        environment = patch.dict(MODULE.os.environ, {'ESIGNET_SEED_STATE_DIR': self.directory.name})
        environment.start()
        self.addCleanup(environment.stop)

    def test_changed_key_or_rp_cannot_update_existing_registration(self):
        MODULE.save_registered_binding('{"kty":"RSA", "n":"original"}')
        with patch.object(MODULE, 'admin_request', return_value={'response': {'clientId': MODULE.CLIENT_ID}}) as request:
            with self.assertRaisesRegex(RuntimeError, 'fresh ESIGNET_CLIENT_ID'):
                MODULE.seed_esignet('{"kty":"RSA", "n":"changed"}')
            self.assertEqual(request.call_count, 1)
        with patch.object(MODULE, 'RELYING_PARTY_ID', 'another-rp'):
            with self.assertRaisesRegex(RuntimeError, 'fresh ESIGNET_CLIENT_ID'):
                MODULE.require_registered_binding('{"kty":"RSA", "n":"original"}')

    def test_existing_registration_without_evidence_fails_closed(self):
        with patch.object(MODULE, 'admin_request', return_value={'response': {'clientId': MODULE.CLIENT_ID}}) as request:
            with self.assertRaisesRegex(RuntimeError, 'cannot be verified'):
                MODULE.seed_esignet('{}')
            self.assertEqual(request.call_count, 1)

    def test_registration_is_otp_only_and_requires_pkce(self):
        payload = MODULE.client_request(json.dumps({'kty': 'RSA', 'e': 'AQAB', 'n': 'public-test-key'}))
        self.assertEqual(payload['authContextRefs'], ['mosip:idp:acr:static-code'])
        self.assertEqual(payload['clientAuthMethods'], ['private_key_jwt'])
        self.assertTrue(payload['additionalConfig']['require_pkce'])
        self.assertNotIn('consent_expire_in_mins', payload['additionalConfig'])
        self.assertIsInstance(payload['publicKey'], dict)

    def test_admin_timestamp_matches_native_millisecond_contract(self):
        with patch.object(MODULE, 'urlopen', return_value=io.BytesIO(b'{"response": {}}')) as transport:
            MODULE.admin_request('POST', '/client-mgmt/client', {})
        request = transport.call_args.args[0]
        timestamp = json.loads(request.data)['requestTime']
        self.assertRegex(timestamp, r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$')

    def test_duplicate_registration_uses_native_update_api(self):
        MODULE.save_registered_binding("{}")
        with patch.object(MODULE, 'admin_request', side_effect=[
            {'response': {'clientId': MODULE.CLIENT_ID}},
            {'response': {'clientId': MODULE.CLIENT_ID}},
        ]) as request:
            MODULE.seed_esignet('{}')
        self.assertEqual(request.call_args_list[0].args[:2], ('GET', '/client-mgmt/client/' + MODULE.CLIENT_ID))
        self.assertEqual(request.call_args_list[1].args[:2], ('PUT', '/client-mgmt/client/' + MODULE.CLIENT_ID))

    def test_api_errors_fail_closed_without_response_detail(self):
        with patch.object(MODULE, 'admin_request', side_effect=[
            {'errors': [{'errorCode': 'invalid_client_id'}]},
            {'errors': [{'errorCode': 'invalid_public_key', 'errorMessage': 'sensitive-value'}]},
        ]):
            with self.assertRaisesRegex(RuntimeError, 'invalid_public_key') as raised:
                MODULE.seed_esignet('{}')
        self.assertNotIn('sensitive-value', str(raised.exception))

    def test_hosted_callback_rejects_loopback_and_http(self):
        for callback in ['http://portal.example/auth/callback', 'https://127.0.0.1/auth/callback']:
            with self.subTest(callback=callback), patch.dict(MODULE.os.environ, {
                'ESIGNET_REQUIRE_HTTPS_REDIRECTS': 'true',
                'ESIGNET_CLIENT_REDIRECT_URIS_JSON': json.dumps([callback]),
            }):
                with self.assertRaises(ValueError):
                    MODULE.redirect_uris()


if __name__ == '__main__':
    unittest.main()
