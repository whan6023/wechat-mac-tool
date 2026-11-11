"""Decrypt the local WeChat databases and rebuild export/wechat.sqlite.

Uses keys already saved in all_keys.json. Needs no sudo and does not log you
out. Keep WeChat open so today's messages are flushed to db_storage.

Output schema (unchanged):
  message(id, ts, chat_id, chat, sender, kind, text)
  chat(chat_id, chat, n, last_ts)
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time

from . import config, keytool

MAGIC = b"\x28\xb5\x2f\xfd"  # zstd


def log(msg: str) -> None:
    print(msg, flush=True)


def _text_of(zstd, blob, compressed: int) -> str:
    import zstandard
    if blob is None:
        return ""
    raw = blob if isinstance(blob, (bytes, bytearray)) else str(blob).encode("utf-8", "replace")
    if compressed == 4 or raw[:4] == MAGIC:
        try:
            raw = zstd.decompress(raw)
        except zstandard.ZstdError:
            return ""
    return raw.decode("utf-8", "replace")


def decrypt_needed(db_dir: str, out_dir: str, keys_path: str) -> None:
    kt = keytool.load()
    with open(keys_path, encoding="utf-8") as f:
        keys = kt._strip_key_metadata(json.load(f))
    want = []
    msg_dir = os.path.join(db_dir, "message")
    for name in sorted(os.listdir(msg_dir)):
        if re.fullmatch(r"message_\d+\.db", name):
            want.append(os.path.join("message", name))
    contact = os.path.join("contact", "contact.db")
    if os.path.exists(os.path.join(db_dir, contact)):
        want.append(contact)
    ok = 0
    for rel in want:
        info = kt._get_key_info(keys, rel)
        src = os.path.join(db_dir, rel)
        if not info or not os.path.exists(src):
            log(f"skip {rel}")
            continue
        dst = os.path.join(out_dir, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        log(f"decrypt {rel}")
        if kt._decrypt_database(src, dst, bytes.fromhex(info["enc_key"])):
            ok += 1
        else:
            raise SystemExit(f"decrypt failed: {rel}")
    if ok == 0:
        raise SystemExit("no databases decrypted")
    log(f"decrypted {ok}")


def build(dec_dir: str, export_path: str) -> None:
    import zstandard
    zstd = zstandard.ZstdDecompressor()
    contact: dict[str, str] = {}
    cpath = os.path.join(dec_dir, "contact", "contact.db")
    if os.path.exists(cpath):
        cc = sqlite3.connect(f"file:{cpath}?immutable=1", uri=True)
        for username, remark, nick in cc.execute("SELECT username, remark, nick_name FROM contact"):
            contact[username] = (remark or nick or username or "").strip()
        cc.close()
    disp = lambda u: contact.get(u) or u  # noqa: E731

    os.makedirs(os.path.dirname(export_path), exist_ok=True)
    tmp = export_path + ".new"
    if os.path.exists(tmp):
        os.remove(tmp)
    out = sqlite3.connect(tmp)
    out.execute("PRAGMA journal_mode=OFF")
    out.execute("PRAGMA synchronous=OFF")
    out.execute("CREATE TABLE message (id INTEGER PRIMARY KEY, ts INTEGER, chat_id TEXT, "
                "chat TEXT, sender TEXT, kind TEXT, text TEXT)")
    out.execute("CREATE TABLE chat (chat_id TEXT PRIMARY KEY, chat TEXT, n INTEGER, last_ts INTEGER)")
    ins = "INSERT INTO message (ts, chat_id, chat, sender, kind, text) VALUES (?,?,?,?,?,?)"
    n = 0
    msg_dir = os.path.join(dec_dir, "message")
    for name in sorted(os.listdir(msg_dir)):
        if not re.fullmatch(r"message_\d+\.db", name):
            continue
        con = sqlite3.connect(f"file:{os.path.join(msg_dir, name)}?immutable=1", uri=True)
        if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='Name2Id'").fetchone():
            con.close()
            continue
        idmap = dict(con.execute("SELECT rowid, user_name FROM Name2Id"))
        by_hash = {hashlib.md5(u.encode()).hexdigest(): u for u in idmap.values()}
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'Msg_%'")]
        batch = []
        for table in tables:
            chat_user = by_hash.get(table[4:])
            if chat_user is None:
                continue
            chat = disp(chat_user)
            rows = con.execute(f"SELECT create_time, real_sender_id, local_type, message_content, "
                               f"WCDB_CT_message_content FROM {table}")
            for ts, sender_id, kind, blob, ct in rows:
                body = _text_of(zstd, blob, ct or 0).strip()
                if not body:
                    continue
                batch.append((ts or 0, chat_user, chat, disp(idmap.get(sender_id, "")), str(kind or ""), body))
                if len(batch) >= 5000:
                    out.executemany(ins, batch)
                    n += len(batch)
                    batch.clear()
        if batch:
            out.executemany(ins, batch)
            n += len(batch)
        con.close()
        log(f"{name} running {n}")
    out.execute("INSERT INTO chat (chat_id, chat, n, last_ts) "
                "SELECT chat_id, max(chat), count(*), max(ts) FROM message GROUP BY chat_id")
    out.execute("CREATE INDEX message_chat_ts ON message(chat, ts)")
    out.execute("CREATE INDEX message_text ON message(text)")
    out.commit()
    out.close()
    os.replace(tmp, export_path)
    log(f"wrote {export_path} rows={n} at {time.strftime('%Y-%m-%d %H:%M:%S')}")


def run(export_path: str | None = None, dec_dir: str | None = None, retries: int = 3) -> None:
    export_path = export_path or config.export_db()
    dec_dir = dec_dir or config.decrypted_dir()
    db_dir = config.db_storage()
    # right after the Mac wakes, listdir can hit EINTR: retry
    for attempt in range(retries):
        try:
            decrypt_needed(db_dir, dec_dir, config.keys_file())
            build(dec_dir, export_path)
            return
        except InterruptedError:
            if attempt == retries - 1:
                raise
            time.sleep(20)
