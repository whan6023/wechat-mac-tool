"""Incrementally decrypt WeChat 4.x (macOS) images.

msg/attach/<md5(chat_id)>/<yyyy-mm>/Img/<hash>[_h|_t].dat
  -> <images_dir>/<chat name>/<yyyy-mm>/<hash>.<ext>

.dat formats
  V2  header 07 08 'V2' 08 07, then <aes_len:u32le><xor_len:u32le>, 1 byte, body.
      body = AES-128-ECB(image key)[first block(s)] + plain middle + XOR tail.
  V1  same layout, fixed public AES key md5("0")[:16].
  old whole file XORed with one byte (detected from the image signature).

The XOR byte of V2 files is constant per account. It is derived at runtime
from thumbnails (*_t.dat are JPEGs, which end in FF D9), so it is never
stored or hardcoded. Earlier versions guessed it from the tail of JPG/PNG
only and used 0 for WeChat's own 'wxgf' (HEVC) images, which corrupted them.

wxgf images are converted to JPEG with ffmpeg (first HEVC frame) when
available; otherwise the .wxgf is kept.
"""
from __future__ import annotations

import collections
import glob
import hashlib
import os
import re
import sqlite3
import struct
import subprocess
import sys
import tempfile

from . import config

V1_KEY = hashlib.md5(b"0").hexdigest()[:16].encode()  # public WeChat V1 constant
V2_MAGIC = b"\x07\x08V2\x08\x07"
V1_MAGIC = b"\x07\x08V1\x08\x07"
SIGS = [(b"\xff\xd8\xff", "jpg"), (b"\x89PNG", "png"), (b"GIF8", "gif"),
        (b"RIFF", "webp"), (b"wxgf", "wxgf"), (b"BM", "bmp")]
HEVC_START = b"\x00\x00\x00\x01"


def load_image_key() -> bytes:
    env = os.environ.get("WXMAC_IMAGE_KEY")
    if env:
        return env.encode()[:16]
    path = config.image_key_file()
    try:
        with open(path, "rb") as f:
            key = f.read()[:16]
    except FileNotFoundError:
        sys.exit(f"image key not found: {path} (16-byte AES key; set WXMAC_IMAGE_KEY_FILE)")
    if len(key) != 16:
        sys.exit(f"image key in {path} must be 16 bytes")
    return key


