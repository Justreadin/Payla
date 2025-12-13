import asyncio
from app.services.channels import send_via_whatsapp

asyncio.run(
    send_via_whatsapp("+2349041385402", "WhatsApp API test from Payla 🚀")
)
