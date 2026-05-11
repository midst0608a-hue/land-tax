import requests
import base64

payload = {
    "contents": [{
        "parts": [
            {"text": "Hello"},
            {
                "inlineData": {
                    "mimeType": "application/pdf",
                    "data": base64.b64encode(b"dummy_pdf_content").decode('utf-8')
                }
            }
        ]
    }]
}

url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=invalid_key"
response = requests.post(url, headers={"Content-Type": "application/json"}, json=payload)
print(f"Status Code: {response.status_code}")
print(f"Response: {response.text}")
