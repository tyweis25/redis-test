"""
Demo hub - one web page linking to every demo script in this repo.

Two kinds of demos live here:

1. One-shot scripts that print their output and exit: redis_test.py, the
   pubsub_publisher.py/pubsub_subscriber.py pair, agent_memory_demo.py, and
   langcache_demo.py. Clicking "Run" executes them as subprocesses (using
   this same Python interpreter/venv) and shows their console output
   inline on this page.

2. Long-running Flask demos that need a server to stay up to be useful:
   app.py, sessions_demo.py, rate_limit_demo.py. Clicking "Start" launches
   the app's own Flask server in a background thread on its usual port
   (5000/5001/5002) without touching those files, and this page shows a
   few example requests you can try against it.

Install:
    pip3 install flask redis   (same requirements.txt as the rest of the repo)

Run:
    python3 demo_hub.py
    open http://localhost:5050
"""

import os
import socket
import subprocess
import sys
import threading
import time
from html import escape

from flask import Flask, redirect, request, url_for

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HUB_PORT = 5050

app = Flask(__name__)

# Imported as modules (not run as __main__), so their own `app.run(...)`
# calls never fire - we start each Flask app ourselves, on demand, below.
import app as cache_aside_module          # noqa: E402  (app.py)
import sessions_demo as sessions_module   # noqa: E402
import rate_limit_demo as rate_limit_module  # noqa: E402

SERVERS = {
    "cache_aside": {
        "title": "Cache-Aside Caching",
        "file": "app.py",
        "module": cache_aside_module,
        "port": 5000,
        "description": "Caches a slow \"database\" lookup in Redis so repeat requests are fast.",
        "try_it": [
            ("GET", "/health"),
            ("GET", "/users/1"),
            ("GET", "/users/1"),
            ("DELETE", "/cache/users/1"),
        ],
    },
    "sessions": {
        "title": "Redis-Backed Sessions",
        "file": "sessions_demo.py",
        "module": sessions_module,
        "port": 5001,
        "description": "Stores login sessions in Redis instead of signed cookies.",
        "try_it": [
            ("POST", "/login", '{"username": "ty"}'),
            ("GET", "/profile"),
            ("POST", "/logout"),
        ],
    },
    "rate_limit": {
        "title": "Rate Limiting",
        "file": "rate_limit_demo.py",
        "module": rate_limit_module,
        "port": 5002,
        "description": "Fixed-window rate limiting backed by a Redis counter.",
        "try_it": [
            ("GET", "/api/data"),
        ],
    },
}

SCRIPTS = {
    "redis_test": {
        "title": "Basic Redis Connectivity",
        "file": "redis_test.py",
        "description": "PING, string/list/hash ops, TTL, and server INFO against Redis Cloud.",
    },
    "agent_memory": {
        "title": "Redis Cloud Agent Memory",
        "file": "agent_memory_demo.py",
        "description": "Stores/reads session and long-term memory via the Agent Memory service.",
    },
    "langcache": {
        "title": "Redis LangCache Semantic Caching",
        "file": "langcache_demo.py",
        "description": "Saves a prompt/response pair and finds it again via semantic search.",
    },
}

_lock = threading.Lock()
_started = {key: False for key in SERVERS}


def _port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _start_server(key):
    info = SERVERS[key]
    with _lock:
        if _started[key] or _port_in_use(info["port"]):
            _started[key] = True
            return False  # already running

        def _serve():
            try:
                info["module"].app.run(host="0.0.0.0", port=info["port"], debug=False, use_reloader=False)
            except Exception as exc:  # pragma: no cover - background thread
                print(f"[demo_hub] {key} server stopped: {exc}", file=sys.stderr)

        threading.Thread(target=_serve, daemon=True, name=f"server-{key}").start()
        _started[key] = True
        # Give the Flask dev server a moment to bind before anyone follows a link.
        for _ in range(20):
            if _port_in_use(info["port"]):
                break
            time.sleep(0.1)
        return True


