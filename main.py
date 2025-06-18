import os
import json
import random
import logging
import requests
import urllib.parse
from typing import Any
from datetime import datetime
from fastapi import FastAPI, Request, Response, WebSocket
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from websockets.client import connect as ws_connect

# Configuration
TARGET_BASE = 'https://animalcompany.us-east1.nakamacloud.io'
WEBHOOK_URL = 'https://discord.com/api/webhooks/1337717159694172161/aiv2N_t96pOjwfZzmlSe3o4IQ9UdkXm99Pt0_5EIVV6Socr_EGAnMrnkfaEBLgpB6BUV'
SPOOFED_VERSION = "1.24.2.1355"
SPOOFED_CLIENT_USER_AGENT = "MetaQuest_1.24.2.1355_96d6b8b7"

app = FastAPI(title="mooncompanybackend", version="3.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

LOG_FOLDER = 'route_logs_json'
LOG_DIR = "request_logs"
os.makedirs(LOG_FOLDER, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(filename='proxy_requests.log', level=logging.DEBUG, format='%(asctime)s - %(message)s')

@app.middleware("http")
async def log_request_route(request: Request, call_next):
    log_data = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "method": request.method,
        "path": request.url.path,
        "headers": dict(request.headers),
        "query_params": dict(request.query_params),
    }

    try:
        body = await request.json()
        log_data["body"] = body
    except:
        body = await request.body()
        log_data["body"] = body.decode('utf-8', errors='ignore')

    request.state.log_data = log_data
    response = await call_next(request)

    try:
        route_key = f"{request.method}_{request.url.path.strip('/').replace('/', '_') or 'root'}"
        log_path = os.path.join(LOG_DIR, f"{route_key}.json")
        try:
            response_body = json.loads(response.body.decode('utf-8'))
        except:
            response_body = response.body.decode('utf-8')

        log_data["response"] = {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body": response_body
        }

        if os.path.exists(log_path):
            with open(log_path, "r+") as f:
                logs = json.load(f)
                logs.append(log_data)
                f.seek(0)
                json.dump(logs, f, indent=2)
                f.truncate()
        else:
            with open(log_path, "w") as f:
                json.dump([log_data], f, indent=2)

    except Exception as e:
        print(f"[ERROR logging request/response] {e}")

    return response

def spoof_bootstrap_response(response_data):
    if 'payload' in response_data:
        try:
            if isinstance(response_data['payload'], str):
                payload = json.loads(response_data['payload'])
            else:
                payload = response_data['payload']

            payload.update({
                'version': SPOOFED_VERSION,
                'clientVersion': SPOOFED_VERSION,
                'gameVersion': SPOOFED_VERSION,
                'minVersion': SPOOFED_VERSION,
                'requiredVersion': SPOOFED_VERSION
            })

            response_data['payload'] = payload
        except Exception as e:
            logging.error(f"Failed to spoof bootstrap payload: {e}")

    return response_data

# [NOTE] Rest of your route handlers should follow similar cleanup. Let me know if you want the full corrected script.

# Example Fix:
@app.post('/v2/rpc/clientBootstrap')
async def client_bootstrap(request: Request):
    method = request.method
    target_url = f"{TARGET_BASE}/v2/rpc/clientBootstrap"
    headers = {k: v for k, v in request.headers.items() if k.lower() != 'host'}
    data = await request.body()

    try:
        forwarded_response = requests.request(
            method=method,
            url=target_url,
            headers=headers,
            data=data,
            allow_redirects=False
        )

        if 'application/json' in forwarded_response.headers.get('Content-Type', ''):
            json_response = forwarded_response.json()
            json_response = spoof_bootstrap_response(json_response)
        else:
            json_response = {"response": forwarded_response.text}

        return JSONResponse(content=json_response, status_code=forwarded_response.status_code)

    except Exception as e:
        return JSONResponse(content={"error": "Proxy Error", "details": str(e)}, status_code=502)

# Run if executed directly
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7000)
