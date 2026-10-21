"""A face-verification web app with Flask, including a tiny HTML page.

    pip install "verifyface[flask]"
    python examples/06_web_flask.py            # → http://127.0.0.1:5000

Developer: Kaustav Kanti Ray
"""

from __future__ import annotations

import verifyface as vf
from verifyface.integrations.flask_ext import init_app

try:
    from flask import Flask, jsonify, request
except ImportError:  # pragma: no cover
    raise SystemExit('Flask is not installed. Run: pip install "verifyface[flask]"')

app = Flask(__name__)
verifier = init_app(app, url_prefix="/face", verifier=vf.Verifier(vault="demo-vault"))

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>verifyface demo</title>
<style>
 body{font-family:system-ui,sans-serif;background:#0b1020;color:#e9eefc;margin:0;padding:40px}
 .card{max-width:560px;margin:auto;background:#141b33;border:1px solid #26314f;border-radius:16px;padding:24px}
 h1{font-size:20px;margin:0 0 4px} p.sub{color:#9aa7c7;margin:0 0 18px;font-size:13px}
 input,button{font-size:14px;padding:10px 12px;border-radius:10px;border:1px solid #26314f;background:#0d1428;color:#e9eefc}
 button{background:linear-gradient(140deg,#6c8cff,#8aa2ff);color:#08122e;font-weight:600;cursor:pointer;border:0}
 .row{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px}
 pre{background:#0d1428;border:1px solid #26314f;border-radius:10px;padding:14px;font-size:12.5px;overflow:auto}
 footer{margin-top:18px;color:#9aa7c7;font-size:12px;text-align:center}
</style></head>
<body><div class="card">
  <h1>verifyface demo</h1>
  <p class="sub">Offline face verification · Developer: Kaustav Kanti Ray</p>
  <form id="f">
    <div class="row"><input name="name" placeholder="Name" required></div>
    <div class="row"><input type="file" name="file" accept="image/*" required></div>
    <div class="row"><button>Verify</button></div>
  </form>
  <pre id="out">Result appears here…</pre>
  <footer><a href="/face/people" style="color:#9fb2ee">/face/people</a> ·
          <a href="https://github.com/iamkkronly/verifyface" style="color:#9fb2ee">GitHub</a></footer>
</div>
<script>
document.getElementById('f').addEventListener('submit', async (e) => {
  e.preventDefault();
  const form = new FormData(e.target);
  const res = await fetch('/face/verify', {method:'POST', body:form});
  const data = await res.json();
  document.getElementById('out').textContent =
    (data.matched ? 'VERIFIED' : 'NOT verified') + '\\n\\n' + JSON.stringify(data, null, 2);
});
</script></body></html>
"""


@app.get("/")
def index():
    return PAGE


@app.get("/health")
def health():
    return jsonify({"ok": True, "developer": vf.__author__, "version": vf.__version__})


if __name__ == "__main__":
    print(f"{vf.BANNER}\nOpen http://127.0.0.1:5000")
    app.run(debug=False, port=5000)
