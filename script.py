import logging
import threading
import os
import time
from flask import Flask, jsonify, request
from ogn.client import AprsClient
from ogn.parser import parse

app = Flask(__name__)

# Configure Flask and Gunicorn logging
gunicorn_logger = logging.getLogger('gunicorn.error')
app.logger.handlers = gunicorn_logger.handlers
app.logger.setLevel(gunicorn_logger.level)

# Configure additional logging for debugging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(levelname)s: %(message)s',
                    filename='app.log',
                    filemode='a')

# Use a list to store all messages
messages = []
lock = threading.Lock()
stop_event = threading.Event()

def keep_alive_ping(client):
    """
    Send periodic keep-alive pings to maintain the connection
    """
    while not stop_event.is_set():
        try:
            # Send a dummy message or perform a connection check
            client.sock.send(b'\r\n')
            app.logger.debug('Sent keep-alive ping')
            time.sleep(60)  # Ping every 60 seconds
        except Exception as e:
            app.logger.error(f"Keep-alive ping failed: {e}")
            break

def process_beacon(raw_message):
    """
    Process incoming beacon messages
    """
    global messages
    app.logger.debug('Processing beacon message')
    try:
        parsed_message = parse(raw_message)
        # Filter out comment messages and ensure latitude and longitude are present
        if parsed_message.get('aprs_type') != 'comment' and 'latitude' in parsed_message and 'longitude' in parsed_message:
            with lock:
                messages.append(parsed_message)
                # Limit message history to prevent unbounded growth
                if len(messages) > 1000:
                    messages = messages[-1000:]
                app.logger.debug(f"Message added: {parsed_message}")
    except Exception as e:
        app.logger.error(f"Failed to parse message: {raw_message}. Error: {e}")

def start_ogn_client():
    """
    Start OGN client with robust connection handling
    """
    app.logger.debug('Starting OGN client')
    aprs_user = os.getenv('APRS_USER', 'N0CALL')
    
    while not stop_event.is_set():
        try:
            # Create a new client for each connection attempt
            client = AprsClient(aprs_user=aprs_user)
            client.connect()
            
            # Start keep-alive thread
            keep_alive_thread = threading.Thread(target=keep_alive_ping, args=(client,))
            keep_alive_thread.daemon = True
            keep_alive_thread.start()
            
            app.logger.info('OGN client connected successfully')
            
            # Run the client with a callback
            client.run(callback=process_beacon, autoreconnect=True)
        
        except KeyboardInterrupt:
            app.logger.info("Stopping OGN client...")
            break
        except Exception as e:
            app.logger.error(f"OGN client connection error: {e}")
            
            # Wait before attempting to reconnect
            app.logger.info("Attempting to reconnect in 30 seconds...")
            time.sleep(30)

@app.route('/data', methods=['GET'])
def get_data():
    """
    Endpoint to retrieve recent beacon messages
    """
    app.logger.info('Accessed /data route')
    num_messages = request.args.get('num', default=10, type=int)
    with lock:
        filtered_messages = [msg for msg in messages if 'latitude' in msg and 'longitude' in msg]
        if filtered_messages:
            app.logger.debug(f"Returning {num_messages} messages")
            return jsonify(filtered_messages[-num_messages:])
        else:
            app.logger.warning('No data available')
            return jsonify({"error": "No data available"}), 204

@app.route('/', methods=['GET'])
def index():
    """
    Simple index route
    """
    app.logger.info('Accessed index route')
    return "OGN API is running. Access /data to get the latest messages."

def cleanup():
    """
    Cleanup function to gracefully stop threads
    """
    stop_event.set()
    app.logger.info("Initiating cleanup")

if __name__ == "__main__":
    try:
        # Start the OGN client in a separate thread
        ogn_thread = threading.Thread(target=start_ogn_client)
        ogn_thread.daemon = True
        ogn_thread.start()

        # Run the Flask app on a specific IP address and port
        app.run(host='0.0.0.0', port=5000)
    except KeyboardInterrupt:
        cleanup()
    finally:
        cleanup()