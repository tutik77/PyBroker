import asyncio
import json
import os
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from pybroker.client.client import BrokerClient

BROKER_HOST = os.environ.get("BROKER_HOST", "localhost")
BROKER_PORT = int(os.environ.get("BROKER_PORT", "9090"))

client: BrokerClient | None = None
orders: list[dict] = []


class OrderRequest(BaseModel):
    product: str
    quantity: int


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
    yield
    await client.close()


app = FastAPI(lifespan=lifespan)


@app.post("/api/orders")
async def create_order(order: OrderRequest):
    order_data = {
        "id": str(uuid.uuid4())[:8],
        "product": order.product,
        "quantity": order.quantity,
        "timestamp": time.time(),
    }
    orders.append(order_data)
    body = json.dumps(order_data)
    await client.publish("/topic/orders", body)
    await client.publish("/queue/order-processing", body)
    return {"status": "ok", "order": order_data}


@app.get("/api/orders")
async def get_orders():
    return {"orders": orders[-50:]}


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML


HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Order Service</title>
<style>
:root{--bg:#0f172a;--surface:#1e293b;--border:#334155;--text:#e2e8f0;--muted:#94a3b8;--accent:#3b82f6;--green:#22c55e}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:system-ui,sans-serif;background:var(--bg);color:var(--text);padding:2rem;min-height:100vh}
.nav{display:flex;gap:1rem;margin-bottom:1.5rem;font-size:.8rem}
.nav a{color:var(--accent);text-decoration:none}.nav a:hover{text-decoration:underline}.nav span{color:var(--muted)}
h1{font-size:1.5rem;margin-bottom:1.5rem}
.form{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:1.5rem;margin-bottom:1.5rem;display:flex;gap:1rem;align-items:end;flex-wrap:wrap}
.field{display:flex;flex-direction:column;gap:.25rem}
.field label{font-size:.75rem;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}
.field select,.field input{background:var(--bg);border:1px solid var(--border);color:var(--text);padding:.5rem .75rem;border-radius:6px;font-size:.875rem}
button{background:var(--accent);color:#fff;border:none;padding:.5rem 1.25rem;border-radius:6px;cursor:pointer;font-size:.875rem;font-weight:500}
button:hover{opacity:.9}
.section{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:1.5rem}
.section-title{font-size:.875rem;font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin-bottom:1rem}
table{width:100%;border-collapse:collapse;font-size:.875rem}
th{text-align:left;padding:.5rem .75rem;color:var(--muted);font-weight:500;border-bottom:1px solid var(--border)}
td{padding:.5rem .75rem;border-bottom:1px solid var(--border)}
tr:last-child td{border-bottom:none}
.empty{color:var(--muted);font-style:italic;text-align:center;padding:1rem}
.toast{position:fixed;top:1rem;right:1rem;background:var(--green);color:#fff;padding:.75rem 1.25rem;border-radius:8px;font-size:.875rem;opacity:0;transition:opacity .3s}
.toast.show{opacity:1}
</style>
</head>
<body>
<nav class="nav">
<a href="" id="nav-dash">Dashboard :8080</a>
<span>Orders :8001</span>
<a href="" id="nav-notif">Notifications :8002</a>
<a href="" id="nav-analytics">Analytics :8003</a>
</nav>
<h1>Order Service</h1>
<div class="form">
<div class="field"><label>Product</label><select id="product"><option>Laptop</option><option>Phone</option><option>Tablet</option><option>Headphones</option><option>Monitor</option></select></div>
<div class="field"><label>Quantity</label><input type="number" id="quantity" value="1" min="1" max="100"></div>
<button onclick="createOrder()">Create Order</button>
</div>
<div class="section">
<div class="section-title">Orders</div>
<div id="orders-body"><div class="empty">No orders yet</div></div>
</div>
<div class="toast" id="toast"></div>
<script>
const host=window.location.hostname;
document.getElementById('nav-dash').href=`http://${host}:8080`;
document.getElementById('nav-notif').href=`http://${host}:8002`;
document.getElementById('nav-analytics').href=`http://${host}:8003`;
function showToast(msg){const t=document.getElementById('toast');t.textContent=msg;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2000)}
async function createOrder(){
const product=document.getElementById('product').value;
const quantity=parseInt(document.getElementById('quantity').value);
const res=await fetch('/api/orders',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({product,quantity})});
if(res.ok){showToast('Order created!');loadOrders()}
}
async function loadOrders(){
const res=await fetch('/api/orders');const data=await res.json();
if(!data.orders.length){document.getElementById('orders-body').innerHTML='<div class="empty">No orders yet</div>';return}
let html='<table><thead><tr><th>ID</th><th>Product</th><th>Qty</th><th>Time</th></tr></thead><tbody>';
for(const o of data.orders.slice().reverse()){
const t=new Date(o.timestamp*1000).toLocaleTimeString();
html+=`<tr><td>${o.id}</td><td>${o.product}</td><td>${o.quantity}</td><td>${t}</td></tr>`}
html+='</tbody></table>';document.getElementById('orders-body').innerHTML=html}
loadOrders();setInterval(loadOrders,3000);
</script>
</body>
</html>"""
