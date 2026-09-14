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
        # None of these apps define a route for "/", so "Open" must point at
        # a real endpoint - otherwise it 404s ("Not Found") every time.
        "open_path": "/health",
        "description": (
            "Simulates a slow 2-second database lookup and caches the result in Redis "
            "for 30 seconds (L2) plus a process-local L1. DELETE drops Redis and "
            "PUBLISHes on demo:cache:invalidate so every replica's L1 goes stale. "
            "A SET NX lock keeps a thundering herd to a single slow fill."
        ),
        "how": [
            "Start the server, then Open /health to confirm Redis is connected.",
            "Open /users/1 twice: first call ~2s (source: database), second ~0.06s (source: cache).",
            "GET /cache/l1/1 shows the process-local copy; DELETE notifies other replicas via Pub/Sub.",
            "A Redis SET NX lock keeps a thundering herd to a single slow fill.",
        ],
        "try_it": [
            ("GET", "/health"),
            ("GET", "/users/1"),
            ("GET", "/cache/l1/1"),
            ("DELETE", "/cache/users/1"),
        ],
    },
    "sessions": {
        "title": "Redis-Backed Sessions",
        "file": "sessions_demo.py",
        "module": sessions_module,
        "port": 5001,
        "open_path": "/",
        "description": (
            "Stores login sessions in Redis instead of signed cookies. The browser only "
            "gets an opaque session_id cookie; username and login time live server-side "
            "and can be revoked instantly. Opening /profile with no cookie returns "
            "{\"error\": \"not logged in\"} — that's expected until you log in."
        ),
        "how": [
            "Start the server, then Open / for the HTML login page, or use Log in (username defaults to ty).",
            "A new tab shows the session; Open /profile for the JSON from Redis.",
            "Click Log out, then Open again: back to not logged in (Redis key deleted).",
            "The curl commands below do the same flow with a cookie jar. Optional: pass ttl=60.",
            "POST /presence/ty (optional ?ttl=30) then GET /presence — expires if heartbeats stop.",
        ],
        "try_it": [
            ("POST", "/login", '{"username": "ty"}'),
            ("GET", "/profile"),
            ("POST", "/logout"),
            ("POST", "/presence/ty", '{"ttl": 30}'),
            ("GET", "/presence"),
        ],
        # Real HTML forms (not curl) so you can log in/out from the browser
        # and then click "Open" to see /profile reflect it - opens each
        # response in a new tab so the hub page itself isn't navigated away.
        "live_forms": [
            {"label": "Log in", "action_path": "/login", "fields": [("username", "ty")]},
            {"label": "Log out", "action_path": "/logout", "fields": []},
        ],
    },
    "rate_limit": {
        "title": "Rate Limiting",
        "file": "rate_limit_demo.py",
        "module": rate_limit_module,
        "port": 5002,
        "open_path": "/api/data",
        "description": (
            "Rate limiter: 5 requests per 30-second window. Default is a fixed clock "
            "slot (INCR). Add ?algo=sliding for a sorted-set window that cannot be "
            "gamed at a slot boundary. Override client/limit/window with "
            "X-Client-Id, X-RateLimit-Limit, X-RateLimit-Window."
        ),
        "how": [
            "Start the server, then click Open (or fire /api/data) six or more times quickly.",
            "First five responses: requests_remaining counts down from 4 to 0.",
            "Sixth and later: {\"error\": \"rate limit exceeded\"} until the 30s window resets.",
            "Try /api/data?algo=sliding to see the ZSET sliding window.",
            "POST /api/charge with Idempotency-Key: a retry returns the same charge_id.",
        ],
        "try_it": [
            ("GET", "/api/data"),
            ("GET", "/api/data?algo=sliding"),
            ("POST", "/api/charge", '{"amount": 12}'),
        ],
    },
}

