"""
Flask app demonstrating cache-aside caching with Redis.

Simulates a "slow" data lookup (like a real DB query or external API call)
and caches the result in Redis so repeated requests are fast.

Install dependencies:
    pip3 install -r requirements.txt

Run:
    python3 app.py

Then in another terminal try:
    curl http://localhost:5000/users/1        # first call: slow (cache miss)
    curl http://localhost:5000/users/1        # second call: fast (cache hit)
    curl -X DELETE http://localhost:5000/cache/users/1   # invalidate
    curl http://localhost:5000/users/1        # slow again (cache miss)
"""

import json
import os
import time
from pathlib import Path

import ldclient
import redis
from flask import Flask, jsonify
from ldclient import Context
from ldclient.config import Config

TEST_BANNER_FLAG_KEY = "show-test-banner"
TEST_BANNER_FLAG_URL = (
    "https://app.launchdarkly.com/projects/default/flags/"
    "show-test-banner/targeting?env=test"
)
BANNER_OFF_TEXT = "LaunchDarkly test banner (flag is off)"
BANNER_ON_TEXT = "LaunchDarkly test banner (flag is on)"


def _load_dotenv(path: str = ".env") -> None:
    """Load KEY=VALUE lines into the environment. Existing vars win."""
    env_path = Path(path)
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()

app = Flask(__name__)

# --- Redis connection ---
# Set REDIS_HOST/REDIS_PORT/REDIS_PASSWORD/REDIS_TLS env vars to point at
# Redis Cloud instead of local Redis. See redis_test.py for the full list.
r = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    password=os.getenv("REDIS_PASSWORD") or None,
    db=0,
    ssl=os.getenv("REDIS_TLS", "false").lower() == "true",
    decode_responses=True,
)

CACHE_TTL_SECONDS = 30  # how long a cached entry stays valid


def _init_launchdarkly():
    """One shared client. Flag reads wait until this has finished."""
    sdk_key = os.getenv("LAUNCHDARKLY_SDK_KEY", "").strip()
    if not sdk_key:
        app.logger.warning(
            "LAUNCHDARKLY_SDK_KEY is not set. Flag evaluations will use defaults."
        )
        return None

    ldclient.set_config(Config(sdk_key))
    client = ldclient.get()
    if not client.is_initialized():
        app.logger.warning(
            "LaunchDarkly client failed to initialize. Flag evaluations will use defaults."
        )
        return None
    return client


ld_client = _init_launchdarkly()


def test_banner_enabled() -> bool:
    if ld_client is None:
        return False
    context = Context.builder("redis-demo").kind("user").name("Redis demo").build()
    try:
        return bool(ld_client.variation(TEST_BANNER_FLAG_KEY, context, False))
    except Exception:
        app.logger.exception("LaunchDarkly flag evaluation failed")
        return False


def _banner_page(flag_on: bool) -> str:
    message = BANNER_ON_TEXT if flag_on else BANNER_OFF_TEXT
    banner_class = "banner on" if flag_on else "banner"
    link = ""
    if not flag_on:
        link = (
            f'<a href="{TEST_BANNER_FLAG_URL}">View flag in LaunchDarkly</a>'
        )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Redis cache demo</title>
  <style>
    body {{
      margin: 0;
      font-family: "Segoe UI", system-ui, sans-serif;
      color: #18181b;
      background: #ffffff;
    }}
    .banner {{
      padding: 14px 20px;
      background: #f4f4f5;
      color: #18181b;
      border-bottom: 1px solid #e4e4e7;
      display: flex;
      gap: 16px;
      align-items: center;
      justify-content: space-between;
    }}
    .banner.on {{
      background: #16a34a;
      color: #ffffff;
      border-bottom-color: #15803d;
    }}
    .banner a {{
      color: inherit;
    }}
    main {{
      padding: 28px 20px;
      max-width: 640px;
    }}
  </style>
</head>
<body>
  <div id="banner" class="{banner_class}">
    <span id="banner-text">{message}</span>
    <span id="banner-link">{link}</span>
  </div>
  <main>
    <h1>Redis cache demo</h1>
    <p>Look up a user at <code>/users/1</code>. Repeated calls should come from the cache.</p>
  </main>
  <script>
    async function refreshBanner() {{
      const response = await fetch("/banner-state");
      const data = await response.json();
      const banner = document.getElementById("banner");
      const text = document.getElementById("banner-text");
      const link = document.getElementById("banner-link");
      banner.className = data.on ? "banner on" : "banner";
      text.textContent = data.message;
      link.innerHTML = data.on ? "" : '<a href="' + data.flagUrl + '">View flag in LaunchDarkly</a>';
    }}
    setInterval(refreshBanner, 2000);
  </script>
</body>
</html>
"""


def fetch_user_from_slow_source(user_id: int) -> dict:
    """
    Stand-in for something expensive: a slow database query,
    a third-party API call, a heavy computation, etc.
    """
    time.sleep(2)  # simulate latency
    return {
        "id": user_id,
        "name": f"User {user_id}",
        "role": "tester",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


@app.route("/users/<int:user_id>", methods=["GET"])
def get_user(user_id):
    cache_key = f"user:{user_id}"
    start = time.time()

    cached = r.get(cache_key)
    if cached is not None:
        elapsed = round(time.time() - start, 4)
        return jsonify({
            "source": "cache",
            "elapsed_seconds": elapsed,
            "data": json.loads(cached),
        })

    # Cache miss - do the "expensive" work
    data = fetch_user_from_slow_source(user_id)
    r.setex(cache_key, CACHE_TTL_SECONDS, json.dumps(data))

    elapsed = round(time.time() - start, 4)
    return jsonify({
        "source": "database",
        "elapsed_seconds": elapsed,
        "data": data,
    })


@app.route("/cache/users/<int:user_id>", methods=["DELETE"])
def invalidate_user_cache(user_id):
    cache_key = f"user:{user_id}"
    deleted = r.delete(cache_key)
    return jsonify({
        "cache_key": cache_key,
        "invalidated": bool(deleted),
    })


@app.route("/", methods=["GET"])
def home():
    flag_on = test_banner_enabled()
    return _banner_page(flag_on)


@app.route("/banner-state", methods=["GET"])
def banner_state():
    flag_on = test_banner_enabled()
    return jsonify({
        "on": flag_on,
        "message": BANNER_ON_TEXT if flag_on else BANNER_OFF_TEXT,
        "flagUrl": TEST_BANNER_FLAG_URL,
    })


@app.route("/health", methods=["GET"])
def health():
    try:
        r.ping()
        return jsonify({"status": "ok", "redis": "connected"})
    except redis.exceptions.ConnectionError:
        return jsonify({"status": "error", "redis": "unreachable"}), 503


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
