import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import os

load_dotenv()

# --- הגדרות סביבה ---
AIRTABLE_TOKEN = os.getenv('AIRTABLE_SLP2_ACCESS_TOKEN', '')
BASE_ID = os.getenv('AIRTABLE_SLP2_BASE_ID', '')
TABLE_ID = "Calls"
WEBHOOK_URL = "https://hook.eu1.make.com/t50dvule2tjxaqpnaowsdpm7qz6h3elw"


def check_sla_and_alert():
    # 1. חישוב הזמן שלפני 15 דקות בדיוק (בזמן עולמי - UTC)
    time_threshold = datetime.now(timezone.utc) - timedelta(minutes=10)

    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_ID}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_TOKEN}",
        "Content-Type": "application/json"
    }

    # 2. שליפת הנתונים מהשרת
    from urllib.parse import quote

    formula = "{status}='קריאה חדשה'"
    params = {
        "filterByFormula": formula
    }

    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        records = response.json().get('records', [])
    except Exception as e:
        print(f"Error fetching data from Airtable: {e}")
        return

    # 3. מעבר על הרשומות הרלוונטיות ובדיקת הזמנים
    for record in records:
        fields = record.get('fields', {})
        record_id = record.get('id')

        # שליפת תאריך היצירה
        created_at_str = fields.get('create_date')
        if not created_at_str:
            continue

        # המרת התאריך מ-Airtable לאובייקט datetime של פייתון
        created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))

        # 4. אם עברו 15 דקות או יותר
        if created_at <= time_threshold:
            print(f"SLA breached for record {record_id}. Sending to Make...")

            # שליפת השדות הנוספים שביקשת מתוך ה-fields של הרשומה
            call_num = fields.get('call_num')
            slp_name = fields.get('slp_name')
            slp_issue = fields.get('slp_issue')

            # בניית ה-payload המורחב עבור ה-Webhook
            payload = {
                "record_id": record_id,
                "create_date": created_at_str,
                "call_num": call_num,
                "slp_name": slp_name,
                "slp_issue": slp_issue
            }

            # א. שליחת ה-Webhook
            try:
                make_response = requests.post(WEBHOOK_URL, json=payload)
                make_response.raise_for_status()
            except Exception as e:
                print(f"Failed to send webhook for {record_id}: {e}")
                continue

            # ב. עדכון הרשומה ← צריך להיות בחוץ, לא בתוך ה-except
            update_url = f"{url}/{record_id}"
            update_data = {
                "fields": {
                    "status": "קריאה חדשה - באיחור טיפול"
                }
            }
            try:
                patch_res = requests.patch(update_url, headers=headers, json=update_data)
                print(f"Update response: {patch_res.status_code} | {patch_res.text}")
            except Exception as e:
                print(f"Failed to update Airtable for {record_id}: {e}")


if __name__ == "__main__":
    check_sla_and_alert()