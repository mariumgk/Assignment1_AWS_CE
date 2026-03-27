"""
UniEvent — Scalable University Event Management System on AWS
Flask backend handling Ticketmaster API integration, S3 image upload,
and event registration.
"""

import os
import json
import logging
import requests
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from datetime import datetime

# ── Configuration ────────────────────────────────────────────────────────────
load_dotenv()

app = Flask(__name__)

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# API key from environment variable — never hardcoded
API_KEY = os.getenv("TICKETMASTER_API_KEY")

# S3 configuration (set via environment variables on EC2)
S3_BUCKET = os.getenv("S3_BUCKET_NAME", "")
S3_REGION = os.getenv("S3_REGION", "us-east-1")

# Registration storage file
REGISTRATIONS_FILE = "registrations.json"

# Visual variety for event cards
CATEGORY_EMOJIS = ['🎓', '🎭', '🏆', '💻', '🎵', '🎨', '🔬', '⚽', '🎤', '🌟']
CATEGORIES = ['academic', 'cultural', 'sports', 'tech']


# ── Helper Functions ─────────────────────────────────────────────────────────

def pick_best_image(images):
    """
    Pick the highest-quality image from Ticketmaster's image list.
    Prefers the largest image by width; falls back to index 0.
    """
    if not images:
        return ""
    # Sort by width descending — largest image first
    try:
        sorted_imgs = sorted(images, key=lambda img: int(img.get("width", 0)), reverse=True)
        return sorted_imgs[0].get("url", "")
    except Exception:
        return images[0].get("url", "")


def upload_to_s3(image_url, event_name):
    """
    Download an image from a URL and upload it to the configured S3 bucket.
    Uses a two-tier strategy:
      1. Try public-read ACL → permanent public S3 URL
      2. If bucket blocks ACLs → upload privately + return 24h pre-signed URL
    Falls back to original Ticketmaster URL on any failure.
    Uses IAM role attached to EC2 — no credentials in code.
    """
    if not S3_BUCKET:
        logger.info("S3_BUCKET_NAME not configured — using original image URL.")
        return image_url

    try:
        # Download the image from Ticketmaster
        img_response = requests.get(image_url, timeout=8)
        img_response.raise_for_status()

        # Detect content type from response headers
        content_type = img_response.headers.get("Content-Type", "image/jpeg").split(";")[0]
        ext = "jpg" if "jpeg" in content_type else content_type.split("/")[-1]

        # Generate a safe, unique filename
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in event_name)[:60]
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        key = f"event-images/{safe_name}_{timestamp}.{ext}"

        s3_client = boto3.client("s3", region_name=S3_REGION)

        # Strategy 1: public-read ACL — permanent public URL
        # Works when bucket has "Block Public ACLs" DISABLED
        try:
            s3_client.put_object(
                Bucket=S3_BUCKET,
                Key=key,
                Body=img_response.content,
                ContentType=content_type,
                ACL="public-read"
            )
            s3_url = f"https://{S3_BUCKET}.s3.amazonaws.com/{key}"
            logger.info(f"Uploaded to S3 (public-read): {s3_url}")
            return s3_url

        except ClientError as acl_err:
            # Strategy 2: bucket blocks public ACLs — upload privately,
            # return a 24-hour pre-signed URL (still renders fine in <img>)
            logger.warning(f"public-read blocked ({acl_err.response['Error']['Code']}). Using pre-signed URL.")
            s3_client.put_object(
                Bucket=S3_BUCKET,
                Key=key,
                Body=img_response.content,
                ContentType=content_type
            )
            presigned_url = s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": S3_BUCKET, "Key": key},
                ExpiresIn=86400  # 24 hours
            )
            logger.info(f"Uploaded to S3 (pre-signed 24h): {presigned_url[:80]}...")
            return presigned_url

    except (NoCredentialsError, ClientError) as e:
        logger.warning(f"S3 upload failed: {e} — using original Ticketmaster URL")
        return image_url
    except requests.exceptions.RequestException as e:
        logger.warning(f"Failed to download image: {e} — using original Ticketmaster URL")
        return image_url
    except Exception as e:
        logger.warning(f"Unexpected S3 error: {e} — using original Ticketmaster URL")
        return image_url


