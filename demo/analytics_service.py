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
stats = {
    "total_orders": 0,
    "total_quantity": 0,
    "processed_from_queue": 0,
    "products": {},
    "last_order_at": None,
}


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

    async def on_order_topic(frame):
        data = json.loads(frame.body.decode())
        stats["total_orders"] += 1
        stats["total_quantity"] += data.get("quantity", 0)
        product = data.get("product", "unknown")
        stats["products"][product] = stats["products"].get(product, 0) + data.get("quantity", 0)
        stats["last_order_at"] = time.time()

    async def on_order_queue(frame):
        msg_id = frame.headers.get("message-id")
        stats["processed_from_queue"] += 1
        await client.ack(msg_id)

    await client.subscribe("/topic/orders", on_order_topic)
    await client.subscribe("/queue/order-processing", on_order_queue, ack_mode="client")
    yield
    await client.close()


app = FastAPI(lifespan=lifespan)


@app.get("/api/stats")
async def get_stats():
    return stats


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML


HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Analytics Service</title>
<style>
:root{--bg:#0f172a;--surface:#1e293b;--border:#334155;--text:#e2e8f0;--muted:#94a3b8;--accent:#3b82f6;--green:#22c55e;--orange:#f97316}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:system-ui,sans-serif;background:var(--bg);color:var(--text);padding:2rem;min-height:100vh}
.nav{display:flex;gap:1rem;margin-bottom:1.5rem;font-size:.8rem}
.nav a{color:var(--accent);text-decoration:none}.nav a:hover{text-decoration:underline}.nav span{color:var(--muted)}
h1{font-size:1.5rem;margin-bottom:1.5rem}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:1rem;margin-bottom:1.5rem}
.card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:1.25rem}
.card .label{font-size:.75rem;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin-bottom:.5rem}
.card .value{font-size:1.75rem;font-weight:700}
.card.blue .value{color:var(--accent)}
.card.green .value{color:var(--green)}
.card.orange .value{color:var(--orange)}
.section{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:1.5rem}
.section-title{font-size:.875rem;font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin-bottom:1rem}
table{width:100%;border-collapse:collapse;font-size:.875rem}
th{text-align:left;padding:.5rem .75rem;color:var(--muted);font-weight:500;border-bottom:1px solid var(--border)}
td{padding:.5rem .75rem;border-bottom:1px solid var(--border)}
tr:last-child td{border-bottom:none}
.empty{color:var(--muted);font-style:italic;text-align:center;padding:1rem}
.bar{height:8px;background:var(--accent);border-radius:4px;margin-top:.25rem}
</style>
</head>
<body>
<nav class="nav">
<a href="" id="nav-dash">Dashboard :8080</a>
<a href="" id="nav-orders">Orders :8001</a>
<a href="" id="nav-notif">Notifications :8002</a>
<span>Analytics :8003</span>
</nav>
<h1>Analytics Service</h1>
<div class="cards">
<div class="card blue"><div class="label">Total Orders</div><div class="value" id="total-orders">0</div></div>
<div class="card green"><div class="label">Total Items</div><div class="value" id="total-qty">0</div></div>
<div class="card orange"><div class="label">Queue Processed</div><div class="value" id="processed">0</div></div>
</div>
<div class="section">
<div class="section-title">Products Breakdown</div>
<div id="products-body"><div class="empty">No data yet</div></div>
</div>
<script>
const host=window.location.hostname;
document.getElementById('nav-dash').href=`http://${host}:8080`;
document.getElementById('nav-orders').href=`http://${host}:8001`;
document.getElementById('nav-notif').href=`http://${host}:8002`;
async function load(){
try{
const res=await fetch('/api/stats');const data=await res.json();
document.getElementById('total-orders').textContent=data.total_orders;
document.getElementById('total-qty').textContent=data.total_quantity;
document.getElementById('processed').textContent=data.processed_from_queue;
const products=data.products;
const entries=Object.entries(products);
if(!entries.length){document.getElementById('products-body').innerHTML='<div class="empty">No data yet</div>';return}
const max=Math.max(...entries.map(e=>e[1]));
let html='<table><thead><tr><th>Product</th><th>Quantity</th><th></th></tr></thead><tbody>';
for(const[name,qty]of entries.sort((a,b)=>b[1]-a[1])){
const pct=Math.round(qty/max*100);
html+=`<tr><td>${name}</td><td>${qty}</td><td style="width:40%"><div class="bar" style="width:${pct}%"></div></td></tr>`}
html+='</tbody></table>';document.getElementById('products-body').innerHTML=html}catch(e){}}
load();setInterval(load,2000);
</script>
</body>
</html>"""
