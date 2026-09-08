import importlib.util
import pathlib
import unittest
from unittest.mock import patch, MagicMock

spec = importlib.util.spec_from_file_location('relay_probe', pathlib.Path(__file__).parents[1] / 'probe.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class ProbeTests(unittest.TestCase):
    def run_with(self, bodies):
        opener = MagicMock()
        responses = []
        for body in bodies:
            response = MagicMock()
            response.__enter__.return_value.status = 200
            response.__enter__.return_value.read.return_value = body
            responses.append(response)
        opener.open.side_effect = responses
        with patch.object(module.urllib.request, 'build_opener', return_value=opener):
            return module.probe('http://127.0.0.1:1')

    def test_expected_payloads(self):
        self.assertTrue(self.run_with([b'ip=1.2.3.4\n', b'{"info":{"name":"six","version":"1.17.0"}}', b'{"model_type":"gpt2"}'])['ok'])

    def test_http_200_wrong_payload_fails(self):
        result = self.run_with([b'CONNECT established', b'<html>error</html>', b'{}'])
        self.assertFalse(result['ok'])
        self.assertTrue(all(not r['ok'] for r in result['results']))

    def test_transport_failure_fails(self):
        opener = MagicMock()
        opener.open.side_effect = TimeoutError('injected timeout')
        with patch.object(module.urllib.request, 'build_opener', return_value=opener):
            self.assertFalse(module.probe('http://127.0.0.1:1')['ok'])
