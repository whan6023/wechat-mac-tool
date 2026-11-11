# Third-party: wcdb-key-tool (macOS)

`wcdb_key_tool_macos.py` is copied **unmodified** from
<https://github.com/TANGandXUE/wcdb-key-tool> (commit `79f1b5b92e12c66aa281b4a60a3c478b5f547dfa`,
git blob `5113a7929af2ef0647d6ea4636b0171b83b2fbfb`).

Copyright (c) 2025 CloudDreamAI / TANGandXUE. Licensed under the MIT License, see [`LICENSE`](LICENSE).

`wxmac` imports its `_decrypt_database`, `_get_key_info` and `_strip_key_metadata`
helpers for `wxmac export`, and runs it for `wxmac keys extract`.
