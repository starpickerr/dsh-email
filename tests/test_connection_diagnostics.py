import imaplib
import json
import socket
import ssl
from unittest.mock import patch
import pytest
from email_mcp.server import connection_error_code, ERROR_MESSAGES
from email_mcp.imap import EmailSource, EmailError, _select_folder


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


def test_query_errors_do_not_misidentify_folder_or_protocol_failure_as_login():
    assert connection_error_code(EmailError('private-code', code='folder_denied'), query=True) == 'folder_denied'
    assert connection_error_code(imaplib.IMAP4.error('private-code SEARCH failed'), query=True) == 'mail_server_error'
    assert connection_error_code(EmailError('private-code', code='auth_failed'), query=True) == 'auth_failed'
    assert all(len(message) > 20 and 'private-code' not in message for message in ERROR_MESSAGES.values())


def test_folder_connection_abort_is_not_reported_as_folder_permission():
    from unittest.mock import Mock
    client = Mock()
    client.select.side_effect = imaplib.IMAP4.abort('private-code EOF')
    with pytest.raises(imaplib.IMAP4.abort):
        _select_folder(client, 'INBOX', 'private-code')
