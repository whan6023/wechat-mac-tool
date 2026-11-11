"""Load / run the vendored wcdb-key-tool (MIT, see third_party/wcdb_key_tool)."""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys

from . import config


def load():
    path = config.key_tool_path()
    if not os.path.exists(path):
        sys.exit(f"wcdb_key_tool_macos.py not found at {path} (set WXMAC_KEY_TOOL)")
    spec = importlib.util.spec_from_file_location("wcdb_key_tool_macos", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


INSTRUCTIONS = """\
Database keys are extracted by the third-party wcdb-key-tool (MIT,
https://github.com/TANGandXUE/wcdb-key-tool), vendored at:
  {tool}

One-time setup (and again after WeChat auto-updates):
  xcode-select --install                     # provides lldb
  sudo codesign --force --deep --sign - /Applications/WeChat.app
  # restart WeChat

Extract keys (needs sudo; WeChat 4.1.10+ will ask you to log in again):
  wxmac keys extract
which runs, in {home}:
  sudo python3 {tool} extract --output {keys}

Keys stay on this Mac only:
  {keys}          database keys (from the step above)
  {imgkey}        16-byte image AES key (V2 .dat images), obtain separately
Both are git-ignored. Never commit, paste or share them.
"""


def instructions() -> str:
    return INSTRUCTIONS.format(tool=config.key_tool_path(), home=config.home(),
                               keys=config.keys_file(), imgkey=config.image_key_file())


def run(args: list[str]) -> int:
    """Run the key tool under sudo with cwd = WXMAC_HOME (its outputs are cwd-relative)."""
    os.makedirs(config.home(), exist_ok=True)
    cmd = ["sudo", sys.executable, config.key_tool_path(), *args]
    if args and args[0] == "extract" and "--output" not in args:
        cmd += ["--output", config.keys_file()]
    print("+", " ".join(cmd), file=sys.stderr)
    return subprocess.call(cmd, cwd=config.home())
