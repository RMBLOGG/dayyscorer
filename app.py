from flask import Flask, render_template, request, jsonify, send_from_directory
import requests, time, os, json

app = Flask(__name__, static_folder='static')

API_KEY  = "809019a2c3cb4da895d535e570ee7f2d"
BASE_URL = "https://api.sportsrc.org/v2/"
HEADERS  = {"X-API-KEY": API_KEY}

# Claude API key — set via environment variable ANTHROPIC_API_KEY
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

# ── Cache ─────────────────────────────────────────────────
_cache = {}
def cache_get(k):
    e = _cache.get(k)
    return e["data"] if e and time.time() < e["expires"] else None
def cache_set(k, d, ttl):
    _cache[k] = {"data": d, "expires": time.time() + ttl}
def api_get(params, ttl=60):
    key = str(sorted(params.items()))
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

@app.route("/parlay")
def parlay(): return render_template("parlay.html")

# ── PWA static files ──────────────────────────────────────
@app.route("/manifest.json")
def manifest(): return send_from_directory("static", "manifest.json")

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
    ttl = 60 if status == "inprogress" else 600
    return jsonify(api_get(params, ttl))

@app.route("/api/detail/<path:match_id>")
def get_detail(match_id):
    return jsonify(api_get({"type": "detail", "id": match_id}, 120))

@app.route("/api/sports")
def get_sports():
    return jsonify(api_get({"type": "sports"}, 3600))

# ── Parlay Prediction ─────────────────────────────────────
@app.route("/api/parlay-predict", methods=["POST"])
def parlay_predict():
    if not ANTHROPIC_API_KEY:
        return jsonify({"error": "ANTHROPIC_API_KEY not configured on server"}), 500

    body = request.get_json(force=True) or {}
    picks = body.get("picks", [])
    sport = body.get("sport", "football")

    if len(picks) < 2:
        return jsonify({"error": "Minimum 2 picks required"}), 400
    if len(picks) > 6:
        return jsonify({"error": "Maximum 6 picks allowed"}), 400

    # Fetch recent results for context (last 3 days) to enrich the prompt
    recent_data = []
    try:
        today = time.strftime("%Y-%m-%d")
        res = api_get({"type": "matches", "sport": sport, "status": "finished", "date": today}, 600)
        recent_data = res.get("data", [])[:5]  # limit to 5 leagues for brevity
    except:
        pass

    # Build match context string
    match_list = "\n".join([
        f"- {p['home']} vs {p['away']} | League: {p.get('league','?')} | Market: {p['market']}"
        for p in picks
    ])

    recent_str = ""
    if recent_data:
        recent_str = "\n\nRecent results context (today):\n"
        for g in recent_data[:3]:
            league = g.get("league", {}).get("name", "?")
            for m in (g.get("matches") or [])[:3]:
                h = m.get("teams", {}).get("home", {}).get("name", "?")
                a = m.get("teams", {}).get("away", {}).get("name", "?")
                sc = m.get("score", {}).get("current", {})
                recent_str += f"  {h} {sc.get('home','?')}-{sc.get('away','?')} {a} [{league}]\n"

    prompt = f"""You are an expert sports betting analyst. Analyze this {sport} parlay and provide a structured JSON prediction.

Parlay selections:
{match_list}
{recent_str}

Analyze each match considering:
- Current form and momentum
- Home/away advantage
- Head-to-head historical tendencies
- League context and team strength
- Market-specific factors (e.g., over/under goal trends, BTTS rates)
- Any general knowledge about these teams

Respond ONLY with a valid JSON object, no markdown, no explanation outside JSON:
{{
  "overall_confidence": <integer 0-100>,
  "summary": "<2-3 sentence overall parlay assessment in a natural, analyst tone>",
  "predictions": [
    {{
      "home": "<team>",
      "away": "<team>",
      "market": "<market>",
      "pick": "<recommended outcome, e.g. Home Win, Over 2.5, Yes, etc>",
      "confidence": <integer 0-100>,
      "reasoning": "<2-3 sentences of specific reasoning for this pick>"
    }}
  ]
}}

Be realistic. For parlays with 4+ legs, overall_confidence should rarely exceed 55%. Be honest about uncertainty."""

    try:
        resp = requests.post(
            ANTHROPIC_URL,
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 1500,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
        raw = data["content"][0]["text"].strip()

        # Strip possible markdown fences
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        parsed = json.loads(raw)
        return jsonify(parsed)

    except json.JSONDecodeError as e:
        return jsonify({"error": f"AI returned invalid JSON: {str(e)}"}), 500
    except requests.RequestException as e:
        return jsonify({"error": f"Claude API error: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)
