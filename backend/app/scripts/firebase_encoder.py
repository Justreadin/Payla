import base64
import json

# Open your Firebase JSON credentials file
with open("payla-elite-firebase-adminsdk.json", "r") as f:
    # Read the JSON content as a string
    json_content = f.read()

# Encode the string into bytes, then to base64
encoded = base64.b64encode(json_content.encode('utf-8')).decode('utf-8')

# Print the encoded string
print(encoded)