def derive_xor(attach: str, sample: int = 400) -> int | None:
    """Per-account V2 XOR byte, from JPEG thumbnails: b[-2]^0xFF == b[-1]^0xD9."""
    env = os.environ.get("WXMAC_IMAGE_XOR")
    if env:
        return int(env, 0)
    votes: collections.Counter = collections.Counter()
    seen = 0
    for p in glob.iglob(os.path.join(attach, "*", "*", "Img", "*_t.dat")):
        try:
            with open(p, "rb") as f:
                head = f.read(6)
                f.seek(-2, os.SEEK_END)
                b = f.read(2)
        except OSError:
            continue
        if head != V2_MAGIC or len(b) != 2:
            continue
        if b[0] ^ 0xFF == b[1] ^ 0xD9:
            votes[b[1] ^ 0xD9] += 1
        seen += 1
        if seen >= sample:
            break
    if not votes:
        return None
    value, n = votes.most_common(1)[0]
    return value if n >= max(1, sum(votes.values()) // 2) else None


def ext_of(data: bytes) -> str | None:
    for sig, ext in SIGS:
        if data.startswith(sig):
            return ext
    return None


def _aes_ecb(key: bytes, data: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    d = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
    out = d.update(data) + d.finalize()
    pad = out[-1] if out else 0
    return out[:-pad] if 1 <= pad <= 16 else out


def _xor_plain(b: bytes) -> bytes | None:
    for sig, _ in SIGS:
        k = b[0] ^ sig[0]
        if all(b[i] ^ k == sig[i] for i in range(len(sig))):
            return bytes(x ^ k for x in b)
    return None


def decrypt(b: bytes, image_key: bytes, xor_byte: int | None) -> bytes | None:
    if b[:6] in (V2_MAGIC, V1_MAGIC):
        key = image_key if b[:6] == V2_MAGIC else V1_KEY
        aes_len, xor_len = struct.unpack("<II", b[6:14])
        body = b[15:]
        alen = (aes_len // 16 + 1) * 16
        xor_len = min(xor_len, max(0, len(body) - alen))
        head = _aes_ecb(key, body[:alen])
        mid = body[alen:len(body) - xor_len]
        tail = body[len(body) - xor_len:] if xor_len else b""
        out = head + mid
        if tail:
            kx = xor_byte
            if kx is None:  # fallback guess, only reliable for JPG/PNG
                kx = (tail[-1] ^ 0xD9 if out[:2] == b"\xff\xd8"
                      else tail[-1] ^ 0x82 if out[:4] == b"\x89PNG" else 0)
            out += bytes(x ^ kx for x in tail)
        return out
    return _xor_plain(b)


def wxgf_to_jpg(data: bytes, out_jpg: str) -> bool:
    ffmpeg = config.which("ffmpeg")
    i = data.find(HEVC_START)
    if not ffmpeg or i < 0:
        return False
    fd, tmp = tempfile.mkstemp(suffix=".hevc", dir=os.path.dirname(out_jpg))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data[i:])
        r = subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-f", "hevc", "-i", tmp,
                            "-frames:v", "1", out_jpg], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ok = r.returncode == 0 and os.path.exists(out_jpg) and os.path.getsize(out_jpg) > 0
        if not ok and os.path.exists(out_jpg):
            os.remove(out_jpg)
        return ok
    finally:
        os.remove(tmp)


def scan_qr(path: str) -> list[str]:
    zbar = config.which("zbarimg")
    if not zbar:
        return []
    r = subprocess.run([zbar, "-q", "--raw", path], capture_output=True, text=True)
    return [x for x in r.stdout.splitlines() if x.strip()]


def chat_names(export_db: str) -> dict[str, str]:
    names: dict[str, str] = {}
    if not os.path.exists(export_db):
        return names
    try:
        c = sqlite3.connect(f"file:{export_db}?mode=ro", uri=True)
        for cid, name in c.execute("select chat_id, chat from chat"):
            if cid:
                names[hashlib.md5(cid.encode()).hexdigest()] = name or cid
        c.close()
    except sqlite3.Error as e:
        print("chat names unavailable:", e, file=sys.stderr)
    return names


_safe = lambda s: re.sub(r"[/:\0]", "_", s)[:80]  # noqa: E731


def run(out_dir: str | None = None, chat_hash: str | None = None, month: str | None = None,
        keep_wxgf: bool = False, qr: bool = False) -> dict:
    attach = config.attach_dir()
    out_dir = out_dir or config.images_dir()
    image_key = load_image_key()
    xor_byte = derive_xor(attach)
    if xor_byte is None:
        print("warning: could not derive XOR byte from thumbnails; falling back to JPG/PNG guess",
              file=sys.stderr)
    names = chat_names(config.export_db())
    stats = collections.Counter()
    qr_rows = []
    for root, _, files in os.walk(attach):
        if os.path.basename(root) != "Img":
            continue
        rel = os.path.relpath(root, attach).split(os.sep)
        chash, mon = rel[0], (rel[1] if len(rel) > 2 else "")
        if chat_hash and chash != chat_hash:
            continue
        if month and mon != month:
            continue
        best: dict[str, str] = {}
        for f in files:  # prefer the full-size _h.dat over the normal .dat; skip thumbnails
            if not f.endswith(".dat") or f.endswith("_t.dat"):
                continue
            h = f[:-4].replace("_h", "")
            if f.endswith("_h.dat") or h not in best:
                best[h] = f
        od = os.path.join(out_dir, _safe(names.get(chash, chash)), mon)
        existing = set(os.listdir(od)) if os.path.isdir(od) else set()
        for h, f in best.items():
            if any(x.startswith(h + ".") for x in existing):
                stats["skipped"] += 1
                continue
            src = os.path.join(root, f)
            try:
                with open(src, "rb") as fh:
                    data = decrypt(fh.read(), image_key, xor_byte)
                ext = ext_of(data) if data else None
                if not ext:
                    stats["failed"] += 1
                    continue
                os.makedirs(od, exist_ok=True)
                op = os.path.join(od, f"{h}.{ext}")
                if ext == "wxgf":
                    jpg = os.path.join(od, f"{h}.jpg")
                    if wxgf_to_jpg(data, jpg):
                        stats["wxgf_converted"] += 1
                        if not keep_wxgf:
                            op = jpg
                            data = None
                    else:
                        stats["wxgf_kept"] += 1
                if data is not None:
                    with open(op, "wb") as fo:
                        fo.write(data)
                st = os.stat(src)
                os.utime(op, (st.st_mtime, st.st_mtime))
                stats["decrypted"] += 1
                if qr and op.endswith((".jpg", ".png")):
                    for code in scan_qr(op):
                        qr_rows.append((op, code))
            except Exception as e:  # keep going on single bad files
                stats["failed"] += 1
                if os.environ.get("WXMAC_DEBUG"):
                    print(f"fail {src}: {e}", file=sys.stderr)
    if qr:
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "qr.tsv"), "a", encoding="utf-8") as fq:
            for op, code in qr_rows:
                fq.write(f"{op}\t{code}\n")
        stats["qr_codes"] = len(qr_rows)
    print("decrypted {decrypted}, already {skipped}, failed {failed}, wxgf->jpg {wxgf_converted}, "
          "wxgf kept {wxgf_kept}".format(**{k: stats.get(k, 0) for k in
                                           ("decrypted", "skipped", "failed", "wxgf_converted", "wxgf_kept")})
          + (f", qr codes {stats['qr_codes']} (see qr.tsv)" if qr else ""))
    return dict(stats)
