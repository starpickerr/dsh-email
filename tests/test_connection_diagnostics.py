import imaplib
import json
import socket
import ssl
from unittest.mock import patch
import pytest
from email_mcp.server import connection_error_code
from email_mcp.imap import EmailSource


@pytest.mark.parametrize(('error','expected'),[
    (socket.gaierror('private-code dns detail'),'dns_error'),
    (ssl.SSLError('private-code ssl detail'),'tls_error'),
    (TimeoutError('private-code timeout'),'timeout'),
    (ConnectionRefusedError('private-code refused'),'connection_refused'),
    (imaplib.IMAP4.abort('private-code EOF'),'connection_lost'),
    (imaplib.IMAP4.error('private-code auth'),'auth_failed'),
    (OSError('private-code network'),'network_error'),
    (PermissionError('private-code denied'),'permission_denied'),
    (KeyError('private-code id'),'account_unavailable'),
    (ValueError('private-code config'),'invalid_config'),
    (RuntimeError('private-code unknown'),'query_failed'),
])
def test_connection_errors_are_classified_without_returning_remote_text(error,expected):
    assert connection_error_code(error)==expected
    assert 'private-code' not in connection_error_code(error)


def test_wrapped_connector_error_keeps_the_original_failure_kind():
    with patch('email_mcp.imap.imaplib.IMAP4_SSL',side_effect=socket.gaierror('private-code')):
        with pytest.raises(ValueError) as failure:
            EmailSource(host='imap.example.com',user='synthetic@example.com',password='private-code',port=993,folder='INBOX')._connect()
    assert connection_error_code(failure.value)=='dns_error'
