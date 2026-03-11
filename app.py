from flask import Flask, render_template, request, jsonify
import requests
import time

app = Flask(__name__)

API_KEY = "809019a2c3cb4da895d535e570ee7f2d"
BASE_URL = "https://api.sportsrc.org/v2/"
HEADERS = {"X-API-KEY": API_KEY}

# ─── Simple in-memory cache ───────────────────────────────────────────────────
_cache = {}

def cache_get(key):
    entry = _cache.get(key)
    if entry and time.time() < entry["expires"]:
        return entry["data"]
    return None

def cache_set(key, data, ttl):
    _cache[key] = {"data": data, "expires": time.time() + ttl}

# ─── API helper ───────────────────────────────────────────────────────────────
def api_get(params, ttl=60):
    key = str(sorted(params.items()))
    cached = cache_get(key)
    if cached is not None:
        return cached
    try:
        r = requests.get(BASE_URL, headers=HEADERS, params=params, timeout=12)
        data = r.json()
        if data:
            cache_set(key, data, ttl)
        return data
    except Exception as e:
        return {"error": str(e)}

# ─── Routes ───────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/watch/<path:match_id>")
def watch(match_id):
    return render_template("watch.html", match_id=match_id)

@app.route("/api/matches")
def get_matches():
    sport  = request.args.get("sport", "football")
    status = request.args.get("status", "inprogress")
    date   = request.args.get("date", "")
    params = {"type": "matches", "sport": sport, "status": status}
    if date:
        params["date"] = date
    # live = 60s, upcoming/finished = 10 min
    ttl = 60 if status == "inprogress" else 600
    return jsonify(api_get(params, ttl))

@app.route("/api/detail/<path:match_id>")
def get_detail(match_id):
    # detail cache 2 min
    return jsonify(api_get({"type": "detail", "id": match_id}, 120))

@app.route("/api/sports")
def get_sports():
    return jsonify(api_get({"type": "sports"}, 3600))

if __name__ == "__main__":
    app.run(debug=True)
