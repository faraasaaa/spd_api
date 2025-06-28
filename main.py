import os
import time
import requests
import json # Added for the new download logic
from pathlib import Path
import re # For cleaning filename
from flask import Flask, request, jsonify
from flask_cors import CORS
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from dotenv import load_dotenv
import logging

# Load environment variables from a .env file
# This should be called as early as possible
load_dotenv()

# --- Constants for Download Functionality ---
# SPOTIFY_API_URL_FROM_USER is no longer used by the new /download logic
# TMPFILES_API_URL is no longer used by the new /download logic
DOWNLOAD_FOLDER = Path.cwd() / "temp_downloads" # May not be used by new /download, but kept for other potential uses

# --- Configure logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Initialize Flask app
app = Flask(__name__)
CORS(app) # Enable CORS for all routes

# Get Spotify API credentials from environment variables or use fallbacks
CLIENT_ID = '66e7d064dbdc421d8a3b9b2faac6d408'
CLIENT_SECRET = 'ccd204ab13c84096b148b3c1091084a8'

# Initialize Spotipy instance variable
sp = None

if not CLIENT_ID or not CLIENT_SECRET:
    app.logger.error("Error: SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET must be set.")
else:
    try:
        auth_manager = SpotifyClientCredentials(client_id=CLIENT_ID, client_secret=CLIENT_SECRET)
        sp = spotipy.Spotify(auth_manager=auth_manager)
        app.logger.info("Spotipy initialized successfully.")
    except Exception as e:
        app.logger.error(f"Error initializing Spotipy: {e}")

# --- Flask API Routes ---

@app.route('/')
def home():
    """A simple route to check if the backend is running."""
    if not sp:
        return "Spotify API backend is running, but Spotipy is NOT initialized. Check credentials and logs."
    return "Spotify API backend is running and Spotipy is initialized!"

@app.route('/search', methods=['GET'])
def search_song():
    """
    Searches for a song on Spotify.
    Expects a 'song_name' query parameter.
    e.g., /search?song_name=Bohemian Rhapsody
    """
    if not sp:
        return jsonify({"error": "Spotipy not initialized. Check credentials."}), 500

    song_name = request.args.get('song_name')

    if not song_name:
        return jsonify({"error": "Missing 'song_name' query parameter"}), 400

    try:
        results = sp.search(q=song_name, type='track', limit=10)
        items = results.get('tracks', {}).get('items', [])

        if items:
            formatted_tracks = []
            for track in items:
                album_images = track.get('album', {}).get('images', [])
                cover_image_url = album_images[0].get('url') if album_images else None

                formatted_tracks.append({
                    "name": track.get('name'),
                    "artists": [artist.get('name') for artist in track.get('artists', [])],
                    "album": track.get('album', {}).get('name'),
                    "uri": track.get('uri'),
                    "external_urls": track.get('external_urls', {}).get('spotify'),
                    "cover_image": cover_image_url
                })
            return jsonify({"tracks": formatted_tracks})
        else:
            return jsonify({"message": f"No tracks found matching '{song_name}'."})

    except spotipy.exceptions.SpotifyException as e:
        app.logger.error(f"Spotify API error during search: {e}")
        return jsonify({"error": f"Spotify API error: {str(e)}"}), 500
    except Exception as e:
        app.logger.error(f"An unexpected error occurred during search: {e}", exc_info=True)
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

