from waitress import serve
import os
from api import API
import logging

app = API()

from app import app  # Make sure this imports your API app correctly

port = int(os.environ.get("PORT", 8000))

try:
    logging.info(f"Starting server on port {port}...")
    print(f"Starting server on port {port}...")
    serve(app, host='0.0.0.0', port=port)
except Exception as e:
    logging.error(f"Failed to start the server: {e}")
    print(f"Failed to start the server: {e}")
    raise

# gunicorn -w 4 -b 127.0.0.1:8000 app:app
# python -m venv venv
# venv/Scripts/activate  --windows
# source venv/bin/activate  --linux

# pip install -r requirements.txt




