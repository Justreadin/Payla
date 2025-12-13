from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from firebase_admin import firestore
from datetime import datetime
from app.models.user_model import User

db = firestore.client()
router = APIRouter(prefix="/users", tags=["Users"])


# 🧩 Create new user
@router.post("/", response_model=User)
def create_user(user: User):
    user_ref = db.collection("users").document(user.id)
    if user_ref.get().exists:
        raise HTTPException(status_code=400, detail="User already exists")

    user_dict = user.dict(by_alias=True)
    user_dict["created_at"] = datetime.utcnow()
    user_dict["updated_at"] = datetime.utcnow()

    user_ref.set(user_dict)
    return user_dict


# 🔍 Get user by ID
@router.get("/{user_id}", response_model=User)
def get_user(user_id: str):
    user_doc = db.collection("users").document(user_id).get()
    if not user_doc.exists:
        raise HTTPException(status_code=404, detail="User not found")
    return user_doc.to_dict()


# 🧾 Update user details
@router.put("/{user_id}", response_model=User)
def update_user(user_id: str, updates: dict):
    user_ref = db.collection("users").document(user_id)
    if not user_ref.get().exists:
        raise HTTPException(status_code=404, detail="User not found")

    updates["updated_at"] = datetime.utcnow()
    user_ref.update(updates)

    updated = user_ref.get().to_dict()
    return updated

#////Admin//////
# ❌ Delete user (admin-level)
@router.delete("/{user_id}")
def delete_user(user_id: str):
    user_ref = db.collection("users").document(user_id)
    if not user_ref.get().exists:
        raise HTTPException(status_code=404, detail="User not found")
    user_ref.delete()
    return {"message": "User deleted successfully"}


# 📊 Get all users (optional, for admin dashboards)
@router.get("/", response_model=list[User])
def list_users():
    users = []
    docs = db.collection("users").stream()
    for doc in docs:
        users.append(doc.to_dict())
    return users