SCRIPTS = {
    "redis_test": {
        "title": "Basic Redis Connectivity",
        "file": "redis_test.py",
        "description": (
            "Sanity-check against Redis Cloud: PING, string set/get, INCR, list RPUSH/"
            "LRANGE, hash HSET/HGETALL, a key with a 10-second TTL, and INFO server. "
            "Keys live under the demo: prefix so they cannot collide with other demos."
        ),
        "how": [
            "Click Run, or from a terminal: python3 redis_test.py",
            "Expect: PING True, counter 2, list [a, b, c], hash {name: Ty}, Redis 8.x.",
            "Also prints a leaderboard, HyperLogLog uniques, Bloom membership, and due delayed jobs.",
        ],
    },
    "agent_memory": {
        "title": "Redis Cloud Agent Memory",
        "file": "agent_memory_demo.py",
        "description": (
            "Talks to Redis Cloud Agent Memory (a separate HTTPS service, not the Redis "
            "database). Adds a short-term session event, reads it back, stores a long-term "
            "fact, then searches it. Needs AGENT_MEMORY_API_KEY set in redis_config.py."
        ),
        "how": [
            "Fill in AGENT_MEMORY_API_KEY in redis_config.py (from cloud.redis.io Agent Memory).",
            "Click Run, or: python3 agent_memory_demo.py",
            "A placeholder key fails cleanly with 403; a real key prints session + search results.",
            "The script then deletes the session and searches long-term again — the fact remains.",
        ],
    },
    "streams": {
        "title": "Redis Streams (durable vs Pub/Sub)",
        "file": "streams_demo.py",
        "description": (
            "Writes messages to a Redis Stream, then a consumer group reads them. "
            "Unlike Pub/Sub, the messages are still there even if nobody was listening."
        ),
        "how": [
            "Click Run, or: python3 streams_demo.py",
            "Expect XADD of 3 jobs, worker-1 reads then 'crashes' (no XACK), worker-2 claims and ACKs.",
        ],
    },
    "langcache": {
        "title": "Redis LangCache Semantic Caching",
        "file": "langcache_demo.py",
        "description": (
            "Managed semantic cache for LLM prompts: stores a prompt/response pair, then "
            "searches with a differently-worded question and still finds it by meaning "
            "(~96% similarity), not exact text. Needs LANGCACHE_API_KEY in redis_config.py."
        ),
        "how": [
            "Fill in LANGCACHE_API_KEY in redis_config.py (from the Redis Cloud LangCache page).",
            "Click Run, or: python3 langcache_demo.py",
            "A real key returns an entry_id on set, then a CacheEntry with SearchStrategy.SEMANTIC.",
            "It also writes the same prompt under tenant=acme and tenant=globex to show isolation.",
        ],
    },
    "search": {
        "title": "JSON, Search, and Vectors",
        "file": "search_demo.py",
        "description": (
            "Redis 8 modules on this Cloud DB: store a catalog as JSON, FT.SEARCH by "
            "TAG, then KNN over a tiny embedding. That's 'what is similar in my corpus?' "
            "LangCache is 'did we already answer this prompt?'"
        ),
        "how": [
            "Click Run, or: python3 search_demo.py",
            "Expect two fruit docs from @category:{fruit}, and red apple first on KNN [1,0,0,0].",
        ],
    },
}

