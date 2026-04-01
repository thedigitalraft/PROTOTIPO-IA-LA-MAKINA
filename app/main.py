import os
import sqlite3
import json
import httpx
from datetime import datetime
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
from typing import Optional
import asyncio

DB_PATH = os.environ.get("DB_PATH", "/data/lamakina.db")
TOGETHER_API_KEY = os.environ.get("TOGETHER_API_KEY", "")
TOGETHER_MODEL = "deepseek-ai/DeepSeek-R1-Distill-Llama-70B-free"
TOGETHER_API_URL = "https://api.together.ai/v1/chat/completions"

def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente TEXT NOT NULL,
            tipo TEXT NOT NULL,
            brief TEXT NOT NULL,
            deadline TEXT,
            status TEXT DEFAULT 'Recibido',
            ia_analysis TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER NOT NULL,
            autor TEXT NOT NULL,
            rol TEXT NOT NULL,
            contenido TEXT NOT NULL,
            es_interno INTEGER DEFAULT 0,
            es_ia INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (request_id) REFERENCES requests(id)
        );
    """)
    conn.commit()
    conn.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(title="La Mákina — Request System", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

STATUSES = ["Recibido", "En espera de respuesta", "Ya hemos comenzado", "En revisión", "Entregado"]
TIPOS = ["Patrocinio", "Redes sociales", "Video institucional", "Campaña", "Presentación", "Otro"]

async def call_deepseek(system_prompt: str, user_prompt: str) -> str:
    if not TOGETHER_API_KEY:
        return "⚠ TOGETHER_API_KEY no configurada."
    headers = {
        "Authorization": f"Bearer {TOGETHER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": TOGETHER_MODEL,
        "max_tokens": 800,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(TOGETHER_API_URL, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()

async def analyze_brief(brief: str, tipo: str, deadline: str) -> str:
    system = """Eres el asistente de producción de La Mákina, una agencia de contenido AI-first.
Tu trabajo es analizar briefs de clientes e identificar información faltante ANTES de asignar el pedido al equipo.
Sé directo, concreto y útil. Responde siempre en español.
Formato: devuelve un JSON con esta estructura exacta:
{
  "problemas": ["problema 1", "problema 2"],
  "preguntas_cliente": ["pregunta 1", "pregunta 2"],
  "riesgo": "bajo|medio|alto",
  "resumen": "una frase de resumen del pedido"
}"""
    user = f"""Tipo de pedido: {tipo}
Deadline: {deadline}
Brief del cliente:
{brief}

Analiza este brief e identifica qué información falta para que el equipo pueda producir sin fricciones."""
    raw = await call_deepseek(system, user)
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            return raw[start:end]
    except:
        pass
    return json.dumps({
        "problemas": ["No se pudo analizar el brief automáticamente."],
        "preguntas_cliente": [],
        "riesgo": "medio",
        "resumen": brief[:120]
    })

async def suggest_response(request_data: dict, context: str, question: str) -> str:
    system = """Eres el asistente de producción de La Mákina.
Ayudas al equipo a redactar mensajes claros para el cliente durante la producción.
Escribe mensajes directos, profesionales y sin tecnicismos. Siempre en español."""
    user = f"""Pedido: {request_data['tipo']} para {request_data['cliente']}
Brief original: {request_data['brief']}
Contexto del hilo: {context}
El equipo necesita: {question}

Redacta el mensaje que se enviaría al cliente."""
    return await call_deepseek(system, user)

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM requests ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return templates.TemplateResponse("index.html", {"request": request, "requests": rows, "statuses": STATUSES})

@app.get("/nuevo", response_class=HTMLResponse)
async def nuevo_form(request: Request):
    return templates.TemplateResponse("nuevo.html", {"request": request, "tipos": TIPOS})

@app.post("/nuevo")
async def nuevo_submit(
    cliente: str = Form(...),
    tipo: str = Form(...),
    brief: str = Form(...),
    deadline: str = Form("")
):
    analysis_raw = await analyze_brief(brief, tipo, deadline)
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO requests (cliente, tipo, brief, deadline, ia_analysis) VALUES (?, ?, ?, ?, ?)",
        (cliente, tipo, brief, deadline, analysis_raw)
    )
    req_id = cur.lastrowid
    conn.commit()
    conn.close()
    return RedirectResponse(f"/request/{req_id}", status_code=303)

@app.get("/request/{req_id}", response_class=HTMLResponse)
async def ver_request(request: Request, req_id: int):
    conn = get_db()
    req = conn.execute("SELECT * FROM requests WHERE id = ?", (req_id,)).fetchone()
    if not req:
        raise HTTPException(404, "Request no encontrado")
    msgs = conn.execute(
        "SELECT * FROM messages WHERE request_id = ? ORDER BY created_at ASC",
        (req_id,)
    ).fetchall()
    conn.close()
    analysis = {}
    try:
        analysis = json.loads(req["ia_analysis"] or "{}")
    except:
        pass
    return templates.TemplateResponse("request.html", {
        "request": request,
        "req": req,
        "msgs": msgs,
        "analysis": analysis,
        "statuses": STATUSES
    })

@app.post("/request/{req_id}/mensaje")
async def enviar_mensaje(
    req_id: int,
    autor: str = Form(...),
    rol: str = Form(...),
    contenido: str = Form(...),
    es_interno: int = Form(0)
):
    conn = get_db()
    conn.execute(
        "INSERT INTO messages (request_id, autor, rol, contenido, es_interno) VALUES (?, ?, ?, ?, ?)",
        (req_id, autor, rol, contenido, es_interno)
    )
    conn.commit()
    conn.close()
    return RedirectResponse(f"/request/{req_id}", status_code=303)

@app.post("/request/{req_id}/status")
async def update_status(req_id: int, status: str = Form(...)):
    conn = get_db()
    conn.execute("UPDATE requests SET status = ? WHERE id = ?", (status, req_id))
    conn.commit()
    conn.close()
    return RedirectResponse(f"/request/{req_id}", status_code=303)

@app.get("/request/{req_id}/ia-stream")
async def ia_stream(req_id: int, pregunta: str = ""):
    conn = get_db()
    req = conn.execute("SELECT * FROM requests WHERE id = ?", (req_id,)).fetchone()
    msgs = conn.execute(
        "SELECT * FROM messages WHERE request_id = ? ORDER BY created_at ASC LIMIT 10",
        (req_id,)
    ).fetchall()
    conn.close()
    if not req:
        raise HTTPException(404)

    context = "\n".join([f"{m['autor']}: {m['contenido']}" for m in msgs])
    req_dict = dict(req)

    async def generate():
        if not TOGETHER_API_KEY:
            yield "data: ⚠ Configura TOGETHER_API_KEY en las variables de entorno.\n\n"
            return
        headers = {
            "Authorization": f"Bearer {TOGETHER_API_KEY}",
            "Content-Type": "application/json"
        }
        system = """Eres el asistente de producción de La Mákina.
Ayudas al equipo durante la producción respondiendo preguntas y redactando mensajes.
Sé directo, útil y habla siempre en español."""
        payload = {
            "model": TOGETHER_MODEL,
            "max_tokens": 600,
            "stream": True,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": f"Pedido: {req_dict['tipo']} para {req_dict['cliente']}\nBrief: {req_dict['brief']}\nHilo reciente:\n{context}\n\nPregunta del equipo: {pregunta}"}
            ]
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", TOGETHER_API_URL, headers=headers, json=payload) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        chunk = line[6:]
                        if chunk == "[DONE]":
                            yield "data: [DONE]\n\n"
                            break
                        try:
                            data = json.loads(chunk)
                            delta = data["choices"][0]["delta"].get("content", "")
                            if delta:
                                yield f"data: {json.dumps({'text': delta})}\n\n"
                        except:
                            continue

    return StreamingResponse(generate(), media_type="text/event-stream")

@app.get("/health")
async def health():
    return {"status": "ok", "model": TOGETHER_MODEL}
