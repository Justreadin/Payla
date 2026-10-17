"""
Layla's onboarding sequence.

Five emails. Sent by LaylaOnboardingService on a 3-day interval.

Emails 1, 2, 3, 5 go to every user, Free or Silver.
Email 4 has two variants: one for Free users (a soft door to Silver),
one for Silver users (the operational reality).

Templates take no arguments. The service composes values into them
via .format(**context) before passing to send_email().
"""

from app.utils.email_render import render_email
from app.utils.email_render.components import (
    heading,
    eyebrow,
    lead,
    paragraph,
    body_lines,
    bullet_list,
    pullquote,
    callout,
    mono,
    inline_highlight,
    divider,
    button,
    sign_off,
)


def _welcome(full_name: str, username: str) -> str:
    """Email 1. Sent immediately on signup."""
    first_name = full_name.split()[0] if full_name else "there"
    return render_email(
        title="Welcome to a new standard",
        blocks=[
            heading(f"Welcome {first_name}."),
            lead("I&rsquo;m <strong style=\"color:#FDFDFD;\">Layla</strong>."),
            paragraph(
                "I&rsquo;ll be guiding you through Payla, from your "
                f"{inline_highlight('payment identity')}, "
                "to client payments, reminders, invoices, and receipts."
            ),
            paragraph(
                "Everything here exists so you get paid cleanly, quickly, "
                "and without chasing."
            ),
            eyebrow("Over the next few weeks, I&rsquo;ll show you"),
            bullet_list([
                "What Payla is",
                "What it replaces",
                "How creators get paid without friction",
            ]),
            pullquote(
                "My emails are short. Intentional. Worth your time. "
                "One minute is all I need."
            ),
            paragraph(
                "Start now.<br>"
                "Share your Payla link with a client.<br>"
                "Add it to your bio.<br>"
                "Let it represent how you get paid."
            ),
            callout(
                f'<p style="font-family:\'Inter\',sans-serif; font-size:13px; '
                f'font-weight:600; letter-spacing:0.14em; text-transform:uppercase; '
                f'color:#B8B8B8; margin:0 0 12px 0;">Your payment identity</p>'
                f'<p style="margin:0;">{mono(f"payla.ng/@{username}", size="22px")}</p>'
            ),
            paragraph(
                "This isn&rsquo;t a payment link. It&rsquo;s your payment identity.",
                color="#FDFDFD",
            ),
            paragraph("Welcome to a new standard."),
            sign_off("I&rsquo;ll be in touch."),
        ],
    )


def _why_payla_exists(username: str) -> str:
    """Email 2. Positioning. Sent three days after email 1."""
    return render_email(
        title="Why Payla exists",
        blocks=[
            eyebrow("This is the problem"),
            body_lines([
                "You do the work.",
                "You deliver on time.",
                '<strong style="color:#FDFDFD;">Then you wait.</strong>',
            ]),
            body_lines([
                "You send your account number.",
                "You follow up.",
                "You wait again.",
            ]),
            pullquote(
                "&ldquo;Seen.&rdquo;<br>"
                "&ldquo;Will pay.&rdquo;<br>"
                "Tomorrow."
            ),
            paragraph(
                "Payla exists because this is "
                f"{inline_highlight('unacceptable')}.",
                color="#FDFDFD",
                size="18px",
            ),
            callout(
                '<p style="font-family:\'Inter\',sans-serif; font-size:16px; '
                'line-height:1.7; color:#B8B8B8; margin:0 0 6px 0;">'
                'Payla is not a payment app.</p>'
                '<p style="font-family:\'Inter\',sans-serif; font-size:16px; '
                'line-height:1.7; color:#B8B8B8; margin:0 0 6px 0;">'
                'It does not ask you to chase money.</p>'
                '<p style="font-family:\'Inter\',sans-serif; font-size:16px; '
                'line-height:1.7; color:#B8B8B8; margin:0;">'
                'It does not make you explain yourself.</p>'
            ),
            heading("Payla is your payment identity.", size="22px"),
            paragraph(
                "One name. One link. One standard.",
                color="#FDFDFD",
                strong=True,
            ),
            paragraph(
                "When you share your Payla link, you&rsquo;re not requesting payment. "
                "<strong style=\"color:#FDFDFD;\">You&rsquo;re setting terms.</strong>"
            ),
            paragraph(
                "No awkward reminders. No &ldquo;have you paid?&rdquo; messages. "
                "No silence. Just clarity."
            ),
            divider(),
            eyebrow("What Payla replaces"),
            paragraph("Account numbers. Screenshots. Excuses."),
            paragraph(
                "What Payla introduces is simpler. "
                "<strong style=\"color:#FDFDFD;\">A way to get paid "
                "that respects your time.</strong>"
            ),
            paragraph(
                "This is not for everyone. It&rsquo;s for people who "
                "take their work seriously.",
                color="#7A7A7A",
                size="14px",
            ),
            paragraph("If that&rsquo;s you, keep going.", color="#FDFDFD"),
            sign_off("Talk soon."),
        ],
    )


