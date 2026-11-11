"""export + images in one go, then optionally rsync the export elsewhere.

Set WXMAC_SYNC_DEST (e.g. "myserver:~/wechat-mcp/data/wechat.sqlite") to
copy export/wechat.sqlite with rsync after a successful export. rsync
writes to a temp file and renames, so readers never see a half file.
"""
from __future__ import annotations

import os
import subprocess

from . import config, export, images


def run(no_images: bool = False, dest: str | None = None) -> int:
    export.run()
    if not no_images:
        images.run()
    dest = dest or os.environ.get("WXMAC_SYNC_DEST")
    if dest:
        return subprocess.call(["/usr/bin/rsync", "-az", "--partial", "--timeout=600",
                                config.export_db(), dest])
    return 0
