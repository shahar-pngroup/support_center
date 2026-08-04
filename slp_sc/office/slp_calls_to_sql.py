import requests
from Connections.ConnectToSql import connect_to_db
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

AIRTABLE_API_KEY: str = os.getenv('AIRTABLE_SLP2_ACCESS_TOKEN')
AIRTABLE_BASE_ID: str = os.getenv('AIRTABLE_SLP2_BASE_ID')
AIRTABLE_TABLE_NAME = "Calls"

AIRTABLE_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_NAME}"


def parse_date(val):
    if not val:
        return None
    try:
        # 1. הופך את המחרוזת מ-Airtable לאובייקט תאריך (UTC)
        dt_utc = datetime.fromisoformat(val.replace('Z', '+00:00'))

        # 2. מוסיף 3 שעות כדי להתאים לזמן ישראל (UTC+3)
        dt_local = dt_utc + timedelta(hours=3)

        # 3. מחזיר מחרוזת מעוצבת שמתאימה ל-SQL Server
        return dt_local.strftime('%Y-%m-%d %H:%M:%S')
    except Exception as e:
        print(f"Error parsing date {val}: {e}")
        return None


def get_airtable_data():
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }

    all_records = []
    offset = None

    print("Fetching data from Airtable...")

    while True:
        url = AIRTABLE_URL
        if offset:
            url += f"?offset={offset}"

        response = requests.get(url, headers=headers)

        if response.status_code != 200:
            print(f"Error fetching from Airtable: {response.status_code}")
            print(response.text)
            return None

        data = response.json()
        records = data.get('records', [])
        all_records.extend(records)
        print(f"Fetched {len(records)} records...")

        offset = data.get('offset')
        if not offset:
            break

    print(f"Total records fetched: {len(all_records)}\n")
    return all_records


def sync_to_sql(airtable_records):
    if not airtable_records:
        print("No records to sync")
        return

    conn = connect_to_db()
    cursor = conn.cursor()

    try:
        synced_count = 0
        updated_count = 0
        inserted_count = 0

        for record in airtable_records:
            fields = record.get('fields', {})

            call_num = fields.get('call_num')
            create_date = parse_date(fields.get('create_date'))
            fatch_date = parse_date(fields.get('fatch_date'))
            close_date = parse_date(fields.get('close_date'))
            slp_name = fields.get('slp_name')
            status = fields.get('status')
            attachment = fields.get('attachment')
            supporter = fields.get('supporter')
            slp_issue = fields.get('slp_issue')
            subject = fields.get('subject')

            print(f"Processing: call_num={call_num}, slp_name={slp_name}, status={status}")

            check_query = "SELECT call_num FROM png_slp_calls WHERE call_num = ?"
            cursor.execute(check_query, (call_num,))
            existing = cursor.fetchone()

            if existing:
                update_query = """
                               UPDATE png_slp_calls
                               SET create_date = ?,
                                   fatch_date  = ?,
                                   close_date  = ?,
                                   slp_name    = ?,
                                   status      = ?,
                                   attachment  = ?,
                                   supporter   = ?,
                                   slp_issue   = ?,
                                   subject     = ?
                               WHERE call_num = ? \
                               """
                cursor.execute(update_query, (
                    create_date, fatch_date, close_date,
                    slp_name, status, attachment,
                    supporter, slp_issue, subject,
                    call_num
                ))
                updated_count += 1
                print(f"   Updated call_num={call_num}")
            else:
                insert_query = """
                               INSERT INTO png_slp_calls (call_num, create_date, fatch_date, close_date, \
                                                          slp_name, status, attachment, \
                                                          supporter, slp_issue, subject)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) \
                               """
                cursor.execute(insert_query, (
                    call_num, create_date, fatch_date, close_date,
                    slp_name, status, attachment,
                    supporter, slp_issue, subject
                ))
                inserted_count += 1
                print(f"   Inserted call_num={call_num}")

            synced_count += 1

        conn.commit()

        print(f"\n{'=' * 60}")
        print(f"Sync completed successfully!")
        print(f"Total records processed: {synced_count}")
        print(f"New records inserted:    {inserted_count}")
        print(f"Existing records updated:{updated_count}")
        print(f"{'=' * 60}")

    except Exception as e:
        print(f"Error syncing to SQL: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


def main():
    print(f"Starting Airtable to SQL sync - {datetime.now()}")
    print(f"{'=' * 60}\n")

    airtable_records = get_airtable_data()

    if airtable_records:
        sync_to_sql(airtable_records)
    else:
        print("No data retrieved from Airtable")

    print(f"\nSync process completed - {datetime.now()}")


if __name__ == "__main__":
    main()