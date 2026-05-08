import requests
import json
import uuid
import sys

# Create a mock session via the test script
# Since the server isn't running in background easily we will just run the FastAPI function directly

from main import app, SESSION_STORE
from fastapi.testclient import TestClient

client = TestClient(app)

session_id = str(uuid.uuid4())
SESSION_STORE[session_id] = {
    "order_id": "TEST", 
    "photos": [b"mockimage" * 1000], 
    "frame_id": "Cinema.png", 
    "mirror": False
}

r = client.get(f"/api/session/{session_id}/preview?filter_name=Cold")
print(f"Status Code: {r.status_code}")
if r.status_code != 200:
    print(f"Error: {r.text}")