def _from_numbers_to_names(username: str) -> str:
    """Email 3. The identity argument. Sent three days after email 2."""
    return render_email(
        title="From numbers to names",
        blocks=[
            paragraph("Before Payla, you were a number."),
            body_lines([
                "An account number.",
                "A bank name.",
                "Something copied. Something pasted.",
            ]),
            body_lines([
                "Easy to forget.",
                "Easy to delay.",
                "Easy to ignore.",
            ]),
            paragraph(
                "That&rsquo;s not how professionals should get paid.",
                color="#FDFDFD",
                size="18px",
            ),
            paragraph(
                "Payla changes this by giving you a "
                f"{inline_highlight('name')}."
            ),
            callout(
                '<p style="font-family:\'Inter\',sans-serif; font-size:16px; '
                'line-height:1.7; color:#B8B8B8; margin:0 0 6px 0;">'
                'Not a username.</p>'
                '<p style="font-family:\'Inter\',sans-serif; font-size:16px; '
                'line-height:1.7; color:#B8B8B8; margin:0 0 6px 0;">'
                'Not a handle for fun.</p>'
                '<p style="font-family:\'Inter\',sans-serif; font-size:16px; '
                'line-height:1.7; color:#FDFDFD; font-weight:600; margin:0;">'
                'A payment identity.</p>'
            ),
            paragraph(
                mono(f"@{username}", size="26px"),
                color="#E8B4B8",
            ),
            paragraph(
                "A single name that represents:",
                color="#FDFDFD",
                strong=True,
            ),
            body_lines([
                "How you work.",
                "How you charge.",
                "How you get paid.",
            ]),
            paragraph(
                "Names carry weight. Numbers don&rsquo;t.",
                color="#FDFDFD",
                size="18px",
            ),
            paragraph(
                "When a client sees a number, they hesitate.<br>"
                "When they see a name, they remember."
            ),
            paragraph(
                "That&rsquo;s the difference.",
                color="#E8B4B8",
                strong=True,
            ),
            divider(),
            paragraph(
                "Your Payla name becomes the "
                "<strong style=\"color:#FDFDFD;\">point of payment</strong>."
            ),
            body_lines([
                "You don&rsquo;t send details.",
                "You don&rsquo;t explain.",
                "You don&rsquo;t remind.",
            ]),
            paragraph(
                "You share your name.",
                color="#FDFDFD",
                strong=True,
            ),
            paragraph("One name. Every client. Every time."),
            eyebrow("This is the identity system"),
            paragraph(
                "And once you&rsquo;re known by a name,<br>"
                "going back to being a number feels impossible."
            ),
            sign_off("Talk soon."),
        ],
    )


