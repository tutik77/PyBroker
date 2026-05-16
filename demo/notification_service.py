import asyncio
import json
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from pybroker.client.client import BrokerClient

BROKER_HOST = os.environ.get("BROKER_HOST", "localhost")
BROKER_PORT = int(os.environ.get("BROKER_PORT", "9090"))

client: BrokerClient | None = None
notifications: list[dict] = []


async def connect_with_retry(c: BrokerClient, retries: int = 30):
    for attempt in range(retries):
        try:
            await c.connect()
            return
        except Exception:
            if attempt < retries - 1:
                await asyncio.sleep(2)
    raise ConnectionError("Failed to connect to broker")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global client
    client = BrokerClient(BROKER_HOST, BROKER_PORT)
    await connect_with_retry(client)

    async def on_order(frame):
        data = json.loads(frame.body.decode())
        notifications.append({
            "timestamp": time.time(),
            "type": "new_order",
            "order_id": data.get("id"),
            "product": data.get("product"),
            "quantity": data.get("quantity"),
        })

    await client.subscribe("/topic/orders", on_order)
    yield
    await client.close()


app = FastAPI(lifespan=lifespan)


@app.get("/api/notifications")
async def get_notifications():
    return {"notifications": notifications[-100:]}


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML


HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Notification Service</title>
<style>
:root{--bg:#0f172a;--surface:#1e293b;--border:#334155;--text:#e2e8f0;--muted:#94a3b8;--accent:#3b82f6;--green:#22c55e}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:system-ui,sans-serif;background:var(--bg);color:var(--text);padding:2rem;min-height:100vh}
.nav{display:flex;gap:1rem;margin-bottom:1.5rem;font-size:.8rem}
.nav a{color:var(--accent);text-decoration:none}.nav a:hover{text-decoration:underline}.nav span{color:var(--muted)}
h1{font-size:1.5rem;margin-bottom:1.5rem}
.counter{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:1.25rem;margin-bottom:1.5rem;display:flex;align-items:center;gap:1rem}
.counter .num{font-size:2rem;font-weight:700;color:var(--accent)}
.counter .lbl{font-size:.875rem;color:var(--muted)}
.section{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:1.5rem}
.section-title{font-size:.875rem;font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin-bottom:1rem}
table{width:100%;border-collapse:collapse;font-size:.875rem}
th{text-align:left;padding:.5rem .75rem;color:var(--muted);font-weight:500;border-bottom:1px solid var(--border)}
td{padding:.5rem .75rem;border-bottom:1px solid var(--border)}
tr:last-child td{border-bottom:none}
.empty{color:var(--muted);font-style:italic;text-align:center;padding:1rem}
.badge{display:inline-block;padding:.125rem .5rem;border-radius:4px;font-size:.7rem;background:#1e3a5f;color:#60a5fa}
</style>
</head>
<body>
<nav class="nav">
<a href="" id="nav-dash">Dashboard :8080</a>
<a href="" id="nav-orders">Orders :8001</a>
<span>Notifications :8002</span>
<a href="" id="nav-analytics">Analytics :8003</a>
</nav>
<h1>Notification Service</h1>
<div class="counter"><div class="num" id="count">0</div><div class="lbl">notifications received<br><small>via /topic/orders (pub/sub)</small></div></div>
<div class="section">
<div class="section-title">Recent Notifications</div>
<div id="notif-body"><div class="empty">Waiting for events...</div></div>
</div>
<script>
const host=window.location.hostname;
document.getElementById('nav-dash').href=`http://${host}:8080`;
document.getElementById('nav-orders').href=`http://${host}:8001`;
document.getElementById('nav-analytics').href=`http://${host}:8003`;
async function load(){
try{
const res=await fetch('/api/notifications');const data=await res.json();
const items=data.notifications;
document.getElementById('count').textContent=items.length;
if(!items.length){document.getElementById('notif-body').innerHTML='<div class="empty">Waiting for events...</div>';return}
let html='<table><thead><tr><th>Time</th><th>Type</th><th>Order</th><th>Product</th><th>Qty</th></tr></thead><tbody>';
for(const n of items.slice().reverse().slice(0,50)){
const t=new Date(n.timestamp*1000).toLocaleTimeString();
html+=`<tr><td>${t}</td><td><span class="badge">${n.type}</span></td><td>${n.order_id}</td><td>${n.product}</td><td>${n.quantity}</td></tr>`}
html+='</tbody></table>';document.getElementById('notif-body').innerHTML=html}catch(e){}}
load();setInterval(load,2000);
</script>
</body>
</html>"""