@app.route('/download', methods=['POST'])
def download_track_endpoint():
    """
    API endpoint to fetch download information for a Spotify track using an external service.
    Expects a JSON payload with "spotify_url".
    e.g., POST /download with {"spotify_url": "https://open.spotify.com/track/yourtrackid"}
    """
    if not request.is_json:
        app.logger.warning("Received non-JSON request to /download endpoint.")
        return jsonify({"status": "error", "message": "Invalid request: payload must be JSON."}), 400

    data = request.get_json()
    spotify_link = data.get('spotify_url') # The user's new code uses 'spotify_link'

    if not spotify_link:
        app.logger.warning("Missing 'spotify_url' in request to /download endpoint.")
        return jsonify({"status": "error", "message": "Missing 'spotify_url' in request payload."}), 400

    # --- New download logic based on user's provided code ---
    url = "https://spotify-scraper.p.rapidapi.com/v1/track/download/soundcloud"
    # IMPORTANT: The API key is hardcoded here as per the user's snippet.
    # In a production environment, this should be managed securely (e.g., environment variables).
    headers = {
        "x-rapidapi-key": "42bab6596emsh9c21014a889d907p14f8bdjsn110fdf83d113", # Hardcoded API key
        "x-rapidapi-host": "spotify-scraper.p.rapidapi.com"
    }
    querystring = {"track": spotify_link, "quality": "hq"} # Using spotify_link from request

    try:
        app.logger.info(f"Fetching download info for Spotify link: {spotify_link} from RapidAPI.")
        response_from_scraper = requests.get(url, headers=headers, params=querystring, timeout=30)
        response_from_scraper.raise_for_status()  # Raise an exception for HTTP errors (4xx or 5xx)

        scraper_data = response_from_scraper.json()
        app.logger.info(f"Received data from RapidAPI")


        # Extract info, providing defaults if keys are missing
        song_name = scraper_data.get("spotifyTrack", {}).get("name", "Unknown Track")
        # Corrected artist name extraction to handle potential empty artists list or missing name
        artists_list = scraper_data.get("spotifyTrack", {}).get("artists", [])
        if artists_list and isinstance(artists_list, list) and len(artists_list) > 0:
             artist_name = artists_list[0].get("name", "Unknown Artist")
        else:
            artist_name = "Unknown Artist"

        album_name = scraper_data.get("spotifyTrack", {}).get("album", {}).get("name", "Unknown Album")
        
        # Corrected mp3_download_url extraction
        mp3_download_url = None
        soundcloud_track_audio = scraper_data.get("soundcloudTrack", {}).get("audio", [])
        if soundcloud_track_audio and isinstance(soundcloud_track_audio, list):
            for audio_item in soundcloud_track_audio:
                if isinstance(audio_item, dict) and audio_item.get("format") == "mp3":
                    mp3_download_url = audio_item.get("url")
                    break # Found the mp3, no need to continue loop
        
        if not mp3_download_url:
            app.logger.warning(f"MP3 download URL not found in RapidAPI response for {spotify_link}.")
            # Optionally, you could return an error here if mp3_download_url is critical
            # return jsonify({"status": "error", "message": "MP3 download URL not found."}), 404


        # Prepare the result in the expected format
        result = {
            "message": "Successfully fetched track information.",
            "track_info": {
                "title": song_name,
                "artist": artist_name,
                "album": album_name
            },
            "upload_url": mp3_download_url # This is the direct MP3 URL from the new API
        }
        
        # The user's code had time.sleep(2). It's unclear why.
        # If it's for rate-limiting or waiting for a process, it might be needed.
        # For an API endpoint, long sleeps are generally avoided unless necessary.
        # time.sleep(2) # Kept commented out, uncomment if necessary
        time.sleep(4)
        return jsonify({"status": "success", "data": result}), 200

    except requests.exceptions.HTTPError as he:
        status_code = he.response.status_code if he.response is not None else 500
        error_message = f"RapidAPI service error: {he}"
        try:
            # Try to get more specific error from RapidAPI response
            error_details = he.response.json()
            error_message = f"RapidAPI service error: {error_details.get('message', str(he))}"
        except ValueError: # If response is not JSON
            pass
        app.logger.error(f"HTTPError calling RapidAPI: {error_message} (Status: {status_code})")
        return jsonify({"status": "error", "message": error_message}), status_code
    except requests.exceptions.ConnectionError as ce:
        app.logger.error(f"ConnectionError calling RapidAPI: {ce}")
        return jsonify({"status": "error", "message": f"Could not connect to RapidAPI service: {ce}"}), 503
    except requests.exceptions.Timeout as te:
        app.logger.error(f"Timeout calling RapidAPI: {te}")
        return jsonify({"status": "error", "message": f"Request to RapidAPI service timed out: {te}"}), 504
    except json.JSONDecodeError as je:
        app.logger.error(f"Failed to parse JSON response from RapidAPI: {je}. Response text: {response_from_scraper.text[:200]}")
        return jsonify({"status": "error", "message": "Invalid response from external service."}), 502
    except Exception as e:
        app.logger.error(f"Unhandled exception in /download endpoint (RapidAPI logic): {e}", exc_info=True)
        return jsonify({"status": "error", "message": f"An internal server error occurred: {str(e)}"}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=True) # Set debug=False for production
