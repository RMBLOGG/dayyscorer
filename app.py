from flask import Flask, render_template, request, jsonify, send_from_directory
import requests, time, os, json

app = Flask(__name__, static_folder='static')

API_KEY  = "809019a2c3cb4da895d535e570ee7f2d"
BASE_URL = "https://api.sportsrc.org/v2/"
HEADERS  = {"X-API-KEY": API_KEY}

# ── Upstash Redis (shared cache semua instance) ───────────
REDIS_URL   = "https://humble-tick-68472.upstash.io"
REDIS_TOKEN = "gQAAAAAAAQt4AAIncDIxNDg2ZjM0YzQyOGQ0NTkyYWFiY2E3MjQxMGYzNmJhNXAyNjg0NzI"
REDIS_HDR   = {"Authorization": f"Bearer {REDIS_TOKEN}"}

def redis_get(k):
    try:
        r = requests.get(f"{REDIS_URL}/get/{k}", headers=REDIS_HDR, timeout=3)
        v = r.json().get("result")
        if v is None: return None
        return json.loads(v)
    except:
        return None

def redis_set(k, v, ttl):
    try:
        data = json.dumps(v)
        # SET key value EX ttl
        requests.post(f"{REDIS_URL}/set/{k}", headers=REDIS_HDR,
                      json={"value": data, "ex": ttl}, timeout=3)
    except:
        pass

# Fallback in-memory cache kalau Redis gagal
_mem = {}
def cache_get(k):
    # Coba Redis dulu
    v = redis_get(k)
    if v is not None: return v
    # Fallback memory
    e = _mem.get(k)
    return e["data"] if e and time.time() < e["expires"] else None

def cache_set(k, d, ttl):
    redis_set(k, d, ttl)
    _mem[k] = {"data": d, "expires": time.time() + ttl}

def api_get(params, ttl=120):
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

# ── PWA static files ──────────────────────────────────────
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
    date   = request.args.get("date", "")
    params = {"type": "matches", "sport": sport, "status": status}
    if date: params["date"] = date
    ttl = 120 if status == "inprogress" else 600
    return jsonify(api_get(params, ttl))

@app.route("/api/detail/<path:match_id>")
def get_detail(match_id):
    return jsonify(api_get({"type": "detail", "id": match_id}, 120))

@app.route("/api/sports")
def get_sports():
    return jsonify(api_get({"type": "sports"}, 3600))

if __name__ == "__main__":
    app.run(debug=True)
