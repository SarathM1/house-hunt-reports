"""Wrap an HTML report in a password-protected shell using AES-GCM encryption."""
import base64
import hashlib
import json
import os
from pathlib import Path


def encrypt_report(html_path: Path, passphrase: str, out_path: Path | None = None) -> Path:
    out_path = out_path or html_path.with_name("index.html")
    content = html_path.read_text()

    salt = os.urandom(16)
    iv = os.urandom(12)
    key = hashlib.pbkdf2_hmac("sha256", passphrase.encode(), salt, 100000, dklen=32)

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(iv, content.encode(), None)

    payload = {
        "salt": base64.b64encode(salt).decode(),
        "iv": base64.b64encode(iv).decode(),
        "ct": base64.b64encode(ct).decode(),
    }

    shell = """<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>House Hunt Report (Protected)</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, sans-serif; background: #1a1a2e; height: 100vh; display: flex; justify-content: center; align-items: center; }
  .lock { text-align: center; color: #fff; }
  .lock h1 { font-size: 20px; margin-bottom: 16px; }
  .lock input { padding: 10px 16px; border: 2px solid #4ecdc4; border-radius: 8px; background: transparent; color: #fff; font-size: 16px; width: 220px; text-align: center; outline: none; }
  .lock input::placeholder { color: #666; }
  .lock button { margin-top: 12px; padding: 10px 32px; border: none; border-radius: 8px; background: #4ecdc4; color: #1a1a2e; font-size: 14px; font-weight: 600; cursor: pointer; display: block; margin-left: auto; margin-right: auto; }
  .lock .err { color: #ff6b6b; font-size: 13px; margin-top: 8px; min-height: 20px; }
</style>
</head><body>
<div class="lock" id="lock">
  <h1>Enter passphrase</h1>
  <input type="password" id="pw" placeholder="passphrase" autofocus>
  <button onclick="unlock()">Unlock</button>
  <div class="err" id="err"></div>
</div>
<script>
const D = """ + json.dumps(payload) + """;

async function unlock() {
  const pw = document.getElementById('pw').value;
  if (!pw) return;
  try {
    const enc = new TextEncoder();
    const salt = Uint8Array.from(atob(D.salt), c => c.charCodeAt(0));
    const iv = Uint8Array.from(atob(D.iv), c => c.charCodeAt(0));
    const ct = Uint8Array.from(atob(D.ct), c => c.charCodeAt(0));
    const keyMaterial = await crypto.subtle.importKey('raw', enc.encode(pw), 'PBKDF2', false, ['deriveKey']);
    const key = await crypto.subtle.deriveKey({name: 'PBKDF2', salt, iterations: 100000, hash: 'SHA-256'}, keyMaterial, {name: 'AES-GCM', length: 256}, false, ['decrypt']);
    const plain = await crypto.subtle.decrypt({name: 'AES-GCM', iv}, key, ct);
    const html = new TextDecoder().decode(plain);
    document.open(); document.write(html); document.close();
  } catch(e) { document.getElementById('err').textContent = 'Wrong passphrase'; }
}
document.getElementById('pw').addEventListener('keydown', e => { if (e.key === 'Enter') unlock(); });
</script>
</body></html>"""

    out_path.write_text(shell)
    print(f"Encrypted report: {out_path} ({len(content)} → {len(shell)} bytes)", flush=True)
    return out_path
