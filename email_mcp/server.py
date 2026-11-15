"""Independent local MCP server. Run with --data-dir and optional --legacy-dir."""

import argparse
import imaplib
import socket
import ssl
import asyncio
import json
import inspect
import logging
from pathlib import Path
import threading

import anyio
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, TextContent, Tool, ToolAnnotations, Request, Result
from . import __version__
from .service import EmailService
from .imap import EmailError


class HostedRequest(Request):
    params: dict


DESCRIPTIONS = {
    "list_courses": "查询 eLearning 可访问课程的 ID 和名称。账号由设置管理，不接收凭证。",
    "fetch": "读取课程公告、作业、测验、成绩和文件元数据；since/until 为时间窗口，offset/limit 分页。",
    "list_files": "查询已选课程文件；可按课程、文件 ID 和扩展名筛选，不下载文件。",
    "sync_files": "下载已选课程课件到配置目录。保留本地文件；支持 managed/courseware 布局、筛选和重复同步。",
    "list_accounts": "查询已配置邮箱及其账号 ID；不返回密码。",
    "list_sources": "查询已启用的邮件简报来源。",
    "fetch_messages": "只读获取指定邮箱的邮件及建议游标；消费成功后才能提交游标，不自动标为已读。",
}

TOOL_TITLES = {'list_accounts': '查询邮箱账号', 'list_sources': '查询邮件来源',
               'fetch_messages': '获取邮件'}


def parameter_schema(name):
    if name in {"payload", "cursors"}:
        return {"type": "object"}
    if name in {"course_ids", "file_ids", "file_extensions"}:
        return {"type": ["array", "null"], "items": {"type": "string"}}
    if name in {"offset", "limit", "lookback_days"}:
        return {"type": "integer"}
    if name == "refresh_existing_content":
        return {"type": "boolean"}
    if name == "layout":
        return {"type": "string", "enum": ["managed", "courseware"]}
    return (
        {"type": ["string", "null"]}
        if name in {"since", "until"}
        else {"type": "string"}
    )


ERROR_MESSAGES = {
    'dns_error': 'IMAP 地址解析失败，尚未验证授权码。请检查服务器地址、DNS、代理及网络。',
    'tls_error': 'IMAP TLS 连接失败。请检查系统时间、SSL 端口、证书及代理，不要关闭证书验证。',
    'timeout': 'IMAP 连接或读取超时。请检查网络、代理及 SSL 端口；超时不能证明授权码错误或审批被拒绝。',
    'connection_refused': 'IMAP 服务器拒绝连接。请检查服务器地址、SSL 端口及网络。',
    'connection_lost': 'IMAP 连接被服务器中断。请检查网络与服务状态后重试。',
    'auth_failed': 'IMAP 登录被服务器拒绝。请确认已开启 IMAP，并使用有效的客户端授权码。',
    'folder_denied': 'IMAP 已登录，但服务器拒绝读取文件夹。请测试连接并选择服务器返回的文件夹，检查账号的 IMAP 访问权限。',
    'mail_server_error': 'IMAP 服务器未能完成邮件查询。请检查邮箱服务状态及文件夹权限；不能据此认定授权码错误。',
    'network_error': 'IMAP 网络连接失败。请检查网络、DNS、代理与 SSL 端口。',
    'permission_denied': '邮件资源访问或操作系统连接被拒绝。请核对账号的有效资源范围及系统网络权限；此回执不能证明 DSH 审批被拒绝。',
    'account_unavailable': '邮箱账号不存在或已移除。请刷新账号列表并使用实际账号 ID。',
    'invalid_config': '邮箱设置或查询参数无效。请检查账号 ID、启用状态、IMAP 设置及时间范围。',
    'query_failed': '邮件查询发生未分类错误，未返回完整结果。请检查插件状态与日志，不要推断为审批拒绝或更改授权码。',
}


def connection_error_code(error, *, query=False):
    # Connector exceptions wrap socket/IMAP errors; never publish exception text.
    for _ in range(4):
        if isinstance(error, EmailError):
            return error.code
        cause = error.__cause__ or error.__context__
        if cause is None or cause is error:
            break
        error = cause
    for kind, code in (
        (socket.gaierror, 'dns_error'), (ssl.SSLError, 'tls_error'),
        (TimeoutError, 'timeout'), (ConnectionRefusedError, 'connection_refused'),
        (imaplib.IMAP4.abort, 'connection_lost'), (imaplib.IMAP4.error, 'mail_server_error' if query else 'auth_failed'),
        (PermissionError, 'permission_denied'), (OSError, 'network_error'),
        (KeyError, 'account_unavailable'), (ValueError, 'invalid_config'),
    ):
        if isinstance(error, kind):
            return code
    return 'query_failed'


