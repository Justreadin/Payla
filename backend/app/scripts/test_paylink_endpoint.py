import sys
import os

# Add project root (payla-backend) to sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))  # two levels up
sys.path.append(PROJECT_ROOT)

# Now import main
from main import app
from fastapi.testclient import TestClient
from app.core.firebase import db


client = TestClient(app)

def test_paylink(username: str):
    username_clean = username.lower().strip()
    print(f"Testing paylink lookup for username: '{username_clean}'")

    # Direct Firestore query
    docs = db.collection("paylinks").where("username", "==", username_clean).limit(1).get()
    print(f"Firestore returned {len(docs)} document(s)")

    if docs:
        data = docs[0].to_dict()
        print("Document data:")
        for k, v in data.items():
            print(f"  {k}: {v}")
    else:
        print("No document found in Firestore")

    # Call FastAPI route via TestClient
    response = client.get(f"/api/paylinks/{username_clean}")
    print(f"\nFastAPI response status: {response.status_code}")
    try:
        print("FastAPI response JSON:")
        print(response.json())
    except Exception as e:
        print("Failed to parse JSON:", e)

if __name__ == "__main__":
    test_paylink("favour")
