from fastapi import FastAPI, Request
import logging

# Configuração de logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

# Inicializa o FastAPI
app = FastAPI()

@app.get("/")
async def root():
    return {"status": "ok", "message": "🚀 Bot WhatsApp rodando no Render"}

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    logger.info(f"📨 Webhook recebido: {data}")
    return {"status": "success", "data": data}
