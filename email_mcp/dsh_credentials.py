"""DSH owns accounts and passwords; only cursors are persisted here."""
from copy import deepcopy
import json
import os
import re

from .hosts import normalize_imap_host
from .service import EmailService


def take_environment():
    primary = os.environ.pop('ALCOR_EMAIL_CREDENTIAL', None)
    legacy = os.environ.pop('STELLA_EMAIL_CREDENTIAL', None)
    if primary is not None and legacy is not None and primary != legacy:
        raise ValueError('凭据环境配置冲突。')
    return primary if primary is not None else legacy


class DshEmailService(EmailService):
    def __init__(self, db_path, accounts, **kwargs):
        if not isinstance(accounts, list) or not 1 <= len(accounts) <= 20:
            raise ValueError('DSH 邮箱凭据无效。')
        self.accounts = []
        identities = set()
        for row in accounts:
            if not isinstance(row, dict) or set(row) != {'id', 'host', 'user', 'password', 'port', 'folder', 'enabled'}:
                raise ValueError('DSH 邮箱凭据无效。')
            if not isinstance(row['id'], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', row['id']) or row['id'] in identities:
                raise ValueError('DSH 邮箱 ID 无效。')
            for key, limit in (('user', 320), ('password', 4096), ('folder', 512)):
                if not isinstance(row[key], str) or not 0 < len(row[key].strip()) <= limit or any(c in row[key] for c in '\r\n\0'):
                    raise ValueError('DSH 邮箱凭据无效。')
            if type(row['port']) is not int or not 1 <= row['port'] <= 65535 or type(row['enabled']) is not bool:
                raise ValueError('DSH 邮箱连接参数无效。')
            identities.add(row['id'])
            self.accounts.append({**row, 'host': normalize_imap_host(row['host'])})
        super().__init__(db_path, **kwargs)

    @classmethod
    def from_environment(cls, db_path, **kwargs):
        return cls.from_raw(db_path, take_environment(), **kwargs)

    @classmethod
    def from_raw(cls, db_path, raw, **kwargs):
        try:
            value = json.loads(raw)
            if not isinstance(value, dict) or set(value) != {'accounts'}:
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError('请通过 DSH 邮件插件提供凭据。') from None
        return cls(db_path, value['accounts'], **kwargs)

    def _load_accounts(self, db=None):
        return deepcopy(self.accounts)

    def save_account(self, payload):
        raise PermissionError('请在 DSH 邮件插件中管理账号。')

    def delete_account(self, account_id):
        raise PermissionError('请在 DSH 邮件插件中管理账号。')

    def test_connection(self, payload):
        if not isinstance(payload, dict) or set(payload) != {'id'}:
            raise ValueError('只能检查已配置的邮箱。')
        return self._source(self._account(payload['id'])).check_connection()
