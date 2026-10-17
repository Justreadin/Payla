# Updated README

```markdown
# Payla

Payment identity for Nigerian creators and freelancers. A creator claims `payla.ng/@username`, receives payments directly into their connected bank account via Paystack, and on Silver gets branded invoices, automated reminders from Layla, payment tracking, analytics, and receipts.

**Stack:** FastAPI · Firebase (Auth + Firestore) · Paystack · Resend · Termii · Cloudinary · Railway

**Live:** [payla.ng](https://payla.ng) · [payla.vip](https://payla.vip) (Silver)

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Architecture](#architecture)
3. [Environment Variables](#environment-variables)
4. [Product Model](#product-model)
5. [Directory Layout](#directory-layout)
6. [Key Systems](#key-systems)
7. [Data Model](#data-model)
8. [Email System](#email-system)
9. [Reminders & Layla](#reminders--layla)
10. [Subscriptions & Entitlement](#subscriptions--entitlement)
11. [Domains & URLs](#domains--urls)
12. [Testing](#testing)
13. [Deployment](#deployment)
14. [Conventions](#conventions)
15. [Troubleshooting](#troubleshooting)

---

## Quick Start

```bash
# Clone and enter
git clone https://github.com/yourorg/payla.ng.git
cd payla.ng/backend

# Create venv
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # Unix

# Install deps
pip install -r requirements.txt

# Configure .env (see Environment Variables)
cp .env.example .env
# Edit .env with real credentials

# Run
python run.py
```

Server starts at `http://127.0.0.1:8000`. In development, `DEBUG=True` enables:
- Docs at `/docs`
- Frontend auto-reload watcher
- Hot reload on file changes

For the Layla onboarding cron (usually Railway-scheduled):

```bash
python -m app.worker
```

---

## Architecture

Three layers:

**1. Frontend (vanilla HTML/CSS/JS)**
- No framework, no build step
- Static files served by FastAPI from `frontend/`
- JS is ES modules loaded directly by the browser
- One page per surface: `payla.html` (landing), `invoice.html`, `profile.html`, `paylink.html`, etc.

**2. FastAPI backend**
- All routes under `/api/*` except static file serving and public pages
- Firestore as the only persistent store
- Firebase Auth for user identity (JWT bearer tokens)
- External integrations handled by dedicated service modules

**3. Background tasks**
- Four asyncio loops start on app boot: reminder loop, billing loop, cleanup loop, bank confirmation scheduler
- One Railway-scheduled worker: Layla onboarding cron
- All loops are per-process; multi-worker deployments need dedicated workers (see Deployment)

**Data flow for a payment:**

```
Client clicks pay → Paystack checkout → charge.success webhook
                  → _process_merchant_payment (transaction)
                  → _record_payout (payout history)
                  → _create_payment_notification (in-app)
                  → dispatch_payment_receipts (email)
```

Every side effect after the transaction is best-effort. A notification failure never rolls back a recorded payment.

---

## Environment Variables

Required in `.env` at the backend root. All are read by `app/core/config.py` via Pydantic `Settings`.

### Core

| Variable | Purpose | Example |
|---|---|---|
| `ENVIRONMENT` | `development` or `production` | `production` |
| `DEBUG` | Must be `False` in production | `False` |
| `BACKEND_URL` | Canonical base for API callbacks and absolute links (webhook URLs, verification links, subscription return URLs) | `https://payla.ng` |
| `VIP_BASE_URL` | Premium paylink domain | `https://payla.vip` |
| `FRONTEND_URL` | Base for browser redirects and client-facing links | `https://payla.ng` |
| `SUBSCRIPTION_CALLBACK_URL` | Paystack post-checkout redirect | `https://payla.ng/subscription` |
| `APP_BASE_URL` | Base for verification links | `https://payla.ng` |

Today `BACKEND_URL` and `FRONTEND_URL` resolve to the same value. They are kept separate so that a future split (API subdomain, CDN for static assets) does not require a find-and-replace across the codebase. When in doubt, use `BACKEND_URL` for anything the server produces and `FRONTEND_URL` for anything the browser should land on.

### Firebase

| Variable | Purpose |
|---|---|
| `PAYLA_FIREBASE_KEY` | Base64-encoded service account JSON |
| `GOOGLE_APPLICATION_CREDENTIALS` | Optional path fallback |

### Paystack

| Variable | Purpose |
|---|---|
| `PAYSTACK_SECRET_KEY` | Main account secret |
| `PAYSTACK_PUBLIC_KEY` | Main account public |
| `PAYSTACK_SECRET_PAYLA` | Payla sub-account secret |
| `PAYSTACK_PUBLIC_PAYLA` | Payla sub-account public |
| `PAYSTACK_CLIENT_INVOICE_FEES_ENABLED` | Toggle client-paid fees |
| `PAYSTACK_FOUNDING_SILVER_MONTHLY_PLAN_CODE` | Paystack plan code for founding monthly |
| `PAYSTACK_FOUNDING_SILVER_YEARLY_PLAN_CODE` | Founding yearly |
| `PAYSTACK_SILVER_MONTHLY_PLAN_CODE` | Standard monthly |
| `PAYSTACK_SILVER_YEARLY_PLAN_CODE` | Standard yearly |

### Pricing

| Variable | Purpose |
|---|---|
| `PAYLA_SILVER_MONTHLY_PRICE_NGN` | Standard monthly price (₦) |
| `PAYLA_SILVER_YEARLY_PRICE_NGN` | Standard yearly price |
| `PAYLA_FOUNDING_SILVER_MONTHLY_PRICE_NGN` | Founding monthly |
| `PAYLA_FOUNDING_SILVER_YEARLY_PRICE_NGN` | Founding yearly |

### Email

| Variable | Purpose |
|---|---|
| `RESEND_API_KEY` | Resend API key |
| `GMAIL_USER`, `GMAIL_PASS` | Legacy — SMTP fallback |
| `LAYLA_USER`, `LAYLA_EMAIL_PASS` | Legacy — Layla SMTP |

### SMS / WhatsApp

| Variable | Purpose |
|---|---|
| `TERMII_API_KEY` | Termii SMS |
| `TERMII_SENDER_ID` | SMS sender name (default `Payla`) |
| `WHATSAPP_TOKEN` | Meta Graph API token |
| `WHATSAPP_PHONE_ID` | Meta phone number ID |
| `WHATSAPP_TEMPLATE_NAME` | Meta template name |

