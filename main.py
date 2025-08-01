import traceback
import requests
from filelock import FileLock
from flask import Flask, request, jsonify, Response, send_file
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import json
import logging
import os
import threading
import time
import random
from datetime import datetime

app = Flask(__name__)

session = requests.Session()
retries = Retry(total=10, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
session.mount('https://', HTTPAdapter(max_retries=retries))

TARGET_BASE = 'https://animalcompany.us-east1.nakamacloud.io:443'

file_lock = threading.Lock()

LOG_FOLDER = 'logs'
os.makedirs(LOG_FOLDER, exist_ok=True)

def log_route_data_json(route, method, request_body, response_body, status_code, headers):
    safe_route = route.replace('/', '_').strip('_')
    filename = os.path.join(LOG_FOLDER, f"{safe_route}.json")

    log_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "method": method,
        "route": f"/{route}",
        "headers": json.dumps(headers, indent=4),
        "request_body": request_body,
        "response_body": response_body,
        "status_code": status_code
    }

    with open(filename, 'a', encoding='utf-8') as f:
        f.write(json.dumps(log_entry, indent=4) + ",\n")


@app.route('/', defaults={'path': ''}, methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
@app.route('/<path:path>', methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
def catch_all(path):
    forward_url = f"{TARGET_BASE}/{path}"
    method = request.method
    headers = dict(request.headers)
    data = request.get_data()
    params = request.args
    headers.pop('Host', None)

    try:
        if path == "v2/account/authenticate/custom":
            b = json.loads(data.decode('utf-8', errors='replace'))
            if isinstance(b, dict) and 'vars' in b and isinstance(b['vars'], dict):
                b['vars']['clientUserAgent'] = "MetaQuest 1.32.0.1514_abc54958"
            resp = session.request(method, forward_url, headers=headers, data=json.dumps(b), params=params)
        else:
            resp = session.request(method, forward_url, headers=headers, data=data, params=params)

        decoded_data = data.decode('utf-8', errors='replace')

        if 'application/json' in resp.headers.get('Content-Type', ''):
            log_route_data_json(path, method, decoded_data, resp.json(), resp.status_code, headers)
            return jsonify(resp.json()), resp.status_code

        decoded_content = resp.content.decode('utf-8', errors='replace')
        log_route_data_json(path, method, decoded_data, decoded_content, resp.status_code, headers)
        return Response(resp.content, status=resp.status_code, headers=dict(resp.headers))

    except Exception as e:
        print(f"Error occurred: {e}")
        return "Internal Server Error", 500
if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=6957)