PUBSUB = {
    "title": "Pub/Sub Notifications",
    "files": "pubsub_publisher.py + pubsub_subscriber.py",
    "description": (
        "Fire-and-forget broadcast: the subscriber listens on the 'demo:notifications' channel, "
        "then the publisher sends 4 messages. Each is delivered live to whoever is "
        "subscribed at that moment. If nobody is listening, the message is gone "
        "(unlike a queue or Redis Streams)."
    ),
    "how": [
        "Click Run here — the hub starts the subscriber, waits, runs the publisher, then stops the subscriber.",
        "Or in two terminals: python3 pubsub_subscriber.py first, then python3 pubsub_publisher.py.",
        "Expect 4 'Received: ...' lines on the subscriber and 'delivered to 1 subscriber(s)' on the publisher.",
    ],
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
                info["module"].app.run(
                    host="0.0.0.0",
                    port=info["port"],
                    debug=False,
                    use_reloader=False,
                    threaded=True,
                )
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
  .card p { margin: 0 0 .55rem; color: #b7c0cc; font-size: .92rem; }
  .card code.file { color: #7fd0ff; font-size: .82rem; }
  .how {
    margin: 0 0 .9rem; padding-left: 1.1rem; color: #9aa4b2; font-size: .85rem;
  }
  .how li { margin: .2rem 0; }
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


def _how_html(steps):
    if not steps:
        return ""
    items = "".join(f"<li>{escape(step)}</li>" for step in steps)
    return f"<ol class=\"how\">{items}</ol>"


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
            f'<a class="open-link" href="http://localhost:{info["port"]}{info["open_path"]}" target="_blank">Open</a>'
            if running
            else f'<form method="post" action="{url_for("start_server", key=key)}">'
            f'<button type="submit">Start server</button></form>'
        )

        live_forms_html = ""
        if running and info.get("live_forms"):
            forms = []
            for form in info["live_forms"]:
                field_inputs = "".join(
                    f'<input type="text" name="{escape(name)}" value="{escape(default)}" '
                    f'style="border-radius:6px;border:1px solid #262a33;background:#0b0d11;'
                    f'color:#e7e9ee;padding:.4rem .55rem;font-size:.85rem;margin-right:.4rem;width:110px;">'
                    for name, default in form["fields"]
                )
                forms.append(
                    f'<form method="post" action="http://localhost:{info["port"]}{form["action_path"]}" '
                    f'target="_blank" style="display:inline-flex;align-items:center;margin-right:.5rem;">'
                    f'{field_inputs}<button type="submit" class="secondary">{escape(form["label"])}</button></form>'
                )
            live_forms_html = f'<div style="margin-top:.6rem;">{"".join(forms)}</div>'

        server_cards.append(f"""
        <div class="card">
          <h3>{escape(info['title'])} {badge}</h3>
          <p>{escape(info['description'])} <code class="file">{escape(info['file'])}</code></p>
          {_how_html(info.get("how"))}
          {action}
          {live_forms_html}
          <div class="try-it">{''.join(try_it_lines)}</div>
        </div>
        """)

    script_cards = []
    for key, info in SCRIPTS.items():
        script_cards.append(f"""
        <div class="card">
          <h3>{escape(info['title'])}</h3>
          <p>{escape(info['description'])} <code class="file">{escape(info['file'])}</code></p>
          {_how_html(info.get("how"))}
          <form method="post" action="{url_for('run_script', key=key)}">
            <button type="submit">Run</button>
          </form>
        </div>
        """)

    script_cards.append(f"""
    <div class="card">
      <h3>{escape(PUBSUB['title'])}</h3>
      <p>{escape(PUBSUB['description'])} <code class="file">{escape(PUBSUB['files'])}</code></p>
      {_how_html(PUBSUB.get("how"))}
      <form method="post" action="{url_for('run_script', key='pubsub')}">
        <button type="submit">Run</button>
      </form>
    </div>
    """)

    banner = f'<div class="banner">{escape(message)}</div>' if message else ""
    eval_card = f"""
    <div class="card">
      <h3>Eval suite</h3>
      <p>Scored checks for every demo: assertions, latencies, isolation, and
      retrieval quality. Writes a pass/fail table (and optional JSON).
      LangCache / Agent Memory are skipped without real API keys.
      <code class="file">run_evals.py</code></p>
      <ol class="how">
        <li>Click Run eval suite (about a minute; rate-limit window wait is ~8s).</li>
        <li>Or: <code>python3 run_evals.py</code> / <code>python3 run_evals.py --json</code></li>
        <li>Exit code 0 only if every non-skipped check passed.</li>
      </ol>
      <form method="post" action="{url_for('run_script', key='evals')}">
        <button type="submit">Run eval suite</button>
      </form>
    </div>
    """

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Redis Demos</title>{PAGE_STYLE}</head>
<body>
  <h1>Redis Demos</h1>
  <p class="lede">All demos run against the Redis Cloud database configured in <code class="file">redis_config.py</code>.</p>
  {banner}
  <h2>Eval</h2>
  {eval_card}
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

    if key == "evals":
        try:
            result = _run_subprocess("run_evals.py", timeout=240)
        except subprocess.TimeoutExpired:
            return render_result("Eval suite", "Timed out after 240 seconds.", 1)
        output = result.stdout + result.stderr
        return render_result("Eval suite", output, result.returncode)

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
