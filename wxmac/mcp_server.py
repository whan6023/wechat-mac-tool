"""Read-only MCP server over export/wechat.sqlite (opened with SQLite mode=ro).

Run:  uv run --with "mcp<2" wxmac mcp      (or: pip install 'wxmac[mcp]'; wxmac mcp)
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime

from . import config


def build_server(db: str | None = None):
    from mcp.server.fastmcp import FastMCP

    db = db or config.export_db()
    mcp = FastMCP("wechat")

    def conn() -> sqlite3.Connection:
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        c.row_factory = sqlite3.Row
        return c

    def ts(s: str | None) -> int | None:
        return int(datetime.fromisoformat(s).timestamp()) if s else None

    def fmt_t(t) -> str | None:
        return datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M") if t else None

    def fmt(rows) -> list[dict]:
        return [{"time": fmt_t(r["ts"]), "chat": r["chat"], "sender": r["sender"],
                 "kind": r["kind"], "text": r["text"]} for r in rows]

    @mcp.tool()
    def export_status() -> dict:
        """How many messages/chats the local WeChat export holds and when it was last refreshed."""
        with conn() as c:
            n, last = c.execute("select count(*), max(ts) from message").fetchone()
            chats = c.execute("select count(*) from chat").fetchone()[0]
        return {"messages": n, "chats": chats, "latest_message": fmt_t(last),
                "file_modified": fmt_t(os.path.getmtime(db))}

    @mcp.tool()
    def list_chats(query: str = "", limit: int = 50) -> list[dict]:
        """List WeChat chats (people and groups), most recent first. `query` filters by chat name substring."""
        with conn() as c:
            rows = c.execute("select chat, n, last_ts from chat where chat like ? order by last_ts desc limit ?",
                             (f"%{query}%", min(limit, 500))).fetchall()
        return [{"chat": r["chat"], "messages": r["n"], "last": fmt_t(r["last_ts"])} for r in rows]

    @mcp.tool()
    def search_messages(keyword: str, chat: str = "", since: str = "", until: str = "",
                        limit: int = 100) -> list[dict]:
        """Search message text for `keyword`. Optional `chat` (name substring), `since`/`until` (YYYY-MM-DD or ISO datetime). Newest first."""
        sql = "select ts, chat, sender, kind, text from message where text like ?"
        args: list = [f"%{keyword}%"]
        if chat:
            sql += " and chat like ?"; args.append(f"%{chat}%")
        if since:
            sql += " and ts >= ?"; args.append(ts(since))
        if until:
            sql += " and ts < ?"; args.append(ts(until))
        sql += " order by ts desc limit ?"; args.append(min(limit, 1000))
        with conn() as c:
            return fmt(c.execute(sql, args).fetchall())

    @mcp.tool()
    def read_chat(chat: str, since: str = "", until: str = "", limit: int = 200) -> list[dict]:
        """Read messages of one chat (exact name, or substring if no exact match), oldest-to-newest within the window. Defaults to the latest `limit` messages."""
        with conn() as c:
            exact = c.execute("select 1 from chat where chat = ?", (chat,)).fetchone()
            sql = "select ts, chat, sender, kind, text from message where " + ("chat = ?" if exact else "chat like ?")
            args: list = [chat if exact else f"%{chat}%"]
            if since:
                sql += " and ts >= ?"; args.append(ts(since))
            if until:
                sql += " and ts < ?"; args.append(ts(until))
            sql += " order by ts desc limit ?"; args.append(min(limit, 2000))
            rows = c.execute(sql, args).fetchall()
        return fmt(reversed(rows))

    return mcp


def run() -> None:
    build_server().run()