**Note on WhatsApp:** These variables are provisioned but unused in production. WhatsApp is gated off in the frontend via `WHATSAPP_CHANNEL_STATUS = "disabled"` in `frontend/js/config.js`. The backend will accept WhatsApp in `channels_selected` if it is sent, but the frontend never sends it. Flip the flag to `"active"` when Meta approval completes. See [Reminders & Layla](#reminders--layla) and the handoff document for the full enablement checklist.

### Storage

| Variable | Purpose |
|---|---|
| `CLOUDINARY_CLOUD_NAME` | Cloudinary account |
| `CLOUDINARY_API_KEY` | API key |
| `CLOUDINARY_API_SECRET` | API secret |

### Worker intervals

| Variable | Default | Purpose |
|---|---|---|
| `REMINDER_CHECK_INTERVAL_SECONDS` | `60` | Reminder loop cadence |
| `REMINDER_MAX_RETRIES` | `3` | Send attempts per channel |
| `REMINDER_RETRY_INTERVAL_SECONDS` | `300` | Retry backoff |
| `REMINDER_LOCK_TIMEOUT_MINUTES` | `10` | Lock expiry |

---

## Product Model

### Tiers

**Free (permanent)**
- Personal `payla.ng/@username` link
- Branded payment page
- Payment history via payouts page
- Direct payments to connected bank account
- No subscription, no card, no time limit

**Silver (paid)**
- Branded invoices clients can pay directly
- Layla automated reminders via SMS and email (WhatsApp coming soon)
- Custom reminder messages
- Payment tracking (outstanding/paid)
- Payment analytics and paylink analytics
- Branded PDF receipts
- Logo on payment page, custom invoice branding
- Silver seal ("Powered by Payla Silver")
- VIP domain: `payla.vip/@username` option
- Automatic invoice closure after payment

**Pricing:** ₦7,500/month or ₦75,000/year
**Founding offer:** First 200 customers lock the founding price permanently. If they cancel and resubscribe, they keep the rate.

The "permanently" guarantee is enforced by the `founding_member_ever: true` flag on the user document. A returning founder keeps their founding pricing fields (`founding_monthly_price_ngn`, `founding_yearly_price_ngn`) across resubscription. No slot is re-reserved on their behalf. See [Subscriptions & Entitlement](#subscriptions--entitlement).

### Payment flow

```
Client → Paystack checkout → charge.success webhook
  ├── Payment document written
  ├── Invoice/paylink marked paid
  ├── Payout record created
  ├── In-app notification
  └── Creator receipt email
```

Payla never holds funds. All settlement is Paystack → connected bank account.

---

## Directory Layout

```
backend/
├── main.py                      # FastAPI app, routes, startup
├── run.py                       # uvicorn launcher
├── requirements.txt
├── .env
├── app/
│   ├── core/
│   │   ├── config.py            # Pydantic Settings
│   │   ├── constants.py         # FOUNDING_LIMIT, username rules
│   │   ├── firebase.py          # Firestore client, storage bucket
│   │   ├── auth.py              # get_current_user, onboarding_guard
│   │   ├── subscription.py      # Entitlement, require_silver
│   │   ├── security.py          # SecurityHeadersMiddleware
│   │   ├── reminder_config.py   # Quiet hours, delivery hour
│   │   ├── payla_urls.py        # paylink_url, invoice_url builders
│   │   ├── paystack.py          # Paystack API helpers
│   │   └── notifications.py     # create_notification
│   │
│   ├── routers/                 # All FastAPI routes
│   │   ├── auth_router.py
│   │   ├── user_router.py
│   │   ├── onboarding_router.py
│   │   ├── founding_router.py
│   │   ├── profile_router.py
│   │   ├── paylink_router.py
│   │   ├── invoice_router.py
│   │   ├── payout_router.py
│   │   ├── receipt_router.py
│   │   ├── subscription_router.py
│   │   ├── reminder_router.py
│   │   ├── dashboard_router.py
│   │   ├── notifications_router.py
│   │   ├── analytics_router.py
│   │   ├── marketing_router.py  # Dormant. Kept for possible reactivation.
│   │   ├── webhooks.py          # Paystack webhook entry
│   │   └── token_gate.py
│   │
│   ├── models/                  # Pydantic models
│   │   ├── user_model.py
│   │   ├── invoice_model.py
│   │   ├── paylink_model.py
│   │   ├── payout_model.py
│   │   ├── founding_model.py
│   │   ├── onboarding_model.py
│   │   ├── profile_model.py
│   │   └── reminder_model.py
│   │
│   ├── services/
│   │   ├── paystack.py
│   │   ├── payout.py
│   │   ├── channels.py          # send_via_whatsapp/sms/email
│   │   ├── email_service.py     # auth + founding emails
│   │   ├── billing_service.py   # Resend dispatcher
│   │   ├── receipt_service.py   # Payment alert dispatcher
│   │   ├── reminder_service.py  # Helpers for the reminder loop
│   │   ├── subscription_webhooks.py  # Idempotent subscription events
│   │   └── layla_service.py     # Onboarding sequence
│   │
│   ├── tasks/
│   │   ├── reminder_service_loop.py
│   │   ├── billing_reminder.py
│   │   ├── reminder_cleanup.py
│   │   ├── marketing_service_loop.py  # Dormant. Commented out in main.py.
│   │   └── bank_confirmation_retry.py
│   │
│   ├── utils/
│   │   ├── email_render/        # Shared email rendering system
│   │   │   ├── tokens.py
│   │   │   ├── document.py
│   │   │   ├── components.py
│   │   │   ├── render.py
│   │   │   └── __init__.py
│   │   ├── Layla_templates.py           # 5-email onboarding
│   │   ├── invoice_reminder_templates.py # 7-stage client reminders
│   │   ├── receipt_templates.py         # Creator payment alert
│   │   ├── billing_templates.py         # Silver expiring/grace
│   │   ├── sms_layla.py                 # SMS copy
│   │   ├── whatsapp_layla.py            # WhatsApp copy
│   │   ├── name_match.py                # Fuzzy name matcher
│   │   ├── firebase.py                  # firestore_run (async wrapper)
│   │   ├── marketing.py                 # Dormant. Kept for possible reactivation.
│   │   ├── security.py
│   │   └── worker.py                    # Railway cron entry
│   │
│   └── scripts/
│       ├── migrate_waitlist.py
│       ├── backfill_logos.py
│       ├── test_silver_expiry.py
│       ├── test_payment_receipt.py
│       └── ...
│
├── frontend/
│   ├── payla.html               # Landing
│   ├── invoice.html
│   ├── profile.html
│   ├── paylink.html
│   ├── onboarding.html
│   ├── subscription.html
│   ├── dashboard.html
│   ├── entry.html
│   ├── i/
│   │   └── public_invoice.html
│   ├── invoice_receipt.html
│   ├── css/
│   └── js/
│
├── uploads/
└── assets/
```

**Dormant modules:** `marketing_router.py`, `marketing_service_loop.py`, and `marketing.py` exist but are not wired into the running app. `marketing_service_loop.py` is commented out in `main.py`. They are kept because the marketing loop may be reactivated. Do not delete without confirming with the maintainer.

---

## Key Systems

### Payment webhook

`POST /api/webhooks/paystack` — HMAC verified. Routes events into three paths:

1. **Subscription events** (`subscription.*`, `charge.*` with `subscription` metadata) → `handle_subscription_event`
2. **Transfer events** (`transfer.*`) → payout status updates
3. **Merchant payments** (`charge.success`/`charge.failed`) → `_process_merchant_payment`

Idempotency: every path writes a marker before returning. Duplicate Paystack deliveries are no-ops.

Review states: if a charge can't be reconciled (amount mismatch, missing source), the marker is written with `status: "review_required"` and the webhook returns 503 so Paystack retries. `_reconcile_existing_success` handles cases where the payment exists but the marker was lost.

### Entitlement

`app/core/subscription.py` is the source of truth.

```python
get_subscription_status(user) → {
    "is_active": bool,
    "in_grace_period": bool,
    "days_left_in_grace": int,
    "end": datetime | None,
}

can_access_silver_features(user) → bool
```

Rules:
- `plan` must be in `PAID_PLANS = {"silver", "gold", "opal"}`
- `subscription_end` (or `next_billing_date`) must be in the future
- State must not be in `INACTIVE_STATES`
- Grace: 7 days after `subscription_end` for `past_due`/`payment_failed`/`unpaid`
- Voluntary cancellation preserves access until `subscription_end`
- `manual_silver_override` grants access (server-managed only)

`require_silver` is the FastAPI dependency for routes that need paid access. It re-reads Firestore, evaluates entitlement, and raises 403 with `subscription_required` if denied.

The 7-day grace value lives in `app/core/subscription.py`. `billing_templates.py` imports it from there — if the grace window changes, billing emails follow automatically. Do not duplicate the number into a template.

### Payout record

`_record_payout` creates a payout document exactly once per reference. Uses a Firestore transaction and returns `False` if the payout already exists. Updates `last_payout_at` and increments `total_invoice_revenue` or `total_paylink_revenue`.

Estimated arrival date uses working-day logic (Friday + 3, Saturday + 2, Sunday + 1, otherwise + 1). This is an **estimate and an approximation**. It does not account for Nigerian public holidays. Treat it as a UI hint, not a settlement promise.

---

## Data Model

Firestore document shapes for the collections most likely to be inspected during debugging. Field names are authoritative. Optional fields are marked `?`. Timestamps are Firestore `Timestamp` unless noted.

### `users/{uid}`

```jsonc
{
  "uid": "string",
  "email": "string",
  "display_name": "string",
  "username": "string",                  // unique, matches USERNAME_PATTERN
  "phone": "string?",
  "onboarding_complete": true,

  // Subscription
  "plan": "free | silver | gold | opal",
  "subscription_status": "active | past_due | unpaid | payment_failed | non_renewing | cancelled | expired",
  "subscription_end": "Timestamp?",
  "next_billing_date": "Timestamp?",
  "cancel_at_period_end": false,
  "manual_silver_override": false,       // server-managed only
  "paystack_customer_code": "string?",
  "paystack_subscription_code": "string?",

  // Founding
  "founding_member_ever": false,
  "founding_monthly_price_ngn": 0,
  "founding_yearly_price_ngn": 0,
  "founding_overflow_review_required": false,   // set if validation failed

  // Domain
  "preferred_domain": "ng | vip",        // vip requires Silver

  // Totals
  "last_payout_at": "Timestamp?",
  "total_invoice_revenue": 0,
  "total_paylink_revenue": 0,

  "created_at": "Timestamp",
  "updated_at": "Timestamp"
}
```

### `paylinks/{username}`

```jsonc
{
  "username": "string",
  "user_id": "string",
  "link_url": "string",                  // rebuilt on domain change
  "preferred_domain": "ng | vip",
  "avatar_url": "string?",
  "business_name": "string?",
  "active": true,
  "created_at": "Timestamp",
  "updated_at": "Timestamp"
}
```

### `invoices/{id}`

```jsonc
{
  "id": "string",
  "short_id": "string",                  // public URL key
  "user_id": "string",
  "client_name": "string",
  "client_email": "string?",             // stored as string today; see Troubleshooting
  "client_phone": "string?",
  "amount_kobo": 0,
  "currency": "NGN",
  "description": "string",
  "due_date": "Timestamp",
  "status": "draft | sent | paid | cancelled",
  "paid_at": "Timestamp?",
  "payment_reference": "string?",
  "created_at": "Timestamp",
  "updated_at": "Timestamp"
}
```

### `reminders/{id}`

```jsonc
{
  "id": "string",
  "invoice_id": "string",
  "user_id": "string",
  "stage": "string",                     // see Reminders & Layla
  "channels_selected": ["email", "sms"], // "whatsapp" gated off today
  "method_priority": ["sms", "email"],
  "status": "pending | sent | failed | cancelled | archived",
  "active": true,
  "next_send": "Timestamp",
  "retries": 0,
  "last_error": "string?",
  "locked_until": "Timestamp?",
  "locked_by": "string?",
  "created_at": "Timestamp",
  "updated_at": "Timestamp"
}
```

### `processed_merchant_payments/{reference}`

```jsonc
{
  "reference": "string",
  "status": "processed | review_required",
  "amount_kobo": 0,
  "user_id": "string?",
  "reason": "string?",                   // present when status is review_required
  "processed_at": "Timestamp"
}
```

### `founding_offer/state`

```jsonc
{
  "available_slots": 200,
  "reserved_count": 0,
  "claimed_count": 0
}
```

### `subscription_events/{event_id}`

Idempotency markers for subscription webhook events. Shape is intentionally minimal: a marker is presence-only.

```jsonc
{
  "event": "string",
  "reference": "string",
  "user_id": "string?",
  "received_at": "Timestamp"
}
```

---

## Email System

Every email in the product flows through `app/utils/email_render/`.

### The wrapper

```python
from app.utils.email_render import render_email
from app.utils.email_render.components import (
    heading, eyebrow, paragraph, callout, mono, divider,
    button, state_line, sign_off,
)

html = render_email(
    title="Subject line",
    blocks=[
        heading("Main heading"),
        paragraph("Body text"),
        button("Action", "https://..."),
        sign_off("I'll be in touch."),
    ],
)
```

Returns a complete HTML document. Pass the result to any sender. Never build bare `<div>` fragments.

### The iPhone fix

`document.py` exists for one reason: Apple Mail was rendering emails with a white background. The fix is triple-nested backgrounds:

1. `<body>` with `background-color` (some clients respect this)
2. Full-width `<table>` with `bgcolor` attribute (legacy Apple Mail path)
3. `<td>` with both `bgcolor` and `background-color` (belt and braces)

Plus `<meta name="color-scheme" content="dark only">` and `<meta name="supported-color-schemes" content="dark only">` to prevent iOS auto-inversion. And no `min-height: 100vh` anywhere — email clients handle vh unreliably and it causes phantom scroll.

If an email renders white on iPhone, the template is not using `render_email()`. Find the template file, confirm it calls the wrapper, rewrite if it builds HTML directly.

### Design tokens

`tokens.py` holds the palette, type scale, and spacing constants. Same values as `payla.css`. Do not hardcode colors or sizes in templates — import from tokens.

Key values:
- Canvas: `#0A0A0A`
- Rose gold: `#E8B4B8`
- Text: `#FDFDFD`, `#B8B8B8`, `#7A7A7A`
- Card radius: 20px (web cards use 16px; this is intentional, do not unify)
- Border: `rgba(232, 180, 184, 0.15)`
- Shadow: `0 24px 60px rgba(0, 0, 0, 0.5)`

### Sign-off

Every email ends with the same block:

```
I'll be in touch.
— Layla
PAYLA
```

Managed by `sign_off()`. Only the closing line varies ("Talk soon.", "Always here.", "With love."). The `— Layla` em dash is the single permitted exception to the no-em-dash copy rule.

### Template modules

| File | Purpose | Audience |
|---|---|---|
| `Layla_templates.py` | 5-email onboarding sequence | New user |
| `email_service.py` | Verification, password reset, founding verification | Auth flows |
| `billing_templates.py` | Silver expiring, grace period | Subscriber |
| `receipt_templates.py` | Payment alert (creator) | Creator |
| `invoice_reminder_templates.py` | 7-stage client reminders | Client |

### Senders

Four senders exist. Two are sync, two are async, and the split is historical rather than principled. The renderer does not know about senders; the sender does not know about templates. Keep that separation.

| Sender | Style | Used by |
|---|---|---|
| `app/core/email.py::send_email` | sync, `requests` | Base helper, legacy paths |
| `app/services/email_service.py::send_email` | sync, `requests` | Auth + founding emails |
| `app/services/receipt_service.py::_send_via_resend` | async, `httpx` | Payment receipt alerts |
| `app/services/billing_service.py::dispatch_billing_email` | async, `httpx` | Billing lifecycle emails |

Consolidating these is a future cleanup, not an urgent task. New email code should pick the sender whose style matches the surrounding call path.

### Adding a new email

There are four steps. The fourth is where most people get stuck.

1. **Write the render function** in the appropriate template module. It takes a typed context and returns `render_email(...)`. Example:

   ```python
   # app/utils/receipt_templates.py
   from app.utils.email_render import render_email
   from app.utils.email_render.components import (
       heading, paragraph, button, sign_off,
   )

   def render_payout_confirmation(amount_display: str, bank_last4: str) -> str:
       return render_email(
           title="Payout on the way",
           blocks=[
               heading("Your payout is on the way."),
               paragraph(f"{amount_display} is heading to your account ending {bank_last4}."),
               button("View payouts", "https://payla.ng/payouts"),
               sign_off("Talk soon."),
           ],
       )
   ```

2. **Register the template** in the module's `TEMPLATES` dict, if the module has one. Modules without a dict are called directly by name.

3. **Call it from the service.** The service owns context assembly and dispatch. Templates do not fetch data.

4. **Watch for the dispatcher's `inspect.signature` filter.** `render_invoice_reminder()` in `invoice_reminder_templates.py` filters context keys against the target template's signature before calling. If you call a reminder template directly instead of through the dispatcher, it will fail with `TypeError: render_X() got an unexpected keyword argument`. Always go through the dispatcher for reminder templates. For other modules, there is no filter — pass exactly the arguments the signature declares.

---

## Reminders & Layla

### The loop

`app/tasks/reminder_service_loop.py` runs every 60 seconds (configurable). It finds reminders with `status: "pending"`, `active: true`, `next_send <= now`, and processes each one.

Per-reminder locking: `acquire_reminder_lock` sets a Firestore lock with a 10-minute timeout. Concurrent workers skip locked reminders.

Quiet hours: 21:00–06:00 UTC (22:00–07:00 WAT). A reminder due during quiet hours is **deferred** — `next_send` is pushed to the next quiet-hours exit, the lock is released, and the loop moves on. The reminder fires at the next cycle after quiet hours end.

Retries: 3 attempts per channel, 5 minutes between retries. After 3 failures, the channel is logged as failed and the reminder stays pending for a future cycle.

### Channel dispatch

`send_via_whatsapp`, `send_via_sms`, `send_via_email` in `app/services/channels.py`. Each is async and raises on failure. The loop handles retries.

WhatsApp is gated by `WHATSAPP_CHANNEL_STATUS` in `frontend/js/config.js`. While `"disabled"`, the frontend never sends `whatsapp` in `method_priority`, and the chip is greyed with a "Soon" badge. To enable, see the handoff document's enablement checklist. The frontend is the only gate today; adding a `WHATSAPP_ENABLED` boolean to `Settings` and short-circuiting in `channels.py` is optional defense-in-depth.

### Reminder copy

| Stage | WhatsApp key | SMS key | Email type |
|---|---|---|---|
| First contact | `first_invoice` | `first` | `first_contact` |
| 3 days before | `gentle_nudge` | `gentle` | `reminder` |
| 1 day before | `tomorrow` | `tomorrow` | `reminder_2` |
| Due today | `due_today_morning/evening` | `due_today` | `due_today` |
| 1 day overdue | `one_day_over` | `one_day_over` | `overdue_gentle` |
| 3-6 days overdue | `few_days_over` | `few_days_over` | `overdue_firm` |
| 7+ days overdue | `few_days_over` | `final_nudge` | `overdue_firm` |
| Paid | `payment_received` | `paid` | (receipt) |

Stage selection: `map_templates()` in `reminder_service.py`. Determines stage based on `trigger_date` vs `due_date`.

### Onboarding cron

`app/utils/worker.py` is run by Railway on a schedule. It calls `LaylaOnboardingService.run_daily_automation()`, which finds users mid-sequence and sends the next email. Interval is 3 days between steps.

Sequence: Welcome → Why Payla exists → From numbers to names → The awkward part (Silver variant if paid, soft bridge if free) → Once you choose a standard.

`worker.py` wraps a sync service method in `asyncio.run()`. Firestore and Resend calls block the event loop. This is fine for a once-a-day cron with no other work. Do not refactor without a specific reason.

---

## Subscriptions & Entitlement

### Status reference

| `subscription_status` | Silver access? | Set by | Cleared by |
|---|---|---|---|
| `active` | Yes | `charge.success` (initial or renewal) | Next state transition |
| `past_due` | Yes, for 7 days grace | `invoice.payment_failed`, `charge.failed` (renewal) | `charge.success` renewal, or grace expiry → `expired` |
| `unpaid` | Yes, for 7 days grace | Paystack `invoice.*` failed state | `charge.success`, or grace expiry → `expired` |
| `payment_failed` | Yes, for 7 days grace | `charge.failed` variants | `charge.success`, or grace expiry → `expired` |
| `non_renewing` | Yes, until `subscription_end` | `POST /api/subscription/cancel` | `subscription_end` passes → `expired` |
| `cancelled` | No | `subscription.disable` (voluntary) | New subscription → `active` |
| `expired` | No | `subscription.expire`, grace expiry, `subscription.disable` | New subscription → `active` |

On transition to `cancelled` or `expired`: `cancel_at_period_end` is cleared, `preferred_domain` reverts to `"ng"` on both user and paylink documents, and `link_url` is rebuilt. The `.vip` URL still resolves for shared links; it redirects to `.ng`.

### Checkout flow

```
User clicks Get Silver → /api/subscription/start/{plan_key}
  ├── Lock checkout (subscription_checkout_locks)
  ├── Reserve founding slot if applicable (founding_reservations)
  ├── Create pending_subscriptions document
  ├── Verify Paystack plan amount/interval matches config
  └── Return authorization_url

User completes Paystack checkout → charge.success webhook
  ├── _process_initial_charge (transaction)
  │   ├── Verify amount matches pending
  │   ├── Set plan, subscription_status, subscription_end
  │   ├── Claim founding slot if applicable
  │   └── Write subscription_events marker
  └── User gets access immediately
```

### Renewal

`charge.success` with `data.subscription` extends `subscription_end`. Same idempotency pattern.

### Cancellation

Voluntary: `POST /api/subscription/cancel` calls `disable_subscription` on Paystack, then sets `cancel_at_period_end: true` and `subscription_status: "non_renewing"`. User keeps access until `subscription_end`.

Involuntary (renewal failure): `invoice.payment_failed` or `charge.failed` sets `subscription_status: "past_due"`. Entitlement check grants 7 days of grace. If no successful renewal within grace, access ends.

### Expiry

When `subscription.expire` or `subscription.disable` fires:
- `subscription_status` is set to `"expired"` (or `"cancelled"`)
- `cancel_at_period_end` is cleared
- `preferred_domain` reverts to `"ng"` on the user document
- The paylink document is updated: `preferred_domain: "ng"`, `link_url` rebuilt to `payla.ng/@username`

The `.vip` URL still resolves for shared links; it redirects to `.ng`. See [Domains & URLs](#domains--urls) for the redirect mechanics.

### Founding

`founding_offer/state` is a Firestore document with `available_slots`, `reserved_count`, `claimed_count`. Reservations are claimed or released atomically.

Returning founders: `founding_member_ever: true` on the user document means they keep the founding price on future subscriptions. Their pricing fields (`founding_monthly_price_ngn`, `founding_yearly_price_ngn`) are preserved. This flag is what makes "permanently" true. No new slot is reserved or claimed when a returning founder resubscribes.

---

## Domains & URLs

### Payla has three domains in play

| Domain | Purpose |
|---|---|
| `payla.ng` | Primary. Landing page, dashboard, invoices, free paylinks. |
| `payla.vip` | Silver feature. Premium paylink domain. Both domains serve the same page; the preferred one is canonical. |
| `app.payla.ng` | Legacy CORS origin. No active use. |

### URL builders

`app/core/payla_urls.py`:

```python
paylink_url(username, domain="ng") → str
invoice_url(short_id) → str
```

`paylink_url` respects `domain`: `"ng"` builds `https://payla.ng/@username`, `"vip"` builds `https://payla.vip/@username`.

### Domain canonicalization

`serve_paylink_page` in `main.py` reads the paylink document's `preferred_domain`:
- If `preferred_domain = "vip"` and request host is `payla.ng` → redirect to `payla.vip`
- If `preferred_domain = "ng"` and request host is `payla.vip` → redirect to `payla.ng`
- Unknown hosts (localhost, Railway internal) serve as-is

**Redirects are 302 (temporary), not 301.** `preferred_domain` is mutable. A user downgrading from Silver flips it back to `"ng"`; if the earlier `.ng` → `.vip` redirect were cached as permanent by a browser, the user's link would keep bouncing to `.vip` indefinitely for that client. 302 prevents that. Do not change to 301 without solving browser cache invalidation on downgrade.

No redirect loops. Every shared URL resolves. The non-canonical domain redirects to the preferred one.

### VIP entitlement

`preferred_domain = "vip"` requires Silver. Enforced at three points:
- `POST /api/profile/update` — checks `can_access_silver_features()`
- `POST /api/paylinks/` — same check
- `POST /api/subscription/start` — N/A, but the update gates block it

Free users can have `preferred_domain = "ng"` only. Silver users can flip to `"vip"` any time.

---

## Testing

### Test scripts

Two live in `app/scripts/`:

**`test_silver_expiry.py`** — Proves the Silver expiry webhook path:
- Seeds a Silver user on `.vip`
- Fires `subscription.expire`
- Asserts status flips to `"expired"`, domain reverts to `"ng"`, `link_url` rebuilds to `.ng`
- Proves idempotency (duplicate event is no-op)
- Proves `subscription.not_renew` does not revert domain (still has paid access)
- Proves subsequent `subscription.expire` on a fresh subscription reverts correctly

Run: `python -m app.scripts.test_silver_expiry`

**`test_payment_receipt.py`** — Proves the full payment pipeline:
- Seeds a Silver creator, paylink, invoice, payment attempt
- Fires `_process_merchant_payment` + `_create_payment_notification` + `dispatch_payment_receipts`
- Asserts every side effect: payment record, invoice closed, attempt closed, payout history, user totals, notification, receipt marker
- Proves idempotency: firing twice doesn't double totals
- Mocks `receipt_service._send_via_resend` to avoid real Resend calls

Run: `python -m app.scripts.test_payment_receipt`

### Manual verification

Real-user spot checks are often faster than synthetic tests for things like entitlement gates:

1. **Free user tries `.vip`** — log in as Free, hit `/api/profile/update` with `{"preferred_domain": "vip"}` via devtools. Should return 403 `silver_required`.
2. **Silver user toggles `.vip`** — log in as Silver, toggle `.vip` in profile, save. Check Firestore: `preferred_domain: "vip"` on both user and paylink docs.
3. **Public redirect** — visit `payla.ng/@vipusername` from the browser. Should redirect to `payla.vip/@vipusername` with a 302.
4. **Downgrade redirect** — flip a user to `"vip"`, visit `.ng`, confirm the browser follows to `.vip`, then downgrade (set `preferred_domain: "ng"`), and confirm the browser follows `.vip` back to `.ng` on next visit. This only works because the redirect is 302.
5. **WhatsApp gating** — open `/invoice`, step 2. WhatsApp chip should be greyed with "Soon". Create an invoice with reminders, check Firestore reminder doc: `channels_selected` should never include `"whatsapp"`.

### What's not tested

- Full HTTP path through `POST /api/webhooks/paystack` (HMAC verification) — manual test via Paystack dashboard
- Real Resend delivery — mock used in `test_payment_receipt.py`
- Real Paystack charges — test mode only
- iPhone email rendering — manual test on Apple Mail iOS
- Entitlement gate HTTP path — was covered by `test_entitlement_gate.py`, deleted due to infrastructure flakiness (httpx/TestClient incompatibility, `email-validator` rejecting test domains, transient gRPC drops). Verify manually using the steps above.

---

## Deployment

### Railway

The backend runs on Railway. Three processes:

1. **Web service** — `python run.py`, serves the app and background loops
2. **Worker** — `python -m app.worker`, runs Layla's daily onboarding sequence
3. **Firestore** — external, managed by Firebase

### Environment

Set every variable from the Environment Variables section. Railway injects them at boot. `DEBUG=False` is required in production.

### Worker concurrency

The four asyncio loops in `main.py` run *per process*. If you scale to multiple web workers:
- Only one instance should run the reminder loop
- Only one should run the billing loop
- Only one should run the cleanup loop
- Only one should run the bank confirmation scheduler

All four are per-process and will duplicate work if scaled. Options:
- Keep a single web worker
- Move loops to a dedicated worker process
- Use distributed locking (Redis, Firestore-based leader election)

Currently the app runs a single web worker. If that changes, this needs addressing before scaling.

### DNS

`payla.ng` and `payla.vip` both CNAME to the Railway service. SSL is provisioned automatically via Railway's certificate manager. Dynadot manages the DNS records.

### Firestore

Region: `africa-south1`. Collections used:
- `users`, `paylinks`, `invoices`, `payments`, `payouts`
- `invoice_payment_attempts`, `paylink_transactions`
- `pending_subscriptions`, `subscription_checkout_locks`, `subscription_events`
- `founding_offer/state`, `founding_reservations`
- `notifications`, `processed_merchant_payments`, `reminders`

---

## Conventions

### Code style

- Python 3.12+, type hints on public functions
- FastAPI routers in `app/routers/`, service logic in `app/services/`
- Firestore queries use `FieldFilter`, not positional args
- Async I/O uses `httpx.AsyncClient`, sync I/O uses `requests`
- Firestore `.get()` calls in async paths use `firestore_run` wrapper

To find remaining positional `.where()` calls (PowerShell):

```powershell
Get-ChildItem -Path app -Recurse -Filter *.py | Select-String -Pattern '\.where\("'
```

Each hit should be wrapped with `FieldFilter`. The `UserWarning: Detected filter using positional arguments` in the startup log is the runtime signal.

### Naming

- `snake_case` for Python
- `kebab-case` for CSS classes (`paylink-card`, `bank-confirmation`)
- `camelCase` for JS variables
- `SCREAMING_SNAKE` for constants
- `.vip` is not written with a capital V anywhere

### Copy rules

These apply to user-facing copy and email templates, not to internal documentation or code comments.

- **No em dashes** in prose. Body text uses commas, periods, or restructures. The `— Layla` signature is the only exception.
- **No emojis.** None. Not in subjects, not in bodies, not in notifications.
- **"Name matched"** uniformly, not "Name confirmed."
- **"Sealed stamp"** for the trust mark, capital S.
- **"payla.ng/@username"** in prose, `<code>` in HTML where it's a literal string.

### Firestore patterns

- Every user-facing write is idempotent via a marker document
- Transactions complete all reads before any writes
- Never trust a webhook payload's `status` field for lifecycle events (use the event name)
- `total_earned` updates once per successful payment, inside the transaction that records the payment

### URL construction

- Never hardcode domain names. Use `settings.BACKEND_URL`, `settings.VIP_BASE_URL`, or `paylink_url()` / `invoice_url()`.
- Invoice URLs are never domain-scoped. Only paylinks respect `preferred_domain`.

---

## Troubleshooting

### "Cannot access local variable X" on startup

Some function is using a variable before assignment. Classic case: `counter_changed` in `_process_initial_charge`. Grep the traceback, add the initialization before the first `if` that might use it.

### Emails render white on iPhone

The `render_email()` wrapper is the fix. If an email goes white, it's not using the wrapper. Grep for the template file and confirm it calls `render_email()`. If it builds HTML directly, rewrite it.

### `TypeError: render_X() got an unexpected keyword argument`

The caller is passing extra context keys to a template that doesn't accept them. `render_invoice_reminder` filters context via `inspect.signature` — if a template is called directly instead of through the dispatcher, it will fail. Always go through `render_invoice_reminder()`.

### Reminder fails on client email

`InvoiceCreate.client_email` is `Optional[str]` today, not `Optional[EmailStr]`. Invalid emails are stored, then `send_via_email` throws when a reminder tries to reach them. Fix: change to `Optional[EmailStr]` in `app/models/invoice_model.py`. One-line change, catches bad data at the API boundary instead of at send time.

### Payment recorded but no notification

Notifications are best-effort. `_create_payment_notification` wraps in try/except and logs. If the payment doc exists but the notification doc doesn't, check the `payla` logger for the exception. Common cause: Firestore permission or a malformed document ID.

### Webhook returns 503

The event handler raised an exception. Paystack will retry. Check the logs for the exception. For payment events, `_write_review_marker` is the safe path — it records a `review_required` state that a future delivery can reconcile.

### Founding slot claimed but user isn't marked founder

Check `founding_offer/state` for the counter. Check `founding_reservations/{user_id}` for the reservation. The reservation must match the reference and slot. If validation failed, `founding_overflow_review_required` is set on the user doc and the error is logged.

### `.vip` link doesn't redirect

`serve_paylink_page` reads `preferred_domain` from the paylink doc. If the doc has `"ng"` but the user expects `.vip`, the profile update didn't mirror. Check:
1. User doc: `preferred_domain` field
2. Paylink doc: `preferred_domain` field
3. Both should match

If they don't, the profile update's mirror to paylink is failing. Check the `payla` logger for the update.

### Reminder fires during quiet hours

It shouldn't. If a reminder fires at 22:30 WAT, either:
- The quiet-hours check is broken (verify `is_within_quiet_hours` in `reminder_service_loop.py`)
- The reminder was created with `next_send` after the quiet window started and the loop didn't defer it

The deferral logic pushes `next_send` forward. If a reminder fires during quiet hours, the deferral didn't run. Check the `next_send` value in the reminder doc and the `is_within_quiet_hours` output for that timestamp.

### Free user has `.vip`

Should be impossible. Three gates prevent it:
- `update_profile` checks `can_access_silver_features()`
- `create_or_update_paylink` checks the same
- `serve_paylink_page` would serve on `.vip` but redirect if `preferred_domain="ng"` and the request arrives on `.vip`

If a Free user has `preferred_domain="vip"` on their doc, the profile gate has a bug. Grep `update_profile` in `profile_router.py` for the `requested_domain == "vip"` check. If it's missing, that's the bug.

### `UserWarning: Detected filter using positional arguments`

A `.where()` call is not using `FieldFilter`. Find it:

```powershell
Get-ChildItem -Path app -Recurse -Filter *.py | Select-String -Pattern '\.where\("'
```

Wrap each hit with `FieldFilter`. Most call sites are already wrapped; the warning fires only on the stragglers.

---

## Further Reading

- **Email system reference** — `docs/email-system.md` (one-page contract for `render_email()`, the iPhone-safe wrapper, tokens, and the dispatcher filter).
- **Handoff document** — the post-cleanup state of the codebase, what shipped, what's dormant, and what's blocked on external dependencies. Read once when onboarding; return to the README as the steady-state reference.
```

---

# Email System Reference

This is the companion doc referenced in the README's Further Reading. Save as `docs/email-system.md`.

```markdown
# Email System Reference

One page on how emails are built, why the wrapper is shaped the way it is, and what to check when a new template misbehaves. Read this before writing a new email or debugging a rendering issue.

**Live in:** `app/utils/email_render/`

---

## The contract

Every email goes through `render_email()`.

```python
from app.utils.email_render import render_email
from app.utils.email_render.components import (
    eyebrow, heading, paragraph, callout, mono, divider,
    button, state_line, sign_off,
)

html = render_email(
    title="Subject line",
    blocks=[
        eyebrow("INVOICE"),
        heading("Your invoice is on the way."),
        paragraph("Here is the amount and the due date."),
        button("View invoice", "https://payla.ng/i/abc123"),
        sign_off("Talk soon."),
    ],
)
```

**`render_email(title, blocks)` returns a complete HTML document.** `title` populates the `<title>` tag and the preheader. `blocks` is a list of component calls, in order. Every component returns an HTML string fragment; `render_email` wraps them in the document shell.

Never build bare `<div>` fragments and pass them to a sender. If a template does not call `render_email()`, it is a bug.

---

## The iPhone fix (why `document.py` is shaped this way)

Early emails rendered with a white background on Apple Mail iOS. The cause was ambiguous — iOS Mail was ignoring the `background-color` on `<body>` under dark mode auto-inversion. The fix is three independent background declarations so that at least one survives in every client:

1. `<body>` with `background-color: #0A0A0A`.
2. Full-width `<table>` with the legacy `bgcolor="#0A0A0A"` attribute (Apple Mail respects this path).
3. Inner `<td>` with **both** `bgcolor` and `background-color`.

Plus two meta tags that prevent iOS from inverting the palette:

```html
<meta name="color-scheme" content="dark only">
<meta name="supported-color-schemes" content="dark only">
```

And one hard rule: **no `min-height: 100vh` anywhere in the document.** Email clients handle `vh` inconsistently and it causes a phantom scroll bar on iOS. If a template needs vertical space, use padding.

If an email renders white on iPhone, the template bypassed `render_email()` or someone edited `document.py` and removed one of the three backgrounds. Check both.

---

## Tokens

`tokens.py` is the single source of truth for palette, type, and spacing. Templates import from it. Do not hardcode colors or sizes.

| Token | Value | Use |
|---|---|---|
| `CANVAS` | `#0A0A0A` | Page background |
| `CARD_TOP` | `#0F0F11` | Card gradient top |
| `CARD_MID` | `#09090B` | Card gradient middle |
| `CARD_BOTTOM` | `#050506` | Card gradient bottom |
| `ROSE_GOLD` | `#E8B4B8` | Accent, buttons, rules |
| `ROSE_GOLD_DEEP` | `#D89FA4` | Hover, secondary accents |
| `ROSE_GOLD_LIGHT` | `#F0C5C9` | Highlights |
| `HAIRLINE` | `rgba(232, 180, 184, 0.15)` | Card top edge |
| `TEXT_PRIMARY` | `#FDFDFD` | Headings, body |
| `TEXT_SECONDARY` | `#B8B8B8` | Secondary body |
| `TEXT_TERTIARY` | `#7A7A7A` | Captions, footnotes |
| `CARD_RADIUS` | `20px` | Email card corner radius |
| `CARD_SHADOW` | `0 24px 60px rgba(0, 0, 0, 0.5)` | Card shadow |

**Card radius is 20px in email, 16px on web.** This is intentional: smaller rendered sizes in email read tight at 16px. Do not unify the two values.

**Do not reference `#BD5878`.** That was an early aspiration that never shipped.

---

## Components

All in `components.py`. Each returns an HTML string.

| Function | Purpose |
|---|---|
| `eyebrow(text)` | Small uppercase label above a heading |
| `heading(text)` | Main heading, Playfair Display |
| `paragraph(text)` | Body copy, Inter |
| `callout(text)` | Highlighted block with rose-gold left rule |
| `mono(text)` | Technical string, monospace |
| `divider()` | Rose-gold hairline |
| `button(label, url)` | Primary CTA with rose-gold shimmer on hover |
| `state_line(text)` | Small state indicator (e.g., "SEALED") |
| `sign_off(closing)` | Standard sign-off block |

`sign_off()` is the only component that accepts variable copy by convention. Pass the closing line only ("Talk soon.", "Always here.", "With love.", "I'll be in touch."); the rest is fixed:

```
{closing}
— Layla
PAYLA
```

The `— Layla` em dash is the single permitted exception to the no-em-dash rule. It lives in `sign_off()` and nowhere else.

---

## Senders

The renderer does not know about senders. The sender does not know about templates. Keep that separation.

| Sender | Style | Used by |
|---|---|---|
| `app/core/email.py::send_email` | sync, `requests` | Base helper, legacy paths |
| `app/services/email_service.py::send_email` | sync, `requests` | Auth + founding emails |
| `app/services/receipt_service.py::_send_via_resend` | async, `httpx` | Payment receipt alerts |
| `app/services/billing_service.py::dispatch_billing_email` | async, `httpx` | Billing lifecycle emails |

Four senders, two styles. The split is historical rather than principled. Consolidation is a future cleanup, not urgent. New code should pick the sender whose style matches the surrounding call path.

---

## Adding a new email

Four steps. The fourth is where people get stuck.

### 1. Write the render function

In the appropriate template module. It takes a typed context and returns `render_email(...)`.

```python
# app/utils/receipt_templates.py
from app.utils.email_render import render_email
from app.utils.email_render.components import (
    heading, paragraph, button, sign_off,
)

def render_payout_confirmation(amount_display: str, bank_last4: str) -> str:
    return render_email(
        title="Payout on the way",
        blocks=[
            heading("Your payout is on the way."),
            paragraph(
                f"{amount_display} is heading to your account ending {bank_last4}."
            ),
            button("View payouts", "https://payla.ng/payouts"),
            sign_off("Talk soon."),
        ],
    )
```

### 2. Register the template

If the module has a `TEMPLATES` dict, add the key. If it does not, the function is called directly by name from the service. Check the module before assuming.

### 3. Call it from the service

The service owns context assembly and dispatch. Templates do not fetch data. If the template needs a user's name, the service passes it.

### 4. Watch for the dispatcher's `inspect.signature` filter

`render_invoice_reminder()` in `invoice_reminder_templates.py` filters context keys against the target template's signature before calling. If you call a reminder template directly instead of through the dispatcher, it fails with:

```
TypeError: render_X() got an unexpected keyword argument 'foo'
```

**Always go through the dispatcher for reminder templates.** For other modules, there is no filter, so pass exactly the arguments the signature declares.

---

## Checklist for a new template

Before you consider it done:

- [ ] Calls `render_email()`, not bare HTML
- [ ] Imports colors and sizes from `tokens.py`, no hardcoded hex
- [ ] No emojis anywhere
- [ ] No em dashes in prose (the `— Layla` sign-off is the exception)
- [ ] Ends with `sign_off(...)`
- [ ] Renders correctly in the local preview (open the returned HTML in a browser)
- [ ] If it is a reminder template, it goes through `render_invoice_reminder()`, not called directly
- [ ] If it accepts a client email, confirm the caller validates it (see the `EmailStr` note in the README's Troubleshooting)

---

## Debugging

**White background on iPhone.** Template bypassed `render_email()`, or `document.py` lost one of the three background layers. Check both.

**`TypeError: unexpected keyword argument`.** You called a reminder template directly instead of through the dispatcher. Use `render_invoice_reminder()`.

**Button looks wrong in Outlook.** Outlook does not support `border-radius` on `<a>` elements. The `button()` component uses a table-cell fallback. If you built a custom button, rebuild it with `button()`.

**Text is invisible on some clients.** iOS auto-inversion is overriding the palette. Confirm the two `color-scheme` meta tags are present in `document.py`.

**Layout breaks in Gmail.** Gmail strips `<style>` in some contexts. Confirm the template relies on inline styles for layout-critical properties. `document.py` inlines the shell; components inline their own styles.

---

## What not to do

- Do not build HTML fragments outside `render_email()`.
- Do not hardcode colors or radii. Import from tokens.
- Do not unify the 20px email radius with the 16px web radius. The difference is intentional.
- Do not add a fifth sender. If you need one, consolidate first.
- Do not put business logic in a template. Templates render; services decide what to render.
- Do not remove the triple-background from `document.py`. It looks redundant. It is not.
```