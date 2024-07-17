import json
import threading
from flask import Flask, jsonify, request
from ogn.client import AprsClient
from ogn.parser import parse

app = Flask(__name__)

# Use a list to store all messages
messages = []
lock = threading.Lock()

def process_beacon(raw_message):
    global messages
    try:
        parsed_message = parse(raw_message)
        # Filter out comment messages and ensure latitude and longitude are present
        if parsed_message.get('aprs_type') != 'comment' and 'latitude' in parsed_message and 'longitude' in parsed_message:
            with lock:
                messages.append(parsed_message)
    except Exception as e:
        print(f"Failed to parse message: {raw_message}. Error: {e}")

def start_ogn_client():
    client = AprsClient(aprs_user='N0CALL')
    client.connect()

    try:
        client.run(callback=process_beacon, autoreconnect=True)
    except KeyboardInterrupt:
        print("\nStopping OGN client...")
        client.disconnect()

@app.route('/data', methods=['GET'])
def get_data():
    num_messages = request.args.get('num', default=10, type=int)  # Get the 'num' parameter from the query string, default to 10 if not provided
    with lock:
        filtered_messages = [msg for msg in messages if 'latitude' in msg and 'longitude' in msg]
        if filtered_messages:
            print('Sending Data')
            return jsonify(filtered_messages[-num_messages:])  # Return the last 'num_messages' filtered messages
        else:
            return jsonify({"error": "No data available"}), 204

@app.route('/', methods=['GET'])
def index():
    return "OGN API is running. Access /data to get the latest messages."

if __name__ == "__main__":
    ogn_thread = threading.Thread(target=start_ogn_client)
    ogn_thread.daemon = True
    ogn_thread.start()

    # Run the Flask app on a specific IP address
    app.run(host='localhost', port=5000)
