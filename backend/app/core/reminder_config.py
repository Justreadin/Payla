# app/core/reminder_config.py
"""
Reminder delivery time configuration
Handles timezone conversion for different regions
"""

from datetime import datetime, timezone
from typing import Dict

# Timezone configurations for different regions
TIMEZONE_CONFIGS: Dict[str, Dict[str, any]] = {
    "WAT": {  # West Africa Time (Nigeria, Ghana, etc.)
        "utc_offset": 1,
        "delivery_hour_local": 10,  # 10 AM local time
        "delivery_hour_utc": 9,      # 9 AM UTC = 10 AM WAT
        "quiet_start_local": 22,     # 10 PM local
        "quiet_end_local": 7,        # 7 AM local
    },
    "EAT": {  # East Africa Time (Kenya, Uganda, etc.)
        "utc_offset": 3,
        "delivery_hour_local": 10,
        "delivery_hour_utc": 7,      # 7 AM UTC = 10 AM EAT
        "quiet_start_local": 22,
        "quiet_end_local": 7,
    },
    "GMT": {  # Ghana, UK
        "utc_offset": 0,
        "delivery_hour_local": 10,
        "delivery_hour_utc": 10,     # 10 AM UTC = 10 AM GMT
        "quiet_start_local": 22,
        "quiet_end_local": 7,
    },
}

# Default timezone for Nigeria
DEFAULT_TIMEZONE = "WAT"


def get_delivery_hour_utc(timezone_code: str = DEFAULT_TIMEZONE) -> int:
    """
    Get the UTC hour when reminders should be delivered
    for a given timezone.
    
    Args:
        timezone_code: The timezone code (e.g., "WAT", "EAT")
        
    Returns:
        int: The UTC hour (0-23)
    """
    config = TIMEZONE_CONFIGS.get(timezone_code, TIMEZONE_CONFIGS[DEFAULT_TIMEZONE])
    return config["delivery_hour_utc"]


def get_quiet_hours_utc(timezone_code: str = DEFAULT_TIMEZONE) -> tuple:
    """
    Get the quiet hours in UTC for a given timezone.
    
    Args:
        timezone_code: The timezone code (e.g., "WAT", "EAT")
        
    Returns:
        tuple: (start_hour_utc, end_hour_utc)
    """
    config = TIMEZONE_CONFIGS.get(timezone_code, TIMEZONE_CONFIGS[DEFAULT_TIMEZONE])
    
    # Convert local quiet hours to UTC
    utc_offset = config["utc_offset"]
    start_local = config["quiet_start_local"]
    end_local = config["quiet_end_local"]
    
    # Convert to UTC (subtract offset)
    start_utc = (start_local - utc_offset) % 24
    end_utc = (end_local - utc_offset) % 24
    
    return (start_utc, end_utc)


def format_time_for_timezone(dt: datetime, timezone_code: str = DEFAULT_TIMEZONE) -> str:
    """
    Format a UTC datetime for display in a specific timezone.
    
    Args:
        dt: UTC datetime
        timezone_code: The timezone code
        
    Returns:
        str: Formatted time string (e.g., "10:00 AM WAT")
    """
    config = TIMEZONE_CONFIGS.get(timezone_code, TIMEZONE_CONFIGS[DEFAULT_TIMEZONE])
    utc_offset = config["utc_offset"]
    
    # Add offset to get local time
    local_hour = (dt.hour + utc_offset) % 24
    local_dt = dt.replace(hour=local_hour)
    
    return local_dt.strftime(f"%I:%M %p {timezone_code}")
