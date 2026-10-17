# services/layla_service.py
from datetime import datetime, timezone

from google.cloud.firestore_v1.base_query import FieldFilter

from app.core.email import send_email
from app.core.firebase import db
from app.models.user_model import User
from app.utils.Layla_templates import LAYLA_ONBOARDING


class LaylaOnboardingService:
    def __init__(self):
        self.sender = "Layla <layla@payla.vip>"
        self.interval_days = 3

    def send_immediate_welcome(self, user: User):
        """Triggers Step 1 instantly upon onboarding."""
        try:
            entry = LAYLA_ONBOARDING[1]
            html = entry["render"](user.full_name, user.username)

            send_email(
                to=user.email,
                subject=entry["subject"],
                html=html,
                sender=self.sender,
            )

            db.collection("users").document(user.id).update({
                "onboarding_step": 1,
                "last_nudge_date": datetime.now(timezone.utc),
            })
        except Exception:
            # Log, do not raise: a welcome email failure must not abort signup.
            import logging
            logging.getLogger("payla.layla").exception(
                "Layla step 1 failed for user %s",
                getattr(user, "id", "unknown"),
            )

    def run_daily_automation(self):
        """
        Worker entrypoint. Run from a cron job or Cloud Function.
        Finds users mid-sequence whose interval has elapsed.
        """
        now = datetime.now(timezone.utc)

        users_ref = (
            db.collection("users")
            .where(filter=FieldFilter("onboarding_step", ">=", 1))
            .where(filter=FieldFilter("onboarding_step", "<", 5))
            .stream()
        )

        for doc in users_ref:
            user = User(**doc.to_dict())

            last_date = getattr(user, "last_nudge_date", None) or getattr(
                user, "created_at", None
            )
            if last_date is None:
                continue

            if last_date.tzinfo is None:
                last_date = last_date.replace(tzinfo=timezone.utc)

            if (now - last_date).days >= self.interval_days:
                self._dispatch_next_step(user)

    def _dispatch_next_step(self, user: User):
        """Send the next email in the sequence (2 through 5)."""
        next_step = user.onboarding_step + 1
        entry = LAYLA_ONBOARDING.get(next_step)

        if not entry:
            return

        try:
            if next_step == 4 and entry.get("tier") == "conditional":
                plan = str(getattr(user, "plan", "free") or "free").lower()
                if plan in {"silver", "gold", "opal"}:
                    html = entry["render_silver"](user.username)
                else:
                    html = entry["render"](user.username)
            else:
                html = entry["render"](user.username)

            send_email(
                to=user.email,
                subject=entry["subject"],
                html=html,
                sender=self.sender,
            )

            db.collection("users").document(user.id).update({
                "onboarding_step": next_step,
                "last_nudge_date": datetime.now(timezone.utc),
            })

            import logging
            logging.getLogger("payla.layla").info(
                "Layla step %s delivered to %s",
                next_step,
                user.username,
            )

        except Exception:
            import logging
            logging.getLogger("payla.layla").exception(
                "Layla step %s failed for user %s",
                next_step,
                getattr(user, "id", "unknown"),
            )