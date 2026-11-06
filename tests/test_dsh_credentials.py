import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from email_mcp.dsh_credentials import DshEmailService
from email_mcp.server import create_server

ACCOUNT = {'id': 'synthetic', 'host': 'imap.example.com', 'user': 'test@example.com',
           'password': 'synthetic-private-secret', 'port': 993, 'folder': 'INBOX', 'enabled': True}


class DshMailTest(unittest.TestCase):
    def test_explicit_accounts_only_without_secret_persistence(self):
        with tempfile.TemporaryDirectory() as root:
            db = Path(root) / 'email.db'
            with patch.dict(os.environ, {'STELLA_EMAIL_CREDENTIAL': json.dumps({'accounts': [ACCOUNT]}), 'IMAP_PASSWORD': 'old-secret'}):
                service = DshEmailService.from_environment(db)
                self.assertNotIn('STELLA_EMAIL_CREDENTIAL', os.environ)
                state = service.list_accounts()
                self.assertEqual(state['mailboxes'][0]['id'], 'synthetic')
                self.assertNotIn(ACCOUNT['password'], json.dumps(state))
                self.assertNotIn(ACCOUNT['password'].encode(), db.read_bytes())
                self.assertNotIn(b'old-secret', db.read_bytes())
                service.set_cursors('synthetic', {'uid': '3'})
                self.assertEqual(service.get_cursors('synthetic'), {'uid': '3'})
                with self.assertRaises(PermissionError): service.save_account({'password': 'forged'})
                with self.assertRaises(PermissionError): service.delete_account('synthetic')
                with self.assertRaises(ValueError): service.test_connection({'host': 'elsewhere', 'id': 'synthetic'})
            for raw in ('', '{}', 'bad', json.dumps({'accounts': [{**ACCOUNT, 'port': True}]})):
                with patch.dict(os.environ, {'STELLA_EMAIL_CREDENTIAL': raw}):
                    with self.assertRaises(ValueError): DshEmailService.from_environment(db)
                    self.assertNotIn('STELLA_EMAIL_CREDENTIAL', os.environ)
            with self.assertRaises(ValueError): create_server(root, legacy_dir=Path(root), dsh_credentials=True)
            with self.assertRaises(ValueError): create_server(root, hosted_connector=True, dsh_credentials=True)


class DshMailWireTest(unittest.IsolatedAsyncioTestCase):
    async def test_readonly_tools_and_forged_writes_refused(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as data:
            params = StdioServerParameters(command=sys.executable,
                args=[str(root / 'mcp_server.py'), '--data-dir', data, '--dsh-credentials'],
                env={'HOME': data, 'STELLA_EMAIL_CREDENTIAL': json.dumps({'accounts': [ACCOUNT]}), 'PYTHONDONTWRITEBYTECODE': '1'})
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await asyncio.wait_for(session.initialize(), 10)
                    inventory = await session.list_tools()
                    self.assertEqual({t.name for t in inventory.tools}, {'list_accounts', 'list_sources', 'get_cursors', 'fetch_messages', 'test_connection', 'list_folders'})
                    self.assertTrue(all(t.annotations.readOnlyHint for t in inventory.tools))
                    self.assertNotIn(ACCOUNT['password'], inventory.model_dump_json())
                    result = await session.call_tool('list_sources', {})
                    self.assertEqual(result.structuredContent['value'][0]['mailbox_id'], 'synthetic')
                    result = await session.call_tool('save_account', {'payload': ACCOUNT})
                    self.assertTrue(result.isError)
                    result = await session.call_tool('list_folders', {'account_id': 'synthetic', 'payload': ACCOUNT})
                    self.assertTrue(result.isError)
            self.assertNotIn(ACCOUNT['password'].encode(), (Path(data) / 'email.db').read_bytes())


    async def test_connection_failure_is_structured_and_never_returns_server_secrets(self):
        root = Path(__file__).resolve().parents[1]
        script = """import asyncio,imaplib
from email_mcp.imap import EmailSource
from email_mcp.server import main
def denied(self):
    try: raise imaplib.IMAP4.error('LOGIN private-server-secret rejected')
    except imaplib.IMAP4.error as cause: raise ValueError('wrapped private-server-secret') from cause
EmailSource._connect=denied
asyncio.run(main())
"""
        with tempfile.TemporaryDirectory() as data:
            params = StdioServerParameters(command=sys.executable,
                args=['-c', script, '--data-dir', data, '--dsh-credentials'], cwd=str(root),
                env={'HOME': data, 'STELLA_EMAIL_CREDENTIAL': json.dumps({'accounts': [ACCOUNT]}), 'PYTHONDONTWRITEBYTECODE': '1'})
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await asyncio.wait_for(session.initialize(), 10)
                    result = await session.call_tool('test_connection', {'payload': {'id': ACCOUNT['id']}})
                    self.assertFalse(result.isError)
                    self.assertEqual(result.structuredContent['value'], {'connected': False, 'folder_accessible': False, 'error_code': 'auth_failed'})
                    self.assertNotIn('private-server-secret', result.model_dump_json())
                    self.assertNotIn(ACCOUNT['password'], result.model_dump_json())


if __name__ == '__main__': unittest.main()
