import requests
import base64
import json
import os

# Construct the absolute path to the root directory
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Paths to the files
json_file_path = os.path.join(root_dir, 'original.json')
image_file_path = os.path.join(root_dir, 'screenshot.jpg')
prompt_file_path = os.path.join(root_dir, 'promt.kt')

# Read the system prompt from promt.kt
with open(prompt_file_path, 'r', encoding='utf-8') as f:
    content = f.read()
    start = content.find('"""') + 3
    end = content.rfind('"""')
    system_prompt = content[start:end].strip()

# Read the JSON file for the semantic description
with open(json_file_path, 'r', encoding='utf-8') as f:
    semantic_data = json.load(f)

# Combine the system prompt and the semantic data with a clearer instruction
combined_prompt = (
    system_prompt + 
    "\n\nВот семантическое описание в json, которое нужно проанализировать:\n" + 
    json.dumps(semantic_data, ensure_ascii=False, indent=2)
)

# Read the image file and encode it in base64
with open(image_file_path, 'rb') as f:
    image_bytes = f.read()
    image_base64 = base64.b64encode(image_bytes).decode('utf-8')

payload = {
    "prompt": combined_prompt,
    "image_base64": image_base64
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
