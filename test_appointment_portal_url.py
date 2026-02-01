"""Test script to verify appointment portal URL configuration"""
from app.config import settings
from app.routes.dynamic_forms import unified_appointment_portal

print("="*60)
print("CONFIGURATION CHECK")
print("="*60)
print(f"PUBLIC_API_BASE_URL from settings: {settings.PUBLIC_API_BASE_URL}")
print(f"Type: {type(settings.PUBLIC_API_BASE_URL)}")
print()

# Test the appointment portal function
bot_id = "test-bot"
org_id = "test-org"

html = unified_appointment_portal(bot_id, org_id)

# Extract the API_BASE value from the HTML
import re
api_base_match = re.search(r"const API_BASE = '([^']+)'", html)
if api_base_match:
    api_base_value = api_base_match.group(1)
    print(f"API_BASE in generated HTML: {api_base_value}")
else:
    print("Could not find API_BASE in HTML")

# Also check the booking and reschedule URLs
booking_match = re.search(r'href="([^"]+)"[^>]*>[\s\S]*?Open Booking Form', html)
if booking_match:
    booking_url = booking_match.group(1)
    print(f"Booking URL: {booking_url}")

reschedule_match = re.search(r'href="([^"]+)"[^>]*>[\s\S]*?Open Reschedule Form', html)
if reschedule_match:
    reschedule_url = reschedule_match.group(1)
    print(f"Reschedule URL: {reschedule_url}")

print("="*60)
