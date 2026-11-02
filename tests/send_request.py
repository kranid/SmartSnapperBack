import base64
import json
import os
from datetime import datetime, timezone

import requests

# Fixtures live next to this script.
tests_dir = os.path.dirname(os.path.abspath(__file__))

# Paths to the files
json_file_path = os.path.join(tests_dir, "original.json")
image_file_path = os.path.join(tests_dir, "screenshot.jpg")
base64_file_path = os.path.join(tests_dir, "screenshot.b64")

# Read the JSON file for the semantic description
with open(json_file_path, "r", encoding="utf-8") as f:
    snapnodes = json.load(f)

# Read the prepared Base64 and verify that it represents screenshot.jpg.
with open(base64_file_path, "r", encoding="ascii") as f:
    image_base64 = f.read().strip()
with open(image_file_path, "rb") as f:
    image_bytes = f.read()
if base64.b64decode(image_base64, validate=True) != image_bytes:
    raise ValueError("tests/screenshot.b64 does not match tests/screenshot.jpg")

payload = {
    "snapshotId": "snap-local-e2e",
    "snapnodes": snapnodes,
    "image_base64": image_base64,
    "platform": "android",
    "capturedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
}

# The URL of the running server
url = os.getenv("CHECK_SNAPSHOT_URL", "http://kranid.ru:8000/checkSnapshot")
headers = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "X-Debug-Client": "tests/send_request.py",
}
session = requests.Session()
session.trust_env = False

# Send the POST request
try:
    print(f"Sending request to the server: {url}")
    response = session.post(url, json=payload, headers=headers, timeout=120)
    print(f"Response URL: {response.url}")
    print(f"Response status: {response.status_code}")
    response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)

    # Print the response from the server
    response_body = response.json()
    if response.status_code != 201:
        raise AssertionError(f"Expected 201 Created, got {response.status_code}")
    if response_body.get("snapshotId") != payload["snapshotId"]:
        raise AssertionError("Response snapshotId does not match the request")
    if response_body.get("status") != "completed":
        raise AssertionError("Response status is not completed")
    if not isinstance(response_body.get("taskId"), str) or not response_body["taskId"]:
        raise AssertionError("Response taskId is missing")
    if not isinstance(response_body.get("violations"), list):
        raise AssertionError("Response violations must be an array")
    print("Server response:")
    print(json.dumps(response_body, ensure_ascii=False, indent=2))

except requests.exceptions.RequestException as e:
    print(f"An error occurred: {e}")
except json.JSONDecodeError:
    print("Failed to decode server response as JSON. Raw response:")
    print(response.text)
