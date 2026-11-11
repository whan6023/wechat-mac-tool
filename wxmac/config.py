"""Paths and settings. Everything is overridable by environment variables.

Defaults keep the historical layout (~/wcdb-key-tool/...), so existing
LaunchAgents / scripts that read export/wechat.sqlite keep working.

Nothing here contains key material: keys are only ever read at runtime from
local files under WXMAC_HOME (or env vars), which are git-ignored.
"""
from __future__ import annotations

import glob
import os
import sys

WECHAT_FILES = os.path.expanduser(
    "~/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files"
)


def home() -> str:
    """Working dir holding keys and exports (default ~/wcdb-key-tool)."""
    return os.path.expanduser(os.environ.get("WXMAC_HOME", "~/wcdb-key-tool"))


def keys_file() -> str:
    return os.path.expanduser(os.environ.get("WXMAC_KEYS", os.path.join(home(), "all_keys.json")))


def image_key_file() -> str:
    return os.path.expanduser(os.environ.get("WXMAC_IMAGE_KEY_FILE", os.path.join(home(), "image_key.bin")))


def export_db() -> str:
    return os.path.expanduser(os.environ.get("WXMAC_EXPORT", os.path.join(home(), "export", "wechat.sqlite")))


def decrypted_dir() -> str:
    return os.path.expanduser(os.environ.get("WXMAC_DECRYPTED", os.path.join(home(), "daily")))


def images_dir() -> str:
    return os.path.expanduser(os.environ.get("WXMAC_IMAGES", os.path.join(home(), "export", "images")))


def account_dir() -> str:
    """The logged-in account folder under xwechat_files/.

    Set WXMAC_ACCOUNT_DIR to pin one. Otherwise auto-discover: every
    xwechat_files/*/ that has db_storage/, newest first.
    """
    env = os.environ.get("WXMAC_ACCOUNT_DIR")
    if env:
        return os.path.expanduser(env)
    cands = [d.rstrip("/") for d in glob.glob(os.path.join(WECHAT_FILES, "*/"))
             if os.path.isdir(os.path.join(d, "db_storage"))]
    if not cands:
        sys.exit(f"no WeChat account folder with db_storage/ under {WECHAT_FILES}; set WXMAC_ACCOUNT_DIR")
    cands.sort(key=lambda d: os.path.getmtime(os.path.join(d, "db_storage")), reverse=True)
    if len(cands) > 1:
        print(f"note: {len(cands)} account folders found, using the most recently active one "
              f"(set WXMAC_ACCOUNT_DIR to choose)", file=sys.stderr)
    return cands[0]


def db_storage() -> str:
    return os.path.join(account_dir(), "db_storage")


def attach_dir() -> str:
    return os.path.join(account_dir(), "msg", "attach")


def key_tool_path() -> str:
    """wcdb_key_tool_macos.py: env override, else the vendored copy."""
    env = os.environ.get("WXMAC_KEY_TOOL")
    if env:
        return os.path.expanduser(env)
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(here, "third_party", "wcdb_key_tool", "wcdb_key_tool_macos.py")


def which(name: str, *extra: str) -> str | None:
    import shutil
    p = shutil.which(name)
    if p:
        return p
    for d in ("/opt/homebrew/bin", "/usr/local/bin", *extra):
        c = os.path.join(d, name)
        if os.access(c, os.X_OK):
            return c
    return None