def _run_subprocess(*args, timeout=30):
    return subprocess.run(
        [sys.executable, *args],
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _run_pubsub_pair():
    import signal

    subscriber = subprocess.Popen(
        [sys.executable, "pubsub_subscriber.py"],
        cwd=BASE_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    time.sleep(1.5)  # let the subscriber finish SUBSCRIBE-ing before we publish

    try:
        publisher = _run_subprocess("pubsub_publisher.py", timeout=15)
        pub_output = publisher.stdout + publisher.stderr
    finally:
        subscriber.send_signal(signal.SIGINT)
        try:
            sub_stdout, sub_stderr = subscriber.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            subscriber.kill()
            sub_stdout, sub_stderr = subscriber.communicate()

    sub_output = sub_stdout + sub_stderr
    combined = (
        "=== pubsub_subscriber.py (started first, ran in background) ===\n"
        f"{sub_output}\n"
        "\n=== pubsub_publisher.py ===\n"
        f"{pub_output}"
    )
    return combined, 0


PAGE_STYLE = """
<style>
  :root { color-scheme: light dark; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    max-width: 920px; margin: 0 auto; padding: 2.5rem 1.5rem 4rem;
    background: #0f1115; color: #e7e9ee;
  }
  h1 { font-size: 1.7rem; margin-bottom: .25rem; }
  h2 { font-size: 1.1rem; margin: 2.5rem 0 1rem; color: #9aa4b2; text-transform: uppercase; letter-spacing: .06em; }
  p.lede { color: #9aa4b2; margin-top: 0; }
  .card {
    background: #171a21; border: 1px solid #262a33; border-radius: 12px;
    padding: 1.25rem 1.5rem; margin-bottom: 1rem;
  }
  .card h3 { margin: 0 0 .35rem; font-size: 1.05rem; }
  .card p { margin: 0 0 .9rem; color: #b7c0cc; font-size: .92rem; }
  .card code.file { color: #7fd0ff; font-size: .82rem; }
  form { display: inline; }
  button, .open-link {
    background: #3b82f6; color: white; border: none; border-radius: 8px;
    padding: .5rem 1rem; font-size: .88rem; cursor: pointer; text-decoration: none;
    display: inline-block; margin-right: .5rem; margin-top: .25rem;
  }
  button:hover, .open-link:hover { background: #2563eb; }
  button.secondary { background: #2a2f3a; }
  button.secondary:hover { background: #3a4152; }
  .running-badge {
    display: inline-block; background: #16351f; color: #4ade80; border: 1px solid #245a2f;
    border-radius: 999px; padding: .15rem .65rem; font-size: .78rem; margin-left: .5rem;
  }
  .try-it { margin-top: .75rem; font-size: .85rem; }
  .try-it code {
    display: block; background: #0b0d11; border-radius: 6px; padding: .4rem .6rem;
    margin: .25rem 0; color: #d1d5db; overflow-x: auto;
  }
  .banner {
    background: #16351f; border: 1px solid #245a2f; color: #baf3c8;
    padding: .75rem 1rem; border-radius: 8px; margin-bottom: 1.5rem; font-size: .9rem;
  }
  pre {
    background: #0b0d11; border: 1px solid #262a33; border-radius: 10px;
    padding: 1rem; overflow-x: auto; font-size: .85rem; line-height: 1.45;
    white-space: pre-wrap; word-break: break-word;
  }
  a.back { color: #7fd0ff; text-decoration: none; font-size: .9rem; }
  a.back:hover { text-decoration: underline; }
</style>
"""


def render_index(message=None):
    server_cards = []
    for key, info in SERVERS.items():
        running = _started[key] or _port_in_use(info["port"])
        badge = '<span class="running-badge">running on :%d</span>' % info["port"] if running else ""
        try_it_lines = []
        for entry in info["try_it"]:
            method, path = entry[0], entry[1]
            body = entry[2] if len(entry) > 2 else None
            if method == "GET":
                cmd = f"curl http://localhost:{info['port']}{path}"
            elif body:
                cmd = (
                    f"curl -X {method} http://localhost:{info['port']}{path} "
                    f"-H \"Content-Type: application/json\" -d '{body}'"
                )
            else:
                cmd = f"curl -X {method} http://localhost:{info['port']}{path}"
            try_it_lines.append(f"<code>{escape(cmd)}</code>")

        action = (
            f'<a class="open-link" href="http://localhost:{info["port"]}/" target="_blank">Open</a>'
            if running
            else f'<form method="post" action="{url_for("start_server", key=key)}">'
            f'<button type="submit">Start server</button></form>'
        )

        server_cards.append(f"""
        <div class="card">
          <h3>{escape(info['title'])} {badge}</h3>
          <p>{escape(info['description'])} <code class="file">{escape(info['file'])}</code></p>
          {action}
          <div class="try-it">{''.join(try_it_lines)}</div>
        </div>
        """)

    script_cards = []
    for key, info in SCRIPTS.items():
        script_cards.append(f"""
        <div class="card">
          <h3>{escape(info['title'])}</h3>
          <p>{escape(info['description'])} <code class="file">{escape(info['file'])}</code></p>
          <form method="post" action="{url_for('run_script', key=key)}">
            <button type="submit">Run</button>
          </form>
        </div>
        """)

    script_cards.append(f"""
    <div class="card">
      <h3>Pub/Sub Notifications</h3>
      <p>Publishes 4 messages while a subscriber listens live.
      <code class="file">pubsub_publisher.py</code> + <code class="file">pubsub_subscriber.py</code></p>
      <form method="post" action="{url_for('run_script', key='pubsub')}">
        <button type="submit">Run</button>
      </form>
    </div>
    """)

    banner = f'<div class="banner">{escape(message)}</div>' if message else ""

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Redis Demos</title>{PAGE_STYLE}</head>
<body>
  <h1>Redis Demos</h1>
  <p class="lede">All demos run against the Redis Cloud database configured in <code class="file">redis_config.py</code>.</p>
  {banner}
  <h2>One-shot scripts</h2>
  {''.join(script_cards)}
  <h2>Long-running servers</h2>
  {''.join(server_cards)}
</body></html>"""


def render_result(title, output, returncode=None):
    status = f" (exit code {returncode})" if returncode not in (None, 0) else ""
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{escape(title)} - Redis Demos</title>{PAGE_STYLE}</head>
<body>
  <a class="back" href="{url_for('index')}">&larr; Back to demos</a>
  <h1>{escape(title)}{escape(status)}</h1>
  <pre>{escape(output) if output.strip() else '(no output)'}</pre>
</body></html>"""


@app.route("/")
def index():
    return render_index(message=request.args.get("msg"))


@app.route("/start/<key>", methods=["POST"])
def start_server(key):
    if key not in SERVERS:
        return redirect(url_for("index", msg=f"Unknown server: {key}"))
    started = _start_server(key)
    info = SERVERS[key]
    msg = (
        f"Started {info['title']} on http://localhost:{info['port']}"
        if started
        else f"{info['title']} is already running on http://localhost:{info['port']}"
    )
    return redirect(url_for("index", msg=msg))


@app.route("/run/<key>", methods=["POST"])
def run_script(key):
    if key == "pubsub":
        output, returncode = _run_pubsub_pair()
        return render_result("Pub/Sub Notifications", output, returncode)

    if key not in SCRIPTS:
        return redirect(url_for("index", msg=f"Unknown script: {key}"))

    info = SCRIPTS[key]
    try:
        result = _run_subprocess(info["file"], timeout=30)
    except subprocess.TimeoutExpired:
        return render_result(info["title"], "Script timed out after 30 seconds.", 1)

    output = result.stdout + result.stderr
    return render_result(info["title"], output, result.returncode)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=HUB_PORT, debug=False)