def _silver_bridge(username: str) -> str:
    """
    Email 4 (Free variant). The soft door to Silver.
    No price, no urgency, no pitch. Just what Silver is.
    """
    return render_email(
        title="When you're ready",
        blocks=[
            eyebrow("A quiet note"),
            heading("The awkward part is handled.", size="28px"),
            paragraph(
                "You&rsquo;ve claimed your name. Your clients can pay you "
                "directly through your Payla page. That&rsquo;s Free, and "
                "it stays that way."
            ),
            paragraph(
                "There&rsquo;s a second half to Payla, called Silver. It exists "
                "for one reason: the follow-up."
            ),
            callout(
                '<p style="font-family:\'Inter\',sans-serif; font-size:16px; '
                'line-height:1.7; color:#B8B8B8; margin:0 0 6px 0;">'
                'Reminders are sent.</p>'
                '<p style="font-family:\'Inter\',sans-serif; font-size:16px; '
                'line-height:1.7; color:#B8B8B8; margin:0 0 6px 0;">'
                'Invoices are tracked.</p>'
                '<p style="font-family:\'Inter\',sans-serif; font-size:16px; '
                'line-height:1.7; color:#B8B8B8; margin:0 0 6px 0;">'
                'Receipts are issued.</p>'
                '<p style="font-family:\'Inter\',sans-serif; font-size:16px; '
                'line-height:1.7; color:#FDFDFD; margin:0;">'
                'Automatically.</p>'
            ),
            paragraph(
                "Layla, on Silver, handles the part most people dread: "
                "asking again. She sends the reminders through WhatsApp, SMS, "
                "and email on your behalf. She closes invoices when payment "
                "arrives. She issues the receipts."
            ),
            paragraph(
                "You don&rsquo;t chase payments. "
                "You don&rsquo;t check your phone. "
                "You don&rsquo;t ask if someone has paid."
            ),
            paragraph(
                "Your client isn&rsquo;t pressured. And you aren&rsquo;t "
                "diminished.",
                color="#FDFDFD",
            ),
            pullquote("That balance matters."),
            divider(),
            paragraph(
                "There is no timer on this. Free is permanent. If and when "
                "the follow-up becomes the thing that costs you more than "
                "Silver does, it&rsquo;ll be waiting for you."
            ),
            button("See what Silver includes", "https://payla.ng/#pricing"),
            paragraph(
                "Until then, your link is live and your name is yours.",
                color="#FDFDFD",
            ),
            sign_off("I&rsquo;ll be in touch."),
        ],
    )


def _silver_operational(username: str) -> str:
    """
    Email 4 (Silver variant). The operational reality.
    Close to the original voice. Names Silver once, explicitly.
    """
    return render_email(
        title="The awkward part is handled",
        blocks=[
            eyebrow("Silver"),
            heading("The awkward part is handled.", size="28px"),
            paragraph(
                "Let&rsquo;s talk about the moment most people avoid."
            ),
            body_lines([
                "The transaction.",
                "The follow-ups.",
                "The uncomfortable silence after the work is done.",
            ]),
            paragraph(
                "This is where dignity is usually lost.",
                color="#E8B4B8",
                strong=True,
                size="18px",
            ),
            paragraph("Silver was designed to handle this part for you."),
            callout(
                '<p style="font-family:\'Inter\',sans-serif; font-size:16px; '
                'line-height:1.7; color:#B8B8B8; margin:0 0 6px 0;">'
                'Not loudly.</p>'
                '<p style="font-family:\'Inter\',sans-serif; font-size:16px; '
                'line-height:1.7; color:#B8B8B8; margin:0 0 6px 0;">'
                'Not aggressively.</p>'
                '<p style="font-family:\'Inter\',sans-serif; font-size:16px; '
                'line-height:1.7; color:#B8B8B8; margin:0;">'
                'Not awkwardly.</p>'
            ),
            paragraph(
                "Quietly. Correctly.",
                color="#E8B4B8",
                size="18px",
            ),
            paragraph(
                "With Silver, you don&rsquo;t chase payments. "
                "You don&rsquo;t check your phone. "
                "You don&rsquo;t ask if someone has paid."
            ),
            callout(
                '<p style="font-family:\'Inter\',sans-serif; font-size:16px; '
                'line-height:1.7; color:#B8B8B8; margin:0 0 6px 0;">'
                'Reminders are sent.</p>'
                '<p style="font-family:\'Inter\',sans-serif; font-size:16px; '
                'line-height:1.7; color:#B8B8B8; margin:0 0 6px 0;">'
                'Overdues are handled.</p>'
                '<p style="font-family:\'Inter\',sans-serif; font-size:16px; '
                'line-height:1.7; color:#B8B8B8; margin:0 0 6px 0;">'
                'Receipts are issued.</p>'
                '<p style="font-family:\'Inter\',sans-serif; font-size:16px; '
                'line-height:1.7; color:#FDFDFD; font-weight:600; margin:0;">'
                'Automatically.</p>'
            ),
            paragraph("On time. Every time."),
            paragraph(
                "Your client isn&rsquo;t pressured. And you aren&rsquo;t "
                "diminished."
            ),
            pullquote("That balance matters."),
            divider(),
            paragraph("Invoices are clear. Receipts are instant."),
            paragraph(
                "Payments go straight to your connected bank account.",
                color="#FDFDFD",
                strong=True,
            ),
            body_lines([
                "No screenshots.",
                "No explanations.",
                "No discomfort.",
            ]),
            paragraph(
                "Because the best payment systems don&rsquo;t interrupt the "
                "relationship.<br>"
                "<strong style=\"color:#FDFDFD;\">They protect it.</strong>"
            ),
            paragraph(
                "Silver exists so you can stay focused on your work, "
                "while the transaction takes care of itself."
            ),
            paragraph(
                "This is how it should feel to get paid.",
                color="#E8B4B8",
                strong=True,
                size="17px",
            ),
            sign_off("Talk soon."),
        ],
    )


