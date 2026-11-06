# email MCP

The public capability introduction is maintained in `email_mcp/capability.json` and shipped as package data. Stella reads this metadata without importing or starting the server; bundled builds include it under `_internal/email_mcp/`.

Independent, local stdio MCP server using the official Python SDK (`mcp==1.30.0`, MIT). No Stella import, Plugin Runtime or proprietary remote backend is required. Business code and state belong to this repository; extracted from Stella-Plugins f5eed89 without changing existing account, cursor, cookie or manifest formats.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python mcp_server.py --data-dir /absolute/private/email --user-id local-default
```

Use Python 3.11 or newer. The optional `--legacy-dir` points to the former briefing settings directory for one-time, non-destructive adoption. Existing migrated data is used in place; original downloaded files and previous source files are not removed. Use a separate data directory and process per identity. Startup paths are trusted local configuration; tools cannot override them.

The server publishes ordinary MCP tools, with read-only annotations, strict argument names, structured results and protocol errors. Call `list_accounts` to inspect public settings. Credentials are masked. Configure accounts through `save_account`; settings operations are intended for the local owner. Stella excludes these management operations from Agent discovery and routes its authenticated settings/briefing through the same managed MCP connection. Stella keeps its execution permissions; independent clients must enforce their own policy.

This server keeps multi-account IMAP compatibility and consumer-controlled checkpoints: fetching only proposes cursors, and `set_cursors` commits after successful consumption. IMAP SELECT remains read-only. Existing IMAP accounts are not silently switched to Gmail OAuth, SMTP, sending or message deletion. A Gmail-specific third-party MCP is not a drop-in replacement for these persisted IMAP/briefing contracts; adding provider backends can happen independently in this repository without duplicating mail business in Stella Core.

## DSH native credentials

The independently installable `@stella/mail` bundle starts this server with `--dsh-credentials`. DSH owns a native `stella-email/accounts` credential record; the transient `STELLA_EMAIL_CREDENTIAL` environment entry is removed immediately after parsing. This mode ignores legacy database accounts, legacy migration arguments and IMAP environment defaults. Only cursor data is persisted here. No Keychain provider is accessed or changed.

This mode exposes six read-only tools: `list_accounts`, `list_sources`, `get_cursors`, `fetch_messages`, `test_connection` and `list_folders`. Connection tests accept only an existing account ID; mailbox management and cursor writes are not published. The briefing consumer supplies and commits its own checkpoints. Ordinary standalone mode and hosted compatibility remain available, but cannot be combined with DSH credential mode.

Configure accounts in the DSH plugin settings, then explicitly authorize Stella conversation tools or select briefing sources. Installing or saving accounts does not fetch message bodies. Validation: `.venv/bin/python -B -m unittest tests.test_dsh_credentials -v`; synthetic accounts only.

Stella starts this server with `--hosted-connector`. In this mode the sandboxed
process neither opens the account database nor receives passwords. Each tool
call asks Core to complete the single pending operation through
`stella/email/invoke`; the request carries only its parent request ID. Core owns
the arguments, current resource checks, original SQLite/Keychain transaction and
revocable IMAPS connection, and reuses the pinned mailbox business modules.
This extension is specific to Stella; independent clients use the ordinary mode
above and supply their own credential and transport policy.