def create_server(data_dir, legacy_dir=None, user_id="local-default", *, hosted_connector=False, dsh_credentials=False):
    if dsh_credentials:
        from .dsh_credentials import take_environment
        raw_credentials = take_environment()
    if dsh_credentials and (hosted_connector or legacy_dir is not None):
        raise ValueError('DSH 凭据模式不读取旧账号或使用旧 Core 连接。')
    data_dir = Path(data_dir).expanduser().resolve()
    if not hosted_connector:
        data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    methods = json.loads(Path(__file__).with_name("methods.json").read_text())
    dsh_accounts = None
    if dsh_credentials:
        from .dsh_credentials import DshEmailService
        dsh_accounts = DshEmailService.from_raw(data_dir / 'email.db', raw_credentials).accounts
        methods = {name: spec for name, spec in methods.items() if name in {
            'list_accounts', 'list_sources', 'get_cursors', 'fetch_messages', 'test_connection', 'list_folders'}}
        methods['list_folders'] = {**methods['list_folders'], 'params': ['account_id']}
    server = Server("email", version=__version__)

    @server.list_tools()
    async def list_tools():
        return [
            Tool(
                name=name,
                title=TOOL_TITLES.get(name),
                description=DESCRIPTIONS.get(name, f"Email: {name}"),
                inputSchema={
                    "type": "object",
                    "properties": {
                        key: parameter_schema(key) for key in spec["params"]
                    },
                    "required": [
                        key
                        for key, value in inspect.signature(
                            getattr(EmailService, name)
                        ).parameters.items()
                        if key != "self" and value.default is inspect.Parameter.empty
                    ],
                    "additionalProperties": False,
                },
                annotations=ToolAnnotations(
                    readOnlyHint=spec["read_only"],
                    destructiveHint=not spec["read_only"],
                ),
            )
            for name, spec in methods.items()
        ]

    @server.call_tool(validate_input=not hosted_connector)
    async def call_tool(name, arguments):
        if name not in methods:
            raise ValueError("Unknown tool")
        if not isinstance(arguments, dict) or set(arguments) - set(
            methods[name]["params"]
        ):
            raise ValueError("Unknown tool parameters")
        if hosted_connector:
            if arguments:
                raise PermissionError('Hosted mailbox arguments are owned by Core')
            result = await server.request_context.session.send_request(
                HostedRequest(method='stella/email/invoke', params={'requestId': server.request_context.request_id}),
                Result,
            )
            value = result.model_dump(mode='json', exclude_none=True)
            return CallToolResult(content=[TextContent(type='text', text=json.dumps(value, ensure_ascii=False))],
                                  structuredContent=value)
        meta = server.request_context.meta
        scope = getattr(meta, "resourceScope", None) if meta else None
        resources = None
        if scope is not None:
            if (
                not isinstance(scope, dict)
                or scope.get("userId") != user_id
                or not isinstance(scope.get("resources"), list)
                or any(
                    not isinstance(row, dict)
                    or set(row) != {"kind", "id"}
                    or not all(
                        isinstance(value, str) and value for value in row.values()
                    )
                    for row in scope["resources"]
                )
            ):
                raise PermissionError("Invalid request resource scope")
            resources = scope["resources"]
        cancel = threading.Event()

        def invoke():
            if dsh_credentials:
                service = DshEmailService(data_dir / 'email.db', dsh_accounts, user_id=user_id, authorized_resources=resources)
            else:
                service = EmailService(data_dir / "email.db",
                    legacy_mailbox_path=legacy_dir / "mailbox.json" if legacy_dir else None,
                    user_id=user_id, authorized_resources=resources)
            value = getattr(service, name)(**arguments)
            return {"value": value}

        try:
            value = await anyio.to_thread.run_sync(invoke, abandon_on_cancel=True)
            return CallToolResult(
                content=[
                    TextContent(type="text", text=json.dumps(value, ensure_ascii=False))
                ],
                structuredContent=value,
            )
        except Exception as error:
            cancel.set()
            if not dsh_credentials:
                raise
            if name == 'test_connection':
                value = {'value': {'connected': False, 'folder_accessible': False, 'error_code': connection_error_code(error)}}
                return CallToolResult(content=[TextContent(type='text', text=json.dumps(value))], structuredContent=value)
            code = connection_error_code(error, query=True)
            if code not in ERROR_MESSAGES:
                code = 'query_failed'
            return CallToolResult(isError=True, content=[TextContent(type='text', text=json.dumps(
                {'error_code': code, 'message': ERROR_MESSAGES[code]}, ensure_ascii=False))])
        except BaseException:
            cancel.set()
            raise

    return server


async def main():
    parser = argparse.ArgumentParser(description="email local stdio MCP")
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--legacy-dir", type=Path)
    parser.add_argument("--user-id", default="local-default")
    parser.add_argument('--hosted-connector', action='store_true')
    parser.add_argument('--dsh-credentials', action='store_true')
    args = parser.parse_args()
    server = create_server(args.data_dir, args.legacy_dir, args.user_id, hosted_connector=args.hosted_connector, dsh_credentials=args.dsh_credentials)
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def cli():
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main())


if __name__ == "__main__":
    cli()