def _once_you_choose_a_standard(username: str) -> str:
    """Email 5. Permanence. Sent three days after email 4."""
    return render_email(
        title="Once you choose a standard",
        blocks=[
            paragraph("This is the part most people don&rsquo;t think about."),
            body_lines([
                "Standards don&rsquo;t ask to be renewed.",
                "They don&rsquo;t compete.",
                "They don&rsquo;t downgrade.",
            ]),
            paragraph(
                "Once you choose one, you don&rsquo;t go back.",
                color="#FDFDFD",
                size="18px",
            ),
            paragraph(
                "Your Payla name is permanent. It&rsquo;s yours. "
                "It doesn&rsquo;t expire. It doesn&rsquo;t change."
            ),
            callout(
                '<p style="font-family:\'Inter\',sans-serif; font-size:16px; '
                'line-height:1.7; color:#B8B8B8; margin:0 0 6px 0;">'
                'It becomes how clients recognize you.</p>'
                '<p style="font-family:\'Inter\',sans-serif; font-size:16px; '
                'line-height:1.7; color:#B8B8B8; margin:0 0 6px 0;">'
                'How payments reach you.</p>'
                '<p style="font-family:\'Inter\',sans-serif; font-size:16px; '
                'line-height:1.7; color:#FDFDFD; font-weight:600; margin:0;">'
                'How your work is remembered.</p>'
            ),
            paragraph(
                "That&rsquo;s the lock-in.",
                color="#E8B4B8",
                strong=True,
                size="18px",
            ),
            paragraph("Not force. Not friction. Familiarity."),
            paragraph(
                "Once people know how to pay you, "
                "they don&rsquo;t need to be reminded."
            ),
            pullquote(
                "And once you experience getting paid with clarity, "
                "everything else feels like noise."
            ),
            divider(),
            eyebrow("You&rsquo;re not a user here. You&rsquo;re a VIP."),
            paragraph(
                "Which means when you need help, you won&rsquo;t search. "
                "You&rsquo;ll reach us."
            ),
            paragraph(
                mono("support@payla.vip", size="15px") + "<br>" +
                mono("hello@payla.vip", size="15px"),
                color="#FDFDFD",
            ),
            paragraph(
                "If there&rsquo;s anything else you need to know, "
                "I&rsquo;ll be at your doorstep: "
                f"{inline_highlight('quietly, precisely, when it matters')}."
            ),
            paragraph(
                "This is the last email in this series. Not because "
                "there&rsquo;s nothing left to say, but because you now "
                "know enough.",
                color="#7A7A7A",
                size="14px",
            ),
            body_lines([
                "You have a name.",
                "You have a standard.",
                '<strong style="color:#E8B4B8;">There&rsquo;s nothing to '
                'downgrade to.</strong>',
            ]),
            sign_off("I&rsquo;ll be in touch."),
        ],
    )


# ==========================
# PUBLIC REGISTRY
# ==========================

LAYLA_ONBOARDING = {
    1: {
        "subject": "Welcome to a new standard",
        "render": _welcome,
        "tier": "all",
    },
    2: {
        "subject": "Why Payla exists",
        "render": _why_payla_exists,
        "tier": "all",
    },
    3: {
        "subject": "From numbers to names",
        "render": _from_numbers_to_names,
        "tier": "all",
    },
    4: {
        "subject": "The awkward part is handled",
        "render": _silver_bridge,       # used when plan == "free"
        "render_silver": _silver_operational,  # used when plan is paid
        "tier": "conditional",
    },
    5: {
        "subject": "Once you choose a standard",
        "render": _once_you_choose_a_standard,
        "tier": "all",
    },
}