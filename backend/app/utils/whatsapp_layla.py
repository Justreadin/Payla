# utils/whatsapp_layla.py
WHATSAPP_MESSAGES = {
    # 3 days before due
    "gentle_nudge": """
Hi {name} ♡

Layla here from Payla.

Just a little whisper – your invoice of {amount} is due in 3 days ({due_date}).

Here’s your private link:
{link}

Tap once and you’re done. I’ll take care of the rest.

With love,  
Layla
    """.strip(),

    # 1 day before
    "tomorrow": """
{name},

Layla again ♡

Your invoice is due tomorrow ({due_date}).

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

Your invoice of {amount} is due today.

Here’s your link (takes 10 seconds):
{link}

Let’s start the week beautifully.

Your assistant,  
Layla ♡
    """.strip(),

    # On due date – evening (soft)
    "due_today_evening": """
{name},

Layla checking in gently ♡

Your invoice is still open for today.

Whenever you’re ready:
{link}

No rush. I’ll be right here.

Softly,  
Layla
    """.strip(),

    # 1 day overdue – kind
    "one_day_over": """
Hi {name},

Layla here ♡

I noticed your invoice slipped by one day. Life happens.

Here’s the link again – no judgment:
{link}

I’m holding space for you.

Always,  
Layla
    """.strip(),

    # 3+ days overdue – still warm, slightly firmer
    "few_days_over": """
{name},

It’s Layla.

Your invoice is now {days} days past due.

I know you’re busy building beautiful things.

Let’s close this gently:
{link}

I believe in you.

Yours,  
Layla ♡
    """.strip(),

    # Payment received – the one that makes them cry (happy tears)
    "payment_received": """
{name}!!!

Layla here – jumping with joy ♡

Your payment of {amount} just landed safely.

Invoice settled. You’re all good.

Thank you for trusting me (and Payla).

You’re amazing.

With so much gratitude,  
Layla
    """.strip(),

    # First-time welcome (sent after first invoice created)
    "first_invoice": """
Hi {name},

I’m Layla – your new personal assistant at Payla ♡

From today, I’ll handle all your reminders, confirm payments, and make everything feel effortless.

You create. I’ll take care of the money.

Can’t wait to work together.

Warmly,  
Layla
    """.strip()
}