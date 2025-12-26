# services/layla_service.py
from datetime import datetime, timezone
from app.core.firebase import db
from app.models.user_model import User
from app.core.email import send_email # Your email sender utility
from app.utils.Layla_templates import Layla_TEMPLATES
from google.cloud.firestore_v1.base_query import FieldFilter

class LaylaOnboardingService:
    def __init__(self):
        self.sender = "Layla • Payla <layla@payla.vip>"
        self.interval_days = 3 # Prestige spacing

    def send_immediate_welcome(self, user: User):
        """Triggers Step 1 instantly upon onboarding."""
        try:
            template = Layla_TEMPLATES[1]
            # Template 1 expects (full_name, username)
            html = template["html"](user.full_name, user.username)
            
            send_email(
                to=user.email,
                subject=template["subject"],
                html=html,
                sender=self.sender
            )

            # Atomic update: Set step to 1 and log the date
            db.collection("users").document(user.id).update({
                "onboarding_step": 1,
                "last_nudge_date": datetime.now(timezone.utc)
            })
        except Exception as e:
            print(f"Layla Error (Step 1): {e}")

    def run_daily_automation(self):
        """
        The 'Worker' function. Call this via a Cron Job or Cloud Function.
        It finds users who are ready for the next lesson.
        """
        now = datetime.now(timezone.utc)
        
        # Query users who have started (Step >= 1) but haven't finished (Step < 5)
        users_ref = db.collection("users")\
                      .where(filter=FieldFilter("onboarding_step", ">=", 1))\
                      .where(filter=FieldFilter("onboarding_step", "<", 5)).stream()

        for doc in users_ref:
            user = User(**doc.to_dict())
            
            # Check if interval has passed
            last_date = user.last_nudge_date or user.created_at
            if (now - last_date).days >= self.interval_days:
                self._dispatch_next_step(user)

    def _dispatch_next_step(self, user: User):
        """Sends the next email in the sequence (2 through 5)."""
        next_step = user.onboarding_step + 1
        template = Layla_TEMPLATES.get(next_step)
        
        if not template:
            return

        try:
            # All templates from 2-5 only expect (username)
            html = template["html"](user.username)
            
            send_email(
                to=user.email,
                subject=template["subject"],
                html=html,
                sender=self.sender
            )

            db.collection("users").document(user.id).update({
                "onboarding_step": next_step,
                "last_nudge_date": datetime.now(timezone.utc)
            })
            print(f"Layla: Step {next_step} delivered to {user.username}")
        except Exception as e:
            print(f"Layla Error (Step {next_step}): {e}")