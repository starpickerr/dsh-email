import importlib,io,json,sys
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import Mock
import pytest
from email.message import EmailMessage as RfcMessage
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
BASE='https://elearning.fudan.edu.cn'
PASSWORD='campus-secret-77'
SECRET='imap-app-secret-9f3'
DRAFT={'host':'127.0.0.1','user':'ada@example.com','password':SECRET,'port':1,'folder':'INBOX'}
def _load_vendored():
    service=importlib.import_module('email_mcp.service')
    return service,importlib.import_module('email_mcp.imap')

def _raw(msgid, subject):
    msg = RfcMessage()
    msg["From"] = "Ada <ada@example.com>"
    msg["Subject"] = subject
    msg["Date"] = "Tue, 8 Sep 2026 22:00:00 +0000"
    msg["Message-ID"] = msgid
    msg.set_content("请确认合同")
    return msg.as_bytes()

class FakeImap:
    def __init__(self, messages, uidvalidity=b"77", folders=(b'(\\HasNoChildren) "/" "INBOX"', b'(\\Noselect) "/" "[Gmail]"')):
        self.messages = messages
        self.untagged_responses = {"UIDVALIDITY": [uidvalidity]}
        self.folders = list(folders)
        self.searches = []
        self.logged_out = False

    def capability(self):
        return "OK", [b"IMAP4rev1"]

    def list(self):
        return "OK", self.folders

    def select(self, folder, readonly=True):
        return ("OK", [b"2"]) if folder == "INBOX" else ("NO", [b"nope " + SECRET.encode()])

    def uid(self, command, *args):
        if command == "SEARCH":
            self.searches.append(args)
            floor = int(args[2].split(":")[0]) if args[1] == "UID" else 0
            return "OK", [" ".join(str(u) for u in sorted(self.messages) if u >= floor).encode()]
        return "OK", [(b"1 (BODY[] {n}", self.messages[int(args[0])]), b")"]

    def logout(self):
        self.logged_out = True

def _service(tmp_path, client):
    service_module, _ = _load_vendored()
    return service_module.EmailService(tmp_path / "email.db", opener=lambda: client)

def test_fetch_proposes_cursors_and_does_not_advance_until_committed(tmp_path):
    client = FakeImap({1: _raw("<a@x>", "旧邮件"), 2: _raw("<b@x>", "新邮件")})
    service = _service(tmp_path, client)
    account = service.save_account(DRAFT)
    first = service.fetch_messages(account["id"], since="2026-09-08T00:00:00Z")
    assert [i["source_id"] for i in first["items"]] == ["<a@x>", "<b@x>"]
    assert first["cursors"] == {"imap_uid": "2", "imap_uidvalidity": "77"} and first["errors"] == []
    assert first["account_id"] == account["source_account_id"] and client.logged_out
    assert "body" in first["items"][0]["payload"] and SECRET not in json.dumps(first)
    # Not committed: the same messages are offered again.
    assert len(service.fetch_messages(account["id"], since="2026-09-08T00:00:00Z")["items"]) == 2
    service.set_cursors(account["id"], first["cursors"])
    client.messages[3] = _raw("<c@x>", "更新")
    second = service.fetch_messages(account["id"])
    assert [i["source_id"] for i in second["items"]] == ["<c@x>"]
    assert second["cursors"]["imap_uid"] == "3"
    # UIDVALIDITY change discards the stale UID cursor.
    client.untagged_responses["UIDVALIDITY"] = [b"88"]
    assert len(service.fetch_messages(account["id"], since="2026-09-08T00:00:00Z")["items"]) == 3

def test_test_connection_and_folders_use_fake_server_and_hide_unselectable(tmp_path):
    client = FakeImap({})
    service = _service(tmp_path, client)
    checked = service.test_connection(DRAFT)
    assert checked["connected"] and checked["folder_accessible"]
    assert [f["name"] for f in checked["folders"]] == ["INBOX"]
    assert [f["name"] for f in service.list_folders(payload=DRAFT)["folders"]] == ["INBOX"]
    account = service.save_account(DRAFT)
    assert service.list_folders(account["id"])["selected"] == "INBOX"
    blocked = service.test_connection({**DRAFT, "folder": "Missing"})
    assert blocked["folder_accessible"] is False and SECRET not in blocked["message"]
    service.save_account({"id": account["id"], "folder": "Missing", "password": "********"})
    with pytest.raises(ValueError) as error:
        service.fetch_messages(account["id"])
    assert SECRET not in str(error.value)