def fetch_events():
    """
    Fetch events from Ticketmaster Discovery API.
    Returns a list of event dicts on success, or an empty list on failure.
    NO fallback to demo/static data — API is the only source.
    """
    if not API_KEY or API_KEY == "your_api_key_here":
        logger.error("TICKETMASTER_API_KEY is not configured.")
        return []

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
            logger.warning("Ticketmaster returned no events.")
            return []

        raw_events = data["_embedded"]["events"]
        result = []

        for i, e in enumerate(raw_events):
            # Pick the best (largest) image from Ticketmaster's image list
            image_url = pick_best_image(e.get("images", []))

            # Upload image to S3 (returns S3 URL on success, original URL on failure)
            if image_url:
                image_url = upload_to_s3(image_url, e.get("name", "event"))
                logger.info(f"Event '{e.get('name','')}' → image: {image_url[:80]}...")

            # Safely extract venue name
            venue = "Venue TBD"
            venues_list = e.get("_embedded", {}).get("venues", [])
            if venues_list:
                venue = venues_list[0].get("name", "Venue TBD")

            # Safely extract description
            description = (
                e.get("info")
                or e.get("pleaseNote")
                or "Join us for this exciting university event. Check back for more details."
            )

            result.append({
                "id": e.get("id", f"evt-{i}"),
                "name": e.get("name", "Unnamed Event"),
                "date": e.get("dates", {}).get("start", {}).get("localDate", "TBD"),
                "time": (e.get("dates", {}).get("start", {}).get("localTime", "") or "")[:5],
                "venue": venue,
                "description": description,
                "image": image_url,
                "emoji": CATEGORY_EMOJIS[i % len(CATEGORY_EMOJIS)],
                "category": CATEGORIES[i % len(CATEGORIES)],
            })

        logger.info(f"Fetched {len(result)} events from Ticketmaster API.")
        return result

    except requests.exceptions.Timeout:
        logger.error("Ticketmaster API request timed out.")
        return []
    except requests.exceptions.ConnectionError:
        logger.error("Could not connect to Ticketmaster API.")
        return []
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"HTTP error from Ticketmaster API: {http_err}")
        return []
    except Exception as ex:
        logger.error(f"Unexpected error fetching events: {ex}")
        return []


def load_registrations():
    """Load existing registrations from JSON file."""
    if os.path.exists(REGISTRATIONS_FILE):
        try:
            with open(REGISTRATIONS_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
    return []


def save_registrations(registrations):
    """Save registrations to JSON file."""
    try:
        with open(REGISTRATIONS_FILE, "w") as f:
            json.dump(registrations, f, indent=2)
    except IOError as e:
        logger.error(f"Failed to save registrations: {e}")


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Main page — fetches events from API and renders them."""
    events = fetch_events()
    return render_template("index.html", events=events)


@app.route("/register", methods=["POST"])
def register_event():
    """
    Handle event registration.
    Expects JSON body with: event_id, event_name, user_name, user_email
    Stores registration in a JSON file.
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({"success": False, "message": "No data provided."}), 400

        event_id = data.get("event_id", "")
        event_name = data.get("event_name", "")
        user_name = data.get("user_name", "").strip()
        user_email = data.get("user_email", "").strip()

        # Validation
        if not user_name or not user_email:
            return jsonify({
                "success": False,
                "message": "Name and email are required."
            }), 400

        if "@" not in user_email:
            return jsonify({
                "success": False,
                "message": "Please provide a valid email address."
            }), 400

        # Create registration record
        registration = {
            "event_id": event_id,
            "event_name": event_name,
            "user_name": user_name,
            "user_email": user_email,
            "timestamp": datetime.now().isoformat()
        }

        # Load, append, save
        registrations = load_registrations()
        registrations.append(registration)
        save_registrations(registrations)

        logger.info(f"New registration: {user_name} for '{event_name}'")

        return jsonify({
            "success": True,
            "message": f"Successfully registered for {event_name}!"
        }), 200

    except Exception as e:
        logger.error(f"Registration error: {e}")
        return jsonify({
            "success": False,
            "message": "An error occurred. Please try again."
        }), 500


@app.route("/health")
def health():
    """Health check endpoint for ALB target group."""
    return jsonify({"status": "healthy", "service": "UniEvent"}), 200


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    logger.info(f"Starting UniEvent on port {port}")
    app.run(host="0.0.0.0", port=port)
