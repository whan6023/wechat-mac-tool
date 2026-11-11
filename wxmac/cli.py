"""wxmac command line."""
from __future__ import annotations

import argparse
import sys

from . import __version__


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="wxmac", description="Local WeChat 4.x (macOS) export toolkit")
    p.add_argument("--version", action="version", version=f"wxmac {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    k = sub.add_parser("keys", help="show key setup, or run the key tool (extract|decrypt ...)")
    k.add_argument("args", nargs=argparse.REMAINDER, help="passed to wcdb_key_tool_macos.py (sudo)")

    e = sub.add_parser("export", help="decrypt DBs and rebuild export/wechat.sqlite")
    e.add_argument("--out", help="output sqlite (default $WXMAC_HOME/export/wechat.sqlite)")
    e.add_argument("--decrypted-dir", help="where decrypted DB copies go (default $WXMAC_HOME/daily)")

    i = sub.add_parser("images", help="decrypt images into export/images/<chat>/<month>/")
    i.add_argument("--out", help="output dir (default $WXMAC_HOME/export/images)")
    i.add_argument("--chat", help="only this chat folder (md5 of chat id)")
    i.add_argument("--month", help="only this month, YYYY-MM")
    i.add_argument("--keep-wxgf", action="store_true", help="also keep the raw .wxgf next to the .jpg")
    i.add_argument("--qr", action="store_true", help="scan decoded images with zbarimg into <out>/qr.tsv")

    s = sub.add_parser("sync", help="export + images, then rsync to $WXMAC_SYNC_DEST if set")
    s.add_argument("--no-images", action="store_true")
    s.add_argument("--dest", help="rsync destination (overrides WXMAC_SYNC_DEST)")

    sub.add_parser("mcp", help="run the read-only MCP server (needs mcp<2)")
    sub.add_parser("paths", help="print the resolved paths (no key contents)")

    a = p.parse_args(argv)
    if a.cmd == "keys":
        from . import keytool
        if not a.args:
            print(keytool.instructions())
            return
        sys.exit(keytool.run(a.args))
    if a.cmd == "export":
        from . import export
        export.run(a.out, a.decrypted_dir)
    elif a.cmd == "images":
        from . import images
        images.run(a.out, a.chat, a.month, a.keep_wxgf, a.qr)
    elif a.cmd == "sync":
        from . import sync
        sys.exit(sync.run(a.no_images, a.dest))
    elif a.cmd == "mcp":
        from . import mcp_server
        mcp_server.run()
    elif a.cmd == "paths":
        import os
        from . import config
        for name in ("home", "keys_file", "image_key_file", "export_db", "decrypted_dir",
                     "images_dir", "key_tool_path"):
            v = getattr(config, name)()
            print(f"{name:15} {v}{'' if os.path.exists(v) else '  (missing)'}")
        try:
            config.account_dir()
            print(f"{'account_dir':15} found")
        except SystemExit as err:
            print(f"{'account_dir':15} {err}")


if __name__ == "__main__":
    main()
