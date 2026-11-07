# dsh-email

An independent local stdio MCP server for multiple IMAP accounts. It provides account and source configuration, mailbox queries and consumer-controlled cursors. IMAP selection is read-only; the server does not provide SMTP sending or message deletion. The capability description is distributed in `email_mcp/capability.json`.

## Install and start

Python 3.11 or newer is required. From the repository directory:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python mcp_server.py --data-dir /absolute/private/email --user-id local-default
```

Configure your MCP client to launch the last command over stdio, replacing the Python, script and data paths with absolute paths on your machine. `--data-dir` is required. Use a separate private data directory and process per identity. Startup paths are trusted local configuration and cannot be overridden by tool calls. The optional `--legacy-dir` reads an earlier settings directory for non-destructive adoption; back up and verify its source first.

## Configure and use

In a trusted local MCP client, use `save_account` to configure an IMAP account and `list_accounts` to inspect public settings; passwords are masked. Enter credentials only through a trusted settings interface, not in the repository or chat. In ordinary standalone mode the SQLite database can contain the account password in plaintext; private file permissions do not encrypt it. Protect the data directory and its backups. Use `list_sources`, `list_folders`, `test_connection` and `fetch_messages` as needed. Fetching proposes cursors; a consumer calls `set_cursors` only after successful consumption. The client must restrict access to account-management and write operations: MCP read-only annotations are not access control.

## DSH credential mode

A compatible host can start the service with `--dsh-credentials`, supply accounts using its credential provider and manage the connection. This mode exposes `list_accounts`, `list_sources`, `get_cursors`, `fetch_messages`, `test_connection` and `list_folders`; it does not expose account management or cursor writes. The transient `STELLA_EMAIL_CREDENTIAL` environment entry is removed after parsing. This mode ignores legacy accounts and cannot be combined with `--legacy-dir` or `--hosted-connector`. Do not put real passwords in a shell command. This repository provides the server mode; verify host plugin distribution and compatibility separately.

## Verification

Run the offline credential-mode tests with:

```sh
.venv/bin/python -B -m unittest tests.test_dsh_credentials -v
```

These tests use synthetic accounts. Actual mailbox access requires user authorization, correct IMAP settings and a reachable provider; an offline test does not validate a real account.
