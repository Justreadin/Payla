# utils/whatsapp_layla.py

WHATSAPP_MESSAGES = {
    # 3 days before due
    "gentle_nudge": """
Hi, Layla from Payla.

Your invoice for {business_name} ({amount}) is due in 3 days ({due_date}).

Complete it easily here: {link}

I’ll take care of the rest.
    """.strip(),

    # 1 day before
    "tomorrow": """
{name},

Layla again ♡

Your invoice for {business_name} is due tomorrow ({due_date}).

One quick tap and it’s settled:
{link}

You’ve got this.

Always here,  
Layla
    """.strip(),

    # On due date – morning
    "due_today_morning": """
Good morning {name} ☀

It’s Layla.

Your invoice for {business_name} of {amount} is due today.

Here’s your link (takes 10 seconds):
{link}

Let’s start the day beautifully.

Your assistant,  
Layla ♡
    """.strip(),

    # On due date – evening
    "due_today_evening": """
{name},

Layla checking in gently ♡

Your invoice for {business_name} is still open for today.

Whenever you’re ready:
{link}

No rush. I’ll be right here.

Softly,  
Layla
    """.strip(),

    # 1 day overdue
    "one_day_over": """

Hi, Layla here. Your payment for {business_name} is one day past due. Complete it easily here: {link}

    """.strip(),

    # 3+ days overdue
    "few_days_over": """
{name},

It’s Layla.

Your invoice for {business_name} is now {days} days past due.

Settle it now to keep your account in good standing: {link}

— Layla

    """.strip(),

    # Payment received
    "payment_received": """
Payment confirmed.

Your {amount} to {business_name} has been received.

Invoice settled, all done.

Thank you for trusting Payla.

— Layla
    """.strip(),

    # First-time welcome
    "first_invoice": """
Hi,

I’m Layla, your personal assistant at Payla.

From today, I’ll handle all transactions with {business_name}, making payments effortless.

You create. I handle the money.

Looking forward to working together.
    """.strip()
}

def get_layla_whatsapp(key: str, context: dict) -> str:
    template = WHATSAPP_MESSAGES.get(key, WHATSAPP_MESSAGES["gentle_nudge"])
    try:
        return template.format(**context)
    except KeyError as e:
        # Fallback to prevent crash if a key is missing
        return f"Hi! Layla here. Your invoice for {context.get('business_name', 'your project')} is ready: {context.get('link')}"