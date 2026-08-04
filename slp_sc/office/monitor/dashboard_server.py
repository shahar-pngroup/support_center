import os
import requests
from flask import Flask, jsonify, render_template, send_file
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta

load_dotenv(r'D:\PythonProjects\.env')

app = Flask(__name__, template_folder='templates')

AIRTABLE_TOKEN   = os.getenv('AIRTABLE_SLP2_ACCESS_TOKEN', '')
AIRTABLE_BASE_ID = os.getenv('AIRTABLE_SLP2_BASE_ID', '')
CALLS_TBL        = 'Calls'
AT_HEADERS       = {'Authorization': f'Bearer {AIRTABLE_TOKEN}'}

@app.route('/favicon.svg')
def favicon():
    return send_file(r'D:\PythonProjects\images\general\favicon.svg', mimetype='image/svg+xml')

def at_get(table, params=None):
    records, offset = [], None
    while True:
        p = dict(params or {})
        if offset:
            p['offset'] = offset
        res = requests.get(
            f'https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{table}',
            headers=AT_HEADERS, params=p
        ).json()
        records.extend(res.get('records', []))
        offset = res.get('offset')
        if not offset:
            break
    return records


def parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace('Z', '+00:00'))
    except:
        return None


def fmt_min(minutes):
    if minutes is None:
        return '-'
    h = int(minutes) // 60
    m = int(minutes) % 60
    return f'{h}:{str(m).zfill(2)}'


@app.route('/')
def index():
    return render_template('dashboard.html')


@app.route('/api/dashboard')
def dashboard_data():
    today_str = datetime.now().strftime('%Y-%m-%d')
    formula   = f"IS_SAME({{create_date}}, '{today_str}', 'day')"
    records   = at_get(CALLS_TBL, {'filterByFormula': formula})

    now     = datetime.now(timezone.utc)

    total            = len(records)
    open_count       = 0
    done_count       = 0
    sla_breach       = 0
    by_supporter     = {}
    by_slp           = {}
    new_calls_list   = []
    inprogress_list  = []
    new_alert_list   = []
    response_times   = []
    close_times      = []

    for r in records:
        f            = r.get('fields', {})
        status       = f.get('status', '')
        supporter    = f.get('supporter', '')
        slp_name     = f.get('slp_name', '')
        created_str  = f.get('create_date', '')
        start_str    = f.get('start_date', '')
        fatch_str    = f.get('fatch_date', '')
        close_str    = f.get('close_date', '')
        resp_dur     = f.get('response-duration')
        close_dur    = f.get('close-duration')
        call_num     = f.get('call_num', '')
        slp_issue    = f.get('slp_issue', '')

        is_closed = (status == 'קריאה סגורה')

        if is_closed:
            done_count += 1
        else:
            open_count += 1

        if supporter:
            by_supporter[supporter] = by_supporter.get(supporter, 0) + 1
        if slp_name:
            by_slp[slp_name] = by_slp.get(slp_name, 0) + 1

        # SLA
        sla_hit = False
        if status == 'קריאה חדשה' and start_str:
            try:
                start_dt = parse_dt(start_str)
                if now - start_dt > timedelta(minutes=10):
                    sla_hit = True
            except:
                pass
        if fatch_str and start_str:
            try:
                fatch_dt = parse_dt(fatch_str)
                start_dt = parse_dt(start_str)
                if fatch_dt - start_dt > timedelta(minutes=10):
                    sla_hit = True
            except:
                pass
        if sla_hit:
            sla_breach += 1

        # זמני תגובה וטיפול
        if resp_dur is not None:
            try:
                response_times.append(float(resp_dur))
            except:
                pass
        if close_dur is not None:
            try:
                close_times.append(float(close_dur))
            except:
                pass

        row = {
            'call_num' : call_num,
            'slp_name' : slp_name,
            'slp_issue': slp_issue,
            'status'   : status,
            'created'  : created_str
        }

        if status == 'קריאה חדשה':
            new_calls_list.append(row)
        elif not is_closed:
            inprogress_list.append(row)

        if status == 'קריאה חדשה' and created_str:
            try:
                created = parse_dt(created_str)
                if (now - created).total_seconds() <= 35:
                    new_alert_list.append({'call_num': call_num, 'slp_name': slp_name})
            except:
                pass

    new_calls_list.sort(key=lambda x: x.get('created', ''), reverse=True)
    inprogress_list.sort(key=lambda x: x.get('created', ''), reverse=True)

    avg_response = fmt_min(sum(response_times)/len(response_times)) if response_times else '-'
    avg_close    = fmt_min(sum(close_times)/len(close_times))       if close_times    else '-'

    return jsonify({
        'total'          : total,
        'open'           : open_count,
        'done'           : done_count,
        'sla_breach'     : sla_breach,
        'by_supporter'   : by_supporter,
        'by_slp'         : by_slp,
        'new_calls_list' : new_calls_list,
        'inprogress_list': inprogress_list,
        'new_calls'      : new_alert_list,
        'avg_response'   : avg_response,
        'avg_close'      : avg_close
    })


if __name__ == '__main__':
    print('Dashboard running -> http://PEERNESHER-SAP3:5052')
    app.run(host='0.0.0.0', port=5052, debug=False)
