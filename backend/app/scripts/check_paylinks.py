# check_paylinks.py
import firebase_admin
from firebase_admin import credentials, firestore

# -----------------------------
# Initialize Firebase
# -----------------------------
if not firebase_admin._apps:
    cred = credentials.Certificate(r"C:\Users\USER\PycharmProjects\Payla.ng\backend\payla-elite-firebase-adminsdk.json")  # replace with your service account path
    firebase_admin.initialize_app(cred)

db = firestore.client()

# -----------------------------
# Fetch all paylinks
# -----------------------------
def list_paylinks():
    docs = db.collection("paylinks").stream()
    print(f"{'Username':<20} {'User ID':<35} {'Active':<10} {'Display Name'}")
    print("-"*80)

    for doc in docs:
        data = doc.to_dict()
        username = data.get("username")
        user_id = data.get("user_id")
        active = data.get("active", False)
        display_name = data.get("display_name", "")
        print(f"{username:<20} {user_id:<35} {str(active):<10} {display_name}")

if __name__ == "__main__":
    list_paylinks()
