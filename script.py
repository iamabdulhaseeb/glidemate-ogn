import logging
import threading
from flask import Flask, jsonify, request
from ogn.client import AprsClient
from ogn.parser import parse

app = Flask(__name__)

# Configure Flask and Gunicorn logging
gunicorn_logger = logging.getLogger('gunicorn.error')
app.logger.handlers = gunicorn_logger.handlers
app.logger.setLevel(gunicorn_logger.level)

# Configure additional logging for debugging
logging.basicConfig(level=logging.DEBUG,  # Set the logging level
                    format='%(asctime)s %(levelname)s: %(message)s',
                    filename='app.log',  # Specify the log file
                    filemode='a')  # Append mode

# Use a list to store all messages
messages = []
lock = threading.Lock()

def process_beacon(raw_message):
    global messages
    app.logger.debug('Process Beacon')
    try:
        parsed_message = parse(raw_message)
        # Filter out comment messages and ensure latitude and longitude are present
        if parsed_message.get('aprs_type') != 'comment' and 'latitude' in parsed_message and 'longitude' in parsed_message:
            with lock:
                messages.append(parsed_message)
    except Exception as e:
        app.logger.error(f"Failed to parse message: {raw_message}. Error: {e}")

def start_ogn_client():
    app.logger.debug('In client start')
    client = AprsClient(aprs_user='N0CALL')
    client.connect()

    try:
        client.run(callback=process_beacon, autoreconnect=True)
    except KeyboardInterrupt:
        app.logger.info("\nStopping OGN client...")
        client.disconnect()

@app.route('/data', methods=['GET'])
def get_data():
    app.logger.info('Accessed data route.')
    num_messages = request.args.get('num', default=10, type=int)  # Get the 'num' parameter from the query string, default to 10 if not provided
    with lock:
        app.logger.info('In lock')
        filtered_messages = [msg for msg in messages if 'latitude' in msg and 'longitude' in msg]
        app.logger.info(filtered_messages)
        if filtered_messages:
            app.logger.info('Sending data')
            return jsonify(filtered_messages[-num_messages:])  # Return the last 'num_messages' filtered messages
        else:
            app.logger.info('In else')
            return jsonify({"error": "No data available"}), 204

@app.route('/', methods=['GET'])
def index():
    app.logger.info('Accessed index route.')
    return "OGN API is running. Access /data to get the latest messages."

if __name__ == "__main__":
    # Start the OGN client in a separate thread
    ogn_thread = threading.Thread(target=start_ogn_client)
    ogn_thread.daemon = True
    ogn_thread.start()

    # Run the Flask app on a specific IP address and port
    app.run(host='0.0.0.0', port=5000)
