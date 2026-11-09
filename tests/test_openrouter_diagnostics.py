"""Offline coverage of security denials, fallback behavior and credential redaction."""
import json, os, socket, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import httpx
from openai import PermissionDeniedError, APIStatusError
from orchestrator import config, llm


class OpenRouterDiagnostics(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.paths = patch.object(config, 'DATA', self.folder)
        self.paths.start()
        self.net = patch.object(socket.socket, 'connect', side_effect=AssertionError('Network forbidden'))
        self.net.start()

    def tearDown(self):
        self.net.stop(); self.paths.stop(); self.temp.cleanup()

    def error(self, status=403, body=None, headers=None, text=None):
        request = httpx.Request('POST', 'https://openrouter.ai/api/v1/chat/completions?secret=not-saved',
                                headers={'Authorization':'Bearer request-secret'})
        response = httpx.Response(status, json=body, text=text, request=request, headers=headers)
        cls = PermissionDeniedError if status == 403 else APIStatusError
        return cls('fixture failure', response=response, body=body)

    def test_error_receipt_preserves_route_and_redacts_credentials(self):
        secret = 'private-test-credential-123'
        body = {'error':{'message':secret,'metadata':{'provider_name':'Provider','api_key':secret}},
                'openrouter_metadata':{'region':'ams','pipeline':[{'name':'guardrail'}]}}
        error = self.error(body=body, headers={'cf-ray':'fixture-AMS','set-cookie':secret,'x-request-id':'req-123'})
        with patch.dict(os.environ, {'OPENROUTER_API_KEY':secret}):
            llm._log_api_error(error,'test-model','test')
        receipt = json.loads(next((self.folder/'llm_log').glob('*.json')).read_text(encoding='utf-8'))
        encoded = json.dumps(receipt)
        self.assertNotIn(secret,encoded)
        self.assertNotIn('request-secret',encoded)
        self.assertNotIn('not-saved',encoded)
        self.assertNotIn('set-cookie',receipt['headers'])
        self.assertEqual(receipt['provider'],'Provider')
        self.assertEqual(receipt['route']['region'],'ams')
        self.assertEqual(receipt['headers']['cf-ray'],'fixture-AMS')

    def test_non_json_error_is_preserved(self):
        error=self.error(body=None,text='Blocked by edge',headers={'content-type':'text/plain'})
        self.assertEqual(llm.error_details(error)['body'],'Blocked by edge')

    def test_edge_security_denial_does_not_retry_other_models(self):
        error=self.error(body={'success':False,'error':'Access denied by security policy.'})
        create=Mock(side_effect=error)
        client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        with patch.object(llm,'client',return_value=client), self.assertRaises(PermissionDeniedError) as caught:
            llm.ask_vision('fixture',[b'png'],model=config.LLM_MODEL_VISION_CHEAP)
        self.assertIs(caught.exception,error)
        self.assertEqual(create.call_count,1)
        receipt=json.loads(next((self.folder/'llm_log').glob('*.json')).read_text(encoding='utf-8'))
        self.assertEqual(receipt['status'],403)

    def test_provider_failure_still_allows_normal_fallback(self):
        error=self.error(status=400,body={'error':{'code':400,'message':'Provider unavailable'}})
        response=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"checks":[]}'),finish_reason='stop')],usage=None)
        create=Mock(side_effect=[error,response])
        client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        with patch.object(llm,'client',return_value=client):
            result=llm.ask_vision('fixture',[b'png'],model='test/alternative')
        self.assertEqual(result,{'checks':[]})
        self.assertEqual(create.call_count,2)
        self.assertEqual(create.call_args.kwargs['model'],config.LLM_MODEL_VISION)

    def test_logging_failure_does_not_hide_api_denial(self):
        error=self.error(body={'success':False,'error':'Access denied by security policy.'})
        create=Mock(side_effect=error)
        client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        with patch.object(llm,'client',return_value=client), patch.object(config,'write',side_effect=OSError('Disk full')):
            with self.assertRaises(PermissionDeniedError) as caught:
                llm.ask_vision('fixture',[b'png'])
        self.assertIs(caught.exception,error)


if __name__ == '__main__': unittest.main()
