import requests
import json

bot_id = "c61ec4c9-deaf-4ce6-ba24-9f479e96c614"
org_id = "5c2228c1-c4a2-5bed-9468-464bd32df471"
api_key = "F3TO0pSqPJSP1qTGFmmIksLqKRFPNZtcJ3spALyISWw"

url = f"http://localhost:8000/api/chat/{bot_id}"
payload = {
    "message": "status id 31",
    "org_id": org_id,
    "session_id": "test_session_123"
}
headers = {
    "x-bot-key": api_key
}

print(f"Sending request to {url}...")
try:
    response = requests.post(url, json=payload, headers=headers, stream=True)
    print(f"Response status: {response.status_code}")
    for line in response.iter_lines():
        if line:
            print(line.decode('utf-8'))
except Exception as e:
    print(f"Error: {e}")
