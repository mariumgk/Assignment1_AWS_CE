import os
import requests
from flask import Flask, render_template
from dotenv import load_dotenv

# Load .env file (for local development)
load_dotenv()

app = Flask(__name__)

# ✅ API key loaded ONLY from environment variable — never hardcoded, never in frontend
API_KEY = os.getenv("TICKETMASTER_API_KEY")

# Emojis and categories for visual variety on cards
CATEGORY_EMOJIS = ['🎓', '🎭', '🏆', '💻', '🎵', '🎨', '🔬', '⚽', '🎤', '🌟']
CATEGORIES = ['academic', 'cultural', 'sports', 'tech']

# ── FALLBACK DEMO EVENTS (used when no API key is configured) ──
DEMO_EVENTS = [
    {
        "name": "GIKI Annual Tech Fest 2026",
        "date": "2026-04-15",
        "time": "10:00",
        "venue": "GIKI Auditorium",
        "description": "The biggest tech event of the year featuring coding competitions, robotics showcases, and keynote speakers from the industry.",
        "image": "",
        "emoji": "💻",
        "category": "tech",
    },
    {
        "name": "Inter-Department Cricket Tournament",
        "date": "2026-04-20",
        "time": "09:00",
        "venue": "GIKI Sports Complex",
        "description": "Annual cricket tournament between all engineering departments. Come cheer for your faculty and enjoy the competitive spirit!",
        "image": "",
        "emoji": "🏆",
        "category": "sports",
    },
    {
        "name": "Cloud Computing Workshop — AWS",
        "date": "2026-04-22",
        "time": "14:00",
        "venue": "CS Lab 3, FES Building",
        "description": "Hands-on workshop covering EC2, S3, and ELB. Learn to deploy real-world applications on AWS infrastructure.",
        "image": "",
        "emoji": "🎓",
        "category": "academic",
    },
    {
        "name": "GIKI Cultural Night",
        "date": "2026-05-01",
        "time": "18:30",
        "venue": "GIKI Open Air Theatre",
        "description": "An evening celebrating the diverse cultures of Pakistan with music, dance performances, and traditional cuisine.",
        "image": "",
        "emoji": "🎭",
        "category": "cultural",
    },
    {
        "name": "AI & Machine Learning Seminar",
        "date": "2026-05-05",
        "time": "11:00",
        "venue": "Seminar Hall, FES Building",
        "description": "Guest lecture on the latest advancements in AI/ML by leading researchers. Open to all departments.",
        "image": "",
        "emoji": "🔬",
        "category": "tech",
    },
    {
        "name": "GIKI Music Society Concert",
        "date": "2026-05-10",
        "time": "19:00",
        "venue": "GIKI Auditorium",
        "description": "Live performances by the GIKI Music Society featuring rock, classical, and fusion genres. A night you won't forget!",
        "image": "",
        "emoji": "🎵",
        "category": "cultural",
    },
    {
        "name": "Entrepreneurship Summit 2026",
        "date": "2026-05-15",
        "time": "10:00",
        "venue": "GIKI Conference Hall",
        "description": "Connect with startup founders, pitch your ideas, and learn what it takes to build a successful tech company.",
        "image": "",
        "emoji": "🌟",
        "category": "academic",
    },
    {
        "name": "Badminton Championship",
        "date": "2026-05-18",
        "time": "08:00",
        "venue": "GIKI Indoor Sports Hall",
        "description": "Inter-hostel badminton championship. Singles and doubles categories with exciting prizes for the winners.",
        "image": "",
        "emoji": "⚽",
        "category": "sports",
    },
    {
        "name": "Hackathon: Code for GIKI",
        "date": "2026-05-25",
        "time": "09:00",
        "venue": "CS Lab 1 & 2, FES Building",
        "description": "24-hour hackathon to build solutions for campus problems. Form teams of up to 4 and compete for cash prizes!",
        "image": "",
        "emoji": "💻",
        "category": "tech",
    },
]


def fetch_events():
    """
    Fetch events from Ticketmaster Discovery API.
    Falls back to demo data if no API key is set or if the API call fails.
    """
    if not API_KEY or API_KEY == "your_api_key_here":
        print("ℹ️  No API key configured — using demo events.")
        return DEMO_EVENTS

    url = "https://app.ticketmaster.com/discovery/v2/events.json"
    params = {
        "apikey": API_KEY,
        "size": 9,
        "countryCode": "US",
        "sort": "date,asc"
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if "_embedded" not in data or "events" not in data["_embedded"]:
            print("⚠️  No events returned from API — using demo events.")
            return DEMO_EVENTS

        events = data["_embedded"]["events"]
        result = []
        for i, e in enumerate(events):
            result.append({
                "name": e.get("name", "Unnamed Event"),
                "date": e.get("dates", {}).get("start", {}).get("localDate", "TBD"),
                "time": (e.get("dates", {}).get("start", {}).get("localTime", "") or "")[:5],
                "venue": (
                    e.get("_embedded", {}).get("venues", [{}])[0].get("name", "GIKI Campus")
                ),
                "description": (
                    e.get("info")
                    or e.get("pleaseNote")
                    or "Join us for this exciting university event at GIKI."
                ),
                "image": e["images"][0]["url"] if e.get("images") else "",
                "emoji": CATEGORY_EMOJIS[i % len(CATEGORY_EMOJIS)],
                "category": CATEGORIES[i % len(CATEGORIES)],
            })
        return result

    except requests.exceptions.Timeout:
        print("⚠️  API request timed out — using demo events.")
        return DEMO_EVENTS
    except requests.exceptions.ConnectionError:
        print("⚠️  Could not connect to Ticketmaster API — using demo events.")
        return DEMO_EVENTS
    except requests.exceptions.HTTPError as http_err:
        print(f"⚠️  HTTP error from Ticketmaster API: {http_err} — using demo events.")
        return DEMO_EVENTS
    except Exception as ex:
        print(f"⚠️  Unexpected error: {ex} — using demo events.")
        return DEMO_EVENTS


@app.route("/")
def index():
    events = fetch_events()
    return render_template("index.html", events=events)


if __name__ == "__main__":
    # 0.0.0.0 = accessible from any network interface (required for EC2)
    # Use port 80 on EC2, port 5000 locally (80 requires admin/root)
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
