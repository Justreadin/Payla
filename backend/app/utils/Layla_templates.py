# Luxury Noir Brand Constants
MIDNIGHT = "#0A0A0A"
ROSE = "#E8B4B8"
SOFT_WHITE = "#FDFDFD"

Layla_TEMPLATES = {
    1: {
        "subject": "Welcome to a new standard",
        "html": lambda full_name, username: f"""
              <div style="background:{MIDNIGHT}; color:{SOFT_WHITE}; font-family:'Inter', -apple-system, sans-serif; padding:60px 20px; min-height:100vh;">
                <div style="max-width:460px; margin:0 auto; background:{MIDNIGHT}; border:1px solid rgba(232,180,184,0.25); border-radius:32px; padding:48px; box-shadow:0 40px 100px rgba(0,0,0,0.5);">
                  
                  <h1 style="font-family:'Playfair Display', serif; font-size:32px; font-weight:400; color:{ROSE}; margin-bottom:32px; letter-spacing:-0.5px;">
                    Welcome {full_name.split()[0]}.
                  </h1>

                  <div style="font-size:16px; line-height:1.9; color:#D6D6D6; font-weight:300;">
                    <p style="color:{SOFT_WHITE}; font-size:18px; margin-bottom:24px;">I’m <strong>Layla</strong>.</p>
                    
                    <p>
                      I’ll be guiding you through Payla, from your <strong>payment identity</strong>, to client payments, reminders, invoices, and receipts.
                    </p>
                    
                    <p>
                      Everything required to get paid cleanly, quickly, and without a single follow-up.
                    </p>

                    <p style="margin:32px 0 12px; color:{ROSE}; font-weight:600; letter-spacing:1px; font-size:13px; text-transform:uppercase;">
                      Over the next few weeks, I’ll show you:
                    </p>
                    
                    <ul style="list-style-type:none; padding:0; margin-bottom:32px; color:{SOFT_WHITE};">
                      <li style="margin-bottom:8px;">• What Payla is</li>
                      <li style="margin-bottom:8px;">• What it replaces</li>
                      <li style="margin-bottom:8px;">• How creators get paid without friction</li>
                    </ul>

                    <p style="font-style:italic; border-left:2px solid {ROSE}; padding-left:16px; margin:32px 0;">
                      My emails are short. Intentional. Worth your time. One minute is all I need.
                    </p>

                    <p style="margin-bottom:24px;">
                      Start now.<br/>
                      Share your Payla link with a client.<br/>
                      Add it to your bio.<br/>
                      Let it represent how you get paid.
                    </p>

                    <div style="text-align:center; margin:40px 0;">
                      <a href="https://payla.ng/@{username}" 
                        style="color:{ROSE}; text-decoration:none; font-size:20px; font-weight:700; letter-spacing:-0.5px;">
                        payla.ng/@{username}
                      </a>
                    </div>

                    <p style="color:{SOFT_WHITE}; font-weight:500;">
                      This isn’t a payment link. It’s your payment identity.
                    </p>
                    
                    <p style="margin-top:8px;">
                      Welcome to a new standard.
                    </p>
                  </div>

                  <div style="margin-top:60px; padding-top:32px; border-top:1px solid rgba(232,180,184,0.15);">
                    <p style="margin:0; color:#888888; font-size:15px;">I’ll be in touch.</p>
                    <p style="margin:8px 0 0; color:{ROSE}; font-size:22px; font-family:'Playfair Display', serif;">— Layla</p>
                    <p style="margin:4px 0 0; font-weight:900; letter-spacing:4px; font-size:12px; color:rgba(232,180,184,0.5);">PAYLA</p>
                  </div>

                </div>
              </div>
              """
            },
    2: {
        "subject": "Why Payla exists",
        "html": lambda username: f"""
<div style="background:{MIDNIGHT}; color:{SOFT_WHITE}; font-family:'Inter', -apple-system, sans-serif; padding:60px 20px; min-height:100vh;">
  <div style="max-width:460px; margin:0 auto; background:{MIDNIGHT}; border:1px solid rgba(232,180,184,0.25); border-radius:32px; padding:48px; box-shadow:0 40px 100px rgba(0,0,0,0.5);">
    
    <div style="font-size:16px; line-height:2.2; color:#D6D6D6; font-weight:300;">
      
      <p style="color:{ROSE}; font-weight:600; margin-bottom:32px;">This is the problem.</p>

      <p>You do the work.</p>
      <p>You deliver on time.</p>
      <p style="color:{SOFT_WHITE};"><strong>Then you wait.</strong></p>

      <p style="margin-top:24px;">You send your account number.</p>
      <p>You follow up.</p>
      <p>You wait again.</p>

      <p style="font-style:italic; color:#888888; margin-top:24px;">
        “Seen.”<br/>
        “Will pay.”<br/>
        Tomorrow.
      </p>

      <p style="margin-top:40px; color:{SOFT_WHITE}; font-size:18px; line-height:1.6;">
        Payla exists because this is <span style="color:{ROSE};">unacceptable</span>.
      </p>

      <div style="margin:40px 0; border-left:2px solid {ROSE}; padding-left:20px;">
        <p style="margin:0;">Payla is not a payment app.</p>
        <p style="margin:0;">It does not ask you to chase money.</p>
        <p style="margin:0;">It does not make you explain yourself.</p>
      </div>

      <p style="color:{ROSE}; font-size:20px; font-weight:700; letter-spacing:-0.5px;">
        Payla is your payment identity.
      </p>

      <p style="font-size:18px; color:{SOFT_WHITE}; font-weight:500; margin-top:12px; letter-spacing:0.5px;">
        One name. One link. One standard.
      </p>

      <p style="margin-top:32px;">
        When you share your Payla link, you’re not requesting payment. 
        <strong>You’re setting terms.</strong>
      </p>

      <p>
        No awkward reminders. No “have you paid?” messages. No silence. 
        <span style="color:{ROSE};">Just clarity.</span>
      </p>

      <p style="margin-top:32px;">
        Money should move the same way your work does — 
        <span style="color:{SOFT_WHITE}; font-weight:500;">clean, deliberate, on time.</span>
      </p>

      <p style="margin-top:40px; color:{ROSE}; font-weight:600; letter-spacing:1px; font-size:13px; text-transform:uppercase;">
        What Payla replaces:
      </p>
      <p style="margin:0; color:#888888;">Account numbers. Screenshots. Excuses.</p>

      <p style="margin-top:32px;">
        What Payla introduces is simpler: 
        <strong>A way to get paid that respects your time.</strong>
      </p>

      <p style="margin-top:40px; font-size:14px;">
        This is not for everyone. It’s for people who take their work seriously.
      </p>
      
      <p style="color:{SOFT_WHITE}; margin-bottom:0;">If that’s you, keep going.</p>
    </div>

    <div style="margin-top:60px; padding-top:32px; border-top:1px solid rgba(232,180,184,0.15);">
      <p style="margin:8px 0 0; color:{ROSE}; font-size:22px; font-family:'Playfair Display', serif;">— Layla</p>
      <p style="margin:4px 0 0; font-weight:900; letter-spacing:4px; font-size:12px; color:rgba(232,180,184,0.5);">PAYLA</p>
    </div>

  </div>
</div>
"""
    },
    3: {
        "subject": "From numbers to names",
        "html": lambda username: f"""
<div style="background:{MIDNIGHT}; color:{SOFT_WHITE}; font-family:'Inter', -apple-system, sans-serif; padding:60px 20px; min-height:100vh;">
  <div style="max-width:460px; margin:0 auto; background:{MIDNIGHT}; border:1px solid rgba(232,180,184,0.25); border-radius:32px; padding:48px; box-shadow:0 40px 100px rgba(0,0,0,0.5);">
    
    <div style="font-size:16px; line-height:2.2; color:#D6D6D6; font-weight:300;">
      
      <p style="margin-bottom:32px;">Before Payla, you were a number.</p>

      <div style="color:#888888; margin-bottom:32px;">
        <p style="margin:0;">An account number.</p>
        <p style="margin:0;">A bank name.</p>
        <p style="margin:0;">Something copied. Something pasted.</p>
      </div>

      <p>Easy to forget.</p>
      <p>Easy to delay.</p>
      <p>Easy to ignore.</p>

      <p style="margin-top:40px; color:{SOFT_WHITE}; font-size:18px; line-height:1.6;">
        That’s not how professionals should get paid.
      </p>

      <p style="margin-top:32px;">
        Payla changes this by giving you a <span style="color:{ROSE}; font-weight:600;">name</span>.
      </p>

      <div style="margin:24px 0; border-left:2px solid {ROSE}; padding-left:20px;">
        <p style="margin:0;">Not a username.</p>
        <p style="margin:0;">Not a handle for fun.</p>
        <p style="margin:0; color:{SOFT_WHITE};"><strong>A payment identity.</strong></p>
      </div>

      <p style="color:{ROSE}; font-size:24px; font-weight:700; letter-spacing:-1px; margin:40px 0;">
        @{username}
      </p>

      <p style="color:{SOFT_WHITE}; font-weight:500; margin-bottom:8px;">A single name that represents:</p>
      <p style="margin:0;">How you work.</p>
      <p style="margin:0;">How you charge.</p>
      <p style="margin:0;">How you get paid.</p>

      <p style="margin-top:40px; font-size:18px; color:{SOFT_WHITE};">
        Names carry weight. Numbers don’t.
      </p>

      <p style="margin-top:12px;">
        When a client sees a number, they hesitate.<br/>
        When they see a name, they remember.
      </p>

      <p style="color:{ROSE}; margin-top:32px; font-weight:600;">That’s the difference.</p>

      <p style="margin-top:40px;">
        Your Payla name becomes the <span style="color:{SOFT_WHITE};">point of payment</span>.
      </p>
      <p style="margin:0;">Not a step. Not a request. <strong>A destination.</strong></p>

      <div style="margin-top:32px; color:#888888;">
        <p style="margin:0;">You don’t send details.</p>
        <p style="margin:0;">You don’t explain.</p>
        <p style="margin:0;">You don’t remind.</p>
      </div>

      <p style="margin-top:32px; color:{SOFT_WHITE}; font-weight:500;">You share your name.</p>
      <p>One name. Every client. Every time.</p>

      <p style="margin-top:40px; color:{ROSE}; font-weight:600; letter-spacing:1px; font-size:13px; text-transform:uppercase;">
        This is the identity system.
      </p>

      <p style="margin-top:32px;">
        And once you’re known by a name,<br/>
        going back to being a number feels impossible.
      </p>
    </div>

    <div style="margin-top:60px; padding-top:32px; border-top:1px solid rgba(232,180,184,0.15);">
      <p style="margin:8px 0 0; color:{ROSE}; font-size:22px; font-family:'Playfair Display', serif;">— Layla</p>
      <p style="margin:4px 0 0; font-weight:900; letter-spacing:4px; font-size:12px; color:rgba(232,180,184,0.5);">PAYLA</p>
    </div>

  </div>
</div>
"""
    },
    4: {
        "subject": "The awkward part is handled",
        "html": lambda username: f"""
<div style="background:{MIDNIGHT}; color:{SOFT_WHITE}; font-family:'Inter', -apple-system, sans-serif; padding:60px 20px; min-height:100vh;">
  <div style="max-width:460px; margin:0 auto; background:{MIDNIGHT}; border:1px solid rgba(232,180,184,0.25); border-radius:32px; padding:48px; box-shadow:0 40px 100px rgba(0,0,0,0.5);">
    
    <div style="font-size:16px; line-height:2.2; color:#D6D6D6; font-weight:300;">
      
      <p style="margin-bottom:32px;">Let’s talk about the moment most people avoid.</p>

      <div style="color:#888888; margin-bottom:32px;">
        <p style="margin:0;">The transaction.</p>
        <p style="margin:0;">The follow-ups.</p>
        <p style="margin:0;">The uncomfortable silence after the work is done.</p>
      </div>

      <p style="color:{ROSE}; font-weight:600; font-size:18px; line-height:1.6; margin-bottom:40px;">
        This is where dignity is usually lost.
      </p>

      <p>Payla was designed to handle this part for you.</p>

      <div style="margin:24px 0; color:{SOFT_WHITE}; font-weight:500;">
        <p style="margin:0;">Not loudly.</p>
        <p style="margin:0;">Not aggressively.</p>
        <p style="margin:0;">Not awkwardly.</p>
      </div>

      <p style="font-size:18px; letter-spacing:0.5px; color:{ROSE};">Quietly. Correctly.</p>

      <p style="margin-top:40px;">
        With Payla, you don’t chase payments.
      </p>
      <p>You don’t check your phone.</p>
      <p>You don’t ask if someone has paid.</p>

      <div style="margin:40px 0; border-left:2px solid {ROSE}; padding-left:20px; color:{SOFT_WHITE}; font-weight:500;">
        <p style="margin:0;">Reminders are sent.</p>
        <p style="margin:0;">Overdues are handled.</p>
        <p style="margin:0;">Receipts are issued.</p>
      </div>

      <p style="color:{ROSE}; font-size:20px; font-weight:700;">Automatically.</p>
      <p>On time. Every time.</p>

      <p style="margin-top:40px;">
        Your client isn’t pressured.<br/>
        And you aren’t diminished.
      </p>

      <p style="color:{SOFT_WHITE}; font-style:italic; margin-top:12px;">That balance matters.</p>

      <div style="margin-top:40px; background:rgba(232,180,184,0.05); padding:24px; border-radius:16px; border:1px solid rgba(232,180,184,0.1);">
        <p style="margin:0;">Invoices are clear.</p>
        <p style="margin:0;">Receipts are instant.</p>
        <p style="margin:0; color:{SOFT_WHITE};">Payments go straight to your account.</p>
      </div>

      <div style="margin-top:32px; color:#888888; font-size:15px;">
        <p style="margin:0;">No screenshots.</p>
        <p style="margin:0;">No explanations.</p>
        <p style="margin:0;">No discomfort.</p>
      </div>

      <p style="margin-top:40px; line-height:1.6;">
        Because the best payment systems don’t interrupt the relationship.<br/>
        <span style="color:{SOFT_WHITE}; font-weight:600;">They protect it.</span>
      </p>

      <p style="margin-top:32px;">
        Payla exists so you can stay focused on your work —<br/>
        while the transaction takes care of itself.
      </p>

      <p style="margin-top:40px; color:{ROSE}; font-weight:600; font-size:17px;">
        This is how it should feel to get paid.
      </p>
    </div>

    <div style="margin-top:60px; padding-top:32px; border-top:1px solid rgba(232,180,184,0.15);">
      <p style="margin:8px 0 0; color:{ROSE}; font-size:22px; font-family:'Playfair Display', serif;">— Layla</p>
      <p style="margin:4px 0 0; font-weight:900; letter-spacing:4px; font-size:12px; color:rgba(232,180,184,0.5);">PAYLA</p>
    </div>

  </div>
</div>
"""
    },
    5: {
        "subject": "Once you choose a standard",
        "html": lambda username: f"""
<div style="background:{MIDNIGHT}; color:{SOFT_WHITE}; font-family:'Inter', -apple-system, sans-serif; padding:60px 20px; min-height:100vh;">
  <div style="max-width:460px; margin:0 auto; background:{MIDNIGHT}; border:1px solid rgba(232,180,184,0.25); border-radius:32px; padding:48px; box-shadow:0 40px 100px rgba(0,0,0,0.5);">
    
    <div style="font-size:16px; line-height:2.2; color:#D6D6D6; font-weight:300;">
      
      <p style="margin-bottom:32px;">This is the part most people don’t think about.</p>

      <div style="color:{ROSE}; font-weight:500; margin-bottom:32px;">
        <p style="margin:0;">Standards don’t ask to be renewed.</p>
        <p style="margin:0;">They don’t compete.</p>
        <p style="margin:0;">They don’t downgrade.</p>
      </div>

      <p style="color:{SOFT_WHITE}; font-size:18px; margin-bottom:40px;">
        Once you choose one, you don’t go back.
      </p>

      <p>Your Payla name is permanent. It’s yours.</p>
      <p>It doesn’t expire. It doesn’t change.</p>

      <div style="margin:40px 0; border-left:2px solid {ROSE}; padding-left:20px;">
        <p style="margin:0;">It becomes how clients recognize you.</p>
        <p style="margin:0;">How payments reach you.</p>
        <p style="margin:0; color:{SOFT_WHITE};"><strong>How your work is remembered.</strong></p>
      </div>

      <p style="color:{ROSE}; font-size:18px; font-weight:600; letter-spacing:-0.5px;">That’s the lock-in.</p>
      <p>Not force. Not friction. Familiarity.</p>

      <p style="margin-top:32px;">
        Once people know how to pay you, they don’t need to be reminded.
      </p>
      
      <p style="color:{SOFT_WHITE}; font-style:italic;">
        And once you experience getting paid with clarity, everything else feels like noise.
      </p>

      <p style="margin-top:40px; color:{ROSE}; font-weight:600; letter-spacing:1px; font-size:13px; text-transform:uppercase;">
        You’re not a user here. You’re a VIP.
      </p>
      
      <p style="margin-top:8px;">
        Which means when you need help, you won’t search. You’ll reach us.
      </p>

      <div style="margin:24px 0; color:{SOFT_WHITE}; font-family:monospace; font-size:15px;">
        support@payla.vip<br/>
        hello@payla.vip
      </div>

      <p style="margin-top:32px;">
        If there’s anything else you need to know, I’ll be at your doorstep — 
        <span style="color:{ROSE};">quietly, precisely, when it matters.</span>
      </p>

      <p style="margin-top:40px; line-height:1.6; color:#888888; font-size:14px;">
        This is the last email in this series. Not because there’s nothing left to say — 
        but because you now know enough.
      </p>

      <div style="margin-top:32px; color:{SOFT_WHITE}; font-weight:500;">
        <p style="margin:0;">You have a name.</p>
        <p style="margin:0;">You have a standard.</p>
        <p style="margin:0; color:{ROSE};">There’s nothing to downgrade to.</p>
      </div>
    </div>

    <div style="margin-top:60px; padding-top:32px; border-top:1px solid rgba(232,180,184,0.15);">
      <p style="margin:8px 0 0; color:{ROSE}; font-size:22px; font-family:'Playfair Display', serif;">— Layla</p>
      <p style="margin:4px 0 0; font-weight:900; letter-spacing:4px; font-size:12px; color:rgba(232,180,184,0.5);">PAYLA</p>
    </div>

  </div>
</div>
"""
    }
}