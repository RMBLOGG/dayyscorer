from flask import Flask, render_template, request, jsonify, send_from_directory
import requests, time, json
from datetime import date as dt

app = Flask(__name__, static_folder='static')

API_KEY  = "809019a2c3cb4da895d535e570ee7f2d"
BASE_URL = "https://api.sportsrc.org/v2/"
HEADERS  = {"X-API-KEY": API_KEY}

# ── Upstash Redis ─────────────────────────────────────────
REDIS_URL   = "https://humble-tick-68472.upstash.io"
REDIS_TOKEN = "gQAAAAAAAQt4AAIncDIxNDg2ZjM0YzQyOGQ0NTkyYWFiY2E3MjQxMGYzNmJhNXAyNjg0NzI"
REDIS_HDR   = {"Authorization": f"Bearer {REDIS_TOKEN}", "Content-Type": "application/json"}

def redis_get(k):
    try:
        r = requests.post(f"{REDIS_URL}/pipeline", headers=REDIS_HDR,
                          json=[["GET", k]], timeout=3)
        result = r.json()
        v = result[0].get("result") if result else None
        return json.loads(v) if v else None
    except:
        return None

def redis_set(k, v, ttl):
    try:
        requests.post(f"{REDIS_URL}/pipeline", headers=REDIS_HDR,
                      json=[["SET", k, json.dumps(v), "EX", ttl]], timeout=3)
    except:
        pass

# ── Fallback in-memory ────────────────────────────────────
_mem = {}

def cache_get(k):
    v = redis_get(k)
    if v is not None: return v
    e = _mem.get(k)
    return e["data"] if e and time.time() < e["expires"] else None

def cache_set(k, d, ttl):
    redis_set(k, d, ttl)
    _mem[k] = {"data": d, "expires": time.time() + ttl}

def api_get(params, ttl=180):
    key = "ds_" + "_".join(f"{k}{v}" for k,v in sorted(params.items()))
    c = cache_get(key)
    if c is not None: return c
    try:
        r = requests.get(BASE_URL, headers=HEADERS, params=params, timeout=12)
        d = r.json()
        if d: cache_set(key, d, ttl)
        return d
    except Exception as e:
        return {"error": str(e)}

# ── Pages ─────────────────────────────────────────────────
@app.route("/")
def index(): return render_template("index.html")

@app.route("/watch/<path:match_id>")
def watch(match_id): return render_template("watch.html", match_id=match_id)

# ── PWA ───────────────────────────────────────────────────
@app.route("/manifest.json")
def manifest(): return send_from_directory("static", "manifest.json")

@app.route("/icon-192.png")
def icon192(): return send_from_directory("static", "icon-192.png")

@app.route("/icon-512.png")
def icon512(): return send_from_directory("static", "icon-512.png")

@app.route("/sw.js")
def sw():
    resp = send_from_directory("static", "sw.js")
    resp.headers["Service-Worker-Allowed"] = "/"
    resp.headers["Cache-Control"] = "no-cache"
    return resp

# ── API ───────────────────────────────────────────────────
@app.route("/api/matches")
def get_matches():
    sport  = request.args.get("sport", "football")
    status = request.args.get("status", "inprogress")
    date   = request.args.get("date", "") or dt.today().strftime("%Y-%m-%d")
    params = {"type": "matches", "sport": sport, "status": status, "date": date}
    ttl = 180 if status == "inprogress" else 600
    return jsonify(api_get(params, ttl))

@app.route("/api/detail/<path:match_id>")
def get_detail(match_id):
    return jsonify(api_get({"type": "detail", "id": match_id}, 180))

@app.route("/api/sports")
def get_sports():
    return jsonify(api_get({"type": "sports"}, 3600))

if __name__ == "__main__":
    app.run(debug=True)
