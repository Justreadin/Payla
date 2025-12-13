# userchecker.py
import firebase_admin
from firebase_admin import auth, credentials
import os

# --- CONFIGURE PATH TO SERVICE ACCOUNT JSON ---
# Replace with your path to the Firebase service account JSON
cred_path = os.path.join(os.getcwd(), "./payla-elite-firebase-adminsdk.json")

# Initialize Firebase Admin SDK if not already initialized
if not firebase_admin._apps:
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)

def check_user(email: str):
    found = False
    for user in auth.list_users().iterate_all():
        if user.email == email:
            print(f"✅ Found user in Firebase Auth: {user.uid}")
            found = True
            break
    if not found:
        print(f"❌ User not found in Firebase Auth: {email}")

if __name__ == "__main__":
    test_email = "paylaopal@gmail.com"  # replace with the email you want to check
    check_user(test_email)
