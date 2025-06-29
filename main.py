from flask import Flask, request, jsonify
import requests
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# External API base URL
EXTERNAL_API_URL = "http://fi8.bot-hosting.net:20980/get"

@app.route('/download')
def download():
    """
    Proxy endpoint that forwards requests to the external API
    Expected parameter: id (spotify_song_id)
    """
    # Get the spotify_song_id from query parameters
    spotify_song_id = request.args.get('id')
    
    # Validate that id parameter is provided
    if not spotify_song_id:
        return jsonify({"error": "Missing required parameter 'id'"}), 400
    
    try:
        # Make request to external API
        logger.info(f"Making request to external API with id: {spotify_song_id}")
        
        external_url = f"{EXTERNAL_API_URL}?id={spotify_song_id}"
        response = requests.get(external_url, timeout=30)
        
        # Log the response status
        logger.info(f"External API response status: {response.status_code}")
        
        # Return the same response from external API
        if response.status_code == 200:
            # Try to parse as JSON
            try:
                json_response = response.json()
                return jsonify(json_response)
            except ValueError:
                # If not valid JSON, return as text
                return response.text, response.status_code
        else:
            # Forward error responses as well
            try:
                error_response = response.json()
                return jsonify(error_response), response.status_code
            except ValueError:
                return {"error": f"External API error: {response.status_code}"}, response.status_code
                
    except requests.exceptions.Timeout:
        logger.error("Request to external API timed out")
        return jsonify({"error": "Request timed out"}), 504
    
    except requests.exceptions.ConnectionError:
        logger.error("Failed to connect to external API")
        return jsonify({"error": "Failed to connect to external service"}), 503
    
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error: {str(e)}")
        return jsonify({"error": "Failed to fetch data from external service"}), 500

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "message": "API is running"})

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=False) # Set debug=False for production
