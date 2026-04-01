# La Mákina — Sistema de Pedidos con IA

Sistema de gestión de requests de producción con análisis automático de briefs y asistente durante producción. Stack: FastAPI + SQLite + DeepSeek via Together AI.

## Stack

- **Backend**: FastAPI + Uvicorn
- **DB**: SQLite con volumen persistente en Railway
- **IA**: DeepSeek R1 Distill 70B via Together AI
- **Deploy**: Railway

## Variables de entorno

| Variable | Descripción |
|---|---|
| `TOGETHER_API_KEY` | API key de Together AI |
| `DB_PATH` | Ruta de la DB (default: `/data/lamakina.db`) |
| `PORT` | Puerto (Railway lo inyecta automáticamente) |

## Setup local

```bash
# Clonar
git clone https://github.com/TU_USUARIO/lamakina-requests
cd lamakina-requests

# Instalar dependencias
pip install -r requirements.txt

# Variables de entorno
export TOGETHER_API_KEY=tu_key_aqui
export DB_PATH=./data/lamakina.db

# Correr
uvicorn app.main:app --reload --port 8000
```

## Deploy en Railway

1. **Crear proyecto** en [railway.app](https://railway.app)
2. **Conectar repositorio** GitHub
3. **Configurar variables de entorno**:
   - `TOGETHER_API_KEY` = tu key de Together AI
4. **Añadir volumen persistente**:
   - En el servicio: Settings → Volumes
   - Mount path: `/data`
   - Esto es CRÍTICO — sin volumen, la DB se borra en cada deploy
5. **Deploy automático** desde cada push a `main`

## Flujo del sistema

```
Cliente llena brief
       ↓
DeepSeek analiza gaps automáticamente
       ↓
Request se crea con análisis visible
       ↓
Equipo ve gaps + preguntas sugeridas al cliente
       ↓
Hilo de comunicación con asistente IA disponible
       ↓
Equipo consulta IA durante producción (SSE streaming)
```

## Estructura del proyecto

```
lamakina-requests/
├── app/
│   └── main.py          # FastAPI app + lógica IA
├── templates/
│   ├── base.html        # Layout base
│   ├── index.html       # Lista de pedidos
│   ├── nuevo.html       # Formulario nuevo pedido
│   └── request.html     # Vista detalle + hilo + IA
├── static/              # Assets estáticos
├── requirements.txt
├── Procfile
├── railway.json
└── .gitignore
```
