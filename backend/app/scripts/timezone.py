#!/usr/bin/env python3
"""
Quick verification that reminder times are correct
Run after scheduling a reminder to check the database
"""

from datetime import datetime, timezone
from firebase import db

def verify_reminders():
    print("\n" + "="*70)
    print("🔍 VERIFYING REMINDER TIMES IN DATABASE")
    print("="*70 + "\n")
    
    # Get the most recent 5 pending reminders
    reminders = list(
        db.collection("reminders")
        .where("status", "==", "pending")
        .where("active", "==", True)
        .order_by("next_send")
        .limit(5)
        .stream()
    )
    
    if not reminders:
        print("❌ No pending reminders found in database")
        print("   Create an invoice to test reminder scheduling\n")
        return
    
    print(f"Found {len(reminders)} pending reminders:\n")
    
    for i, doc in enumerate(reminders, 1):
        data = doc.to_dict()
        next_send = data.get("next_send")
        
        if next_send:
            # Convert to UTC if needed
            if not hasattr(next_send, 'tzinfo') or next_send.tzinfo is None:
                next_send = next_send.replace(tzinfo=timezone.utc)
            
            # Calculate WAT time (UTC + 1)
            wat_hour = (next_send.hour + 1) % 24
            
            utc_str = next_send.strftime('%Y-%m-%d %H:%M UTC')
            wat_str = f"{next_send.strftime('%Y-%m-%d')} {wat_hour:02d}:{next_send.minute:02d} WAT"
            
            # Check if it's at 9 AM UTC (10 AM WAT)
            is_correct = next_send.hour == 9 and next_send.minute == 0
            status = "✅" if is_correct else "❌"
            
            print(f"{i}. {status} {doc.id}")
            print(f"   Invoice: {data.get('invoice_id')}")
            print(f"   UTC Time: {utc_str}")
            print(f"   WAT Time: {wat_str}")
            print(f"   Channels: {data.get('channels_selected')}")
            
            if not is_correct:
                print(f"   ⚠️  WARNING: Expected 09:00 UTC (10:00 WAT), got {next_send.hour:02d}:{next_send.minute:02d} UTC")
            
            print()
    
    print("="*70)
    print("✅ All reminders should show 09:00 UTC (10:00 WAT)")
    print("="*70 + "\n")


def check_quiet_hours():
    print("\n" + "="*70)
    print("🌙 CHECKING QUIET HOURS CONFIGURATION")
    print("="*70 + "\n")
    
    from app.core.reminder_config import get_quiet_hours_utc
    
    quiet_start_utc, quiet_end_utc = get_quiet_hours_utc("WAT")
    
    print(f"Quiet Hours (UTC): {quiet_start_utc}:00 - {quiet_end_utc}:00")
    print(f"Quiet Hours (WAT): {(quiet_start_utc + 1) % 24}:00 - {(quiet_end_utc + 1) % 24}:00")
    print(f"Expected: 22:00 - 07:00 WAT (21:00 - 06:00 UTC)")
    
    is_correct = quiet_start_utc == 21 and quiet_end_utc == 6
    
    if is_correct:
        print("\n✅ Quiet hours configuration is CORRECT")
    else:
        print(f"\n❌ Quiet hours configuration is WRONG")
        print(f"   Expected: start=21, end=6")
        print(f"   Got: start={quiet_start_utc}, end={quiet_end_utc}")
    
    print()


if __name__ == "__main__":
    verify_reminders()
    check_quiet_hours()
    
    print("\n💡 Tips:")
    print("   • Reminders should be scheduled for 09:00 UTC (10:00 AM WAT)")
    print("   • Quiet hours: 21:00-06:00 UTC (10:00 PM - 7:00 AM WAT)")
    print("   • Check logs for: '🕐 Reminders will be delivered at 10:00 AM WAT'")
    print()