# Import necessary libraries
from flask import Flask, request, jsonify
# Import CORS for handling Cross-Origin Resource Sharing
from flask_cors import CORS
import requests
import json

# Create a Flask application instance
app = Flask(__name__)
# Enable CORS for all routes and origins.
# For production, you might want to restrict origins: CORS(app, resources={r"/fetch-track": {"origins": "YOUR_FRONTEND_DOMAIN"}})
CORS(app)

# Define constant headers for the external API calls
SPOTYDOWN_HEADERS = {
    'accept': '*/*',
    'accept-language': 'en-US,en;q=0.9,de;q=0.8',
    'content-type': 'application/json',
    'origin': 'https://spotydown.com',
    'priority': 'u=1, i',
    'referer': 'https://spotydown.com/',
    'sec-ch-ua': '"Google Chrome";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36',
}

# Define the API endpoint - Changed to GET and accepts 'url' query parameter
@app.route('/fetch-track', methods=['GET'])
def fetch_track_info():
    """
    API endpoint to fetch Spotify track metadata and download URL.
    Expects a 'url' query parameter.
    e.g., /fetch-track?url=YOUR_SPOTIFY_TRACK_URL_HERE
    """
    # --- 1. Get URL from query parameter ---
    spotify_url = request.args.get('url') # Get 'url' from query string args

    if not spotify_url:
        # Return a JSON error response if 'url' parameter is missing
        return jsonify({"error": "Missing 'url' query parameter"}), 400

    # --- 2. Prepare data for external API ---
    payload = {'url': spotify_url}
    metadata = None
    download_info = None
    combined_data = {}

    # --- 3. Call get-metadata endpoint ---
    try:
        response_meta = requests.post(
            'https://spotydown.com/api/get-metadata',
            headers=SPOTYDOWN_HEADERS,
            json=payload,
            timeout=15 # Increased timeout slightly
        )
        response_meta.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)

        # Try parsing the metadata response
        try:
            metadata = response_meta.json()
            # Extract the relevant part if structure is consistent
            if isinstance(metadata, dict) and metadata.get("apiResponse", {}).get("data"):
                 if isinstance(metadata["apiResponse"]["data"], list) and len(metadata["apiResponse"]["data"]) > 0:
                     combined_data = metadata["apiResponse"]["data"][0] # Get the first track's data
                 else:
                     # Handle cases where data is empty or not a list
                     print(f"Warning: Unexpected structure in metadata response data: {metadata['apiResponse']['data']}")
                     combined_data = {} # Start with empty dict if structure is off
            else:
                # Handle cases where the expected keys aren't present
                print(f"Warning: Unexpected structure in metadata response: {metadata}")
                combined_data = {} # Start with empty dict if structure is off

        except json.JSONDecodeError:
            print(f"Error decoding metadata JSON: {response_meta.text}")
            return jsonify({"error": "Failed to parse metadata response from external API"}), 500
        except Exception as e:
             print(f"Error processing metadata: {e}")
             return jsonify({"error": f"Error processing metadata: {e}"}), 500


    except requests.exceptions.RequestException as e:
        print(f"Error calling get-metadata API: {e}")
        return jsonify({"error": f"Failed to connect to get-metadata API: {e}"}), 502 # Bad Gateway

    # --- 4. Call download-track endpoint ---
    # Only proceed if metadata was successfully retrieved and processed
    if combined_data: # Check if combined_data was populated
        try:
            response_download = requests.post(
                'https://spotydown.com/api/download-track',
                headers=SPOTYDOWN_HEADERS,
                json=payload, # Send the same payload
                timeout=15 # Increased timeout slightly
            )
            response_download.raise_for_status() # Raise an exception for bad status codes

            # Try parsing the download response
            try:
                download_info = response_download.json()
                # Add the file_url to the combined data if it exists
                if isinstance(download_info, dict) and 'file_url' in download_info:
                    combined_data['download_url'] = download_info['file_url'] # Use a more descriptive key
                else:
                     print(f"Warning: 'file_url' not found or unexpected structure in download response: {download_info}")
                     # Metadata was found, but download URL wasn't. Still return metadata.
                     # combined_data['download_url'] = None # Explicitly set to None or omit

            except json.JSONDecodeError:
                print(f"Error decoding download JSON: {response_download.text}")
                # Don't fail the whole request, just log it. Metadata might still be useful.
                # combined_data['download_url'] = None # Explicitly set to None or omit
            except Exception as e:
                 print(f"Error processing download info: {e}")
                 # Don't fail the whole request, just log it.
                 # combined_data['download_url'] = None # Explicitly set to None or omit


        except requests.exceptions.RequestException as e:
            print(f"Error calling download-track API: {e}")
            # Don't fail the whole request if metadata succeeded. Log the error.
            # The response will just lack the download_url.
            # return jsonify({"error": f"Failed to connect to download-track API: {e}"}), 502 # Or just let it return metadata

    # --- 5. Return combined response ---
    if not combined_data:
         # Handle case where metadata extraction failed initially
         return jsonify({"error": "Failed to retrieve track information"}), 500

    # Return the combined data (with or without download_url)
    return jsonify(combined_data), 200

# --- Run the Flask app ---
if __name__ == '__main__':
    # Run on localhost, port 5000
    # Set debug=True for development (provides detailed error pages)
    # Set debug=False for production
    app.run(debug=True)
