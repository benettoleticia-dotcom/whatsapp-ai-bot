import os
import time
import random
import logging
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from openai import OpenAI
import httpx

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

# Inicialização do FastAPI
app = FastAPI(title="WhatsApp AI Bot")

# OpenAI client
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logger.warning("⚠️ OPENAI_API_KEY não definida, respostas GPT não funcionarão!")

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# Maytapi configs
MAYTAPI_BASE_URL = os.getenv("MAYTAPI_BASE_URL")
MAYTAPI_TOKEN = os.getenv("MAYTAPI_TOKEN")

if not MAYTAPI_BASE_URL or not MAYTAPI_TOKEN:
    logger.error("❌ Configuração do Maytapi faltando. Adicione MAYTAPI_BASE_URL e MAYTAPI_TOKEN.")

# Função para gerar respostas com GPT
def generate_gpt_response(message: str) -> str:
    if not client:
        return "Desculpe, GPT não configurado 😅"
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": message}],
            temperature=0.7,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Erro ao gerar resposta GPT: {e}")
        return "Desculpe, não consegui processar sua mensagem agora 😅"

# Função para enviar mensagens via Maytapi
def send_whatsapp_message(to_number: str, text: str):
    if not MAYTAPI_BASE_URL or not MAYTAPI_TOKEN:
        logger.error("Configuração do Maytapi faltando.")
        return
    url = MAYTAPI_BASE_URL
    payload = {"to_number": to_number, "text": text, "type": "text"}
    headers = {"Authorization": f"Bearer {MAYTAPI_TOKEN}"}
    try:
        response = httpx.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        logger.info(f"💬 [BOT -> {to_number}]: {text}")
    except Exception as e:
        logger.error(f"Erro ao enviar mensagem WhatsApp: {e}")

# Webhook endpoint
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    logger.info(f"📨 Webhook recebido: {data}")

    # Validar se é mensagem de usuário
    message_info = data.get("message")
    user_info = data.get("user")
    if not message_info or not user_info:
        logger.warning("⚠️ Dados insuficientes ou mensagem do próprio bot, ignorando.")
        return {"status": "ignored"}

    if message_info.get("fromMe"):
        logger.info("Mensagem do próprio bot, ignorando.")
        return {"status": "ignored"}

    text = message_info.get("text")
    to_number = user_info.get("id")

    if not text or not to_number:
        logger.warning("⚠️ Mensagem vazia ou número inválido.")
        return {"status": "ignored"}

    # Delay humano aleatório
    time.sleep(random.randint(5, 10))

    # Gerar resposta GPT
    reply = generate_gpt_response(text)

    # Enviar mensagem
    send_whatsapp_message(to_number, reply)

    return {"status": "ok"}

# Página inicial simples
@app.get("/")
async def index():
    html = """
    <html>
        <head><title>WhatsApp AI Bot</title></head>
        <body>
            <h1>🤖 WhatsApp AI Bot</h1>
            <p>Webhook ativo e pronto para receber mensagens.</p>
        </body>
    </html>
    """
    return HTMLResponse(html)

# Analytics (opcional)
@app.get("/analytics")
async def analytics():
    return {"status": "analytics não implementado ainda"}

# Teste de mensagem
@app.get("/test-message")
async def test_message(phone: str, message: str):
    reply = generate_gpt_response(message)
    send_whatsapp_message(phone, reply)
    return {"phone": phone, "message": message, "reply": reply}

# Rodar localmente
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
