import base64
import json
import os

import requests

# Construct the absolute path to the root directory
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Paths to the files
json_file_path = os.path.join(root_dir, "original.json")
image_file_path = os.path.join(root_dir, "screenshot.jpg")

# Read the JSON file for the semantic description
with open(json_file_path, "r", encoding="utf-8") as f:
    snapnodes = json.load(f)

# Read the image file and encode it in base64
with open(image_file_path, "rb") as f:
    image_bytes = f.read()
    image_base64 = base64.b64encode(image_bytes).decode("utf-8")

payload = {
    "snapnodes": snapnodes,
    "image_base64": image_base64,
}

# The URL of the running server
url = "http://localhost:8000/checkSnapshot"

# Send the POST request
try:
    print("Sending request to the server...")
    response = requests.post(url, json=payload)
    response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)

    # Print the response from the server
    print("Server response:")
    print(json.dumps(response.json(), ensure_ascii=False, indent=2))

except requests.exceptions.RequestException as e:
    print(f"An error occurred: {e}")
except json.JSONDecodeError:
    print("Failed to decode server response as JSON. Raw response:")
    print(response.text)
