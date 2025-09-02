import re
import json
import random
import asyncio
from datetime import datetime
from typing import Optional, Dict
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import logging
import httpx
import os
import openai

# Configurações iniciais
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MAYTAPI_BASE_URL = os.getenv("MAYTAPI_BASE_URL")  # exemplo: https://api.maytapi.com/api/<product_id>/<phone_id>/sendMessage
MAYTAPI_TOKEN = os.getenv("MAYTAPI_TOKEN")

if not OPENAI_API_KEY:
    logger.warning("⚠️ OPENAI_API_KEY não definida, respostas GPT não funcionarão!")

openai.api_key = OPENAI_API_KEY

app = FastAPI()

# ======================
# Classe do Bot
# ======================
class WhatsAppBotIntelligent:
    def __init__(self):
        self.client_profiles = {}

    async def process_incoming_message(self, phone: str, message: str):
        # Delay de 5 a 10 segundos para parecer humano
        await asyncio.sleep(random.randint(5, 10))
        
        try:
            response = await self.generate_intelligent_response(phone, message)
            await self.send_whatsapp_message(phone, response)
            logger.info(f"💬 [BOT -> {phone}]: {response}")
        except Exception as e:
            logger.error(f"Erro ao processar mensagem: {e}")

    async def generate_intelligent_response(self, phone: str, message: str) -> str:
        try:
            prompt = f"Responda de forma natural e humana, curta e direta ao ponto: {message}"
            completion = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150,
                temperature=0.7
            )
            response = completion.choices[0].message.content.strip()
            return response
        except Exception as e:
            logger.error(f"Erro ao gerar resposta GPT: {e}")
            return "Desculpe, não consegui processar sua mensagem agora 😅"

    async def send_whatsapp_message(self, phone: str, text: str):
        if not MAYTAPI_BASE_URL or not MAYTAPI_TOKEN:
            logger.error("❌ Configuração do Maytapi faltando.")
            return

        headers = {
            "Authorization": f"Bearer {MAYTAPI_TOKEN}",
            "Content-Type": "application/json"
        }
        payload = {
            "to_number": phone,
            "type": "text",
            "text": text
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(MAYTAPI_BASE_URL, headers=headers, json=payload)
                response.raise_for_status()
        except Exception as e:
            logger.error(f"Erro ao enviar mensagem WhatsApp: {e}")

bot = WhatsAppBotIntelligent()

# ======================
# Webhook
# ======================
@app.post("/webhook")
async def receive_message(request: Request):
    try:
        raw_data = await request.json()
        logger.info(f"📨 Webhook recebido: {raw_data}")

        # Processa apenas mensagens do usuário
        if raw_data.get("type") != "message":
            logger.info(f"ℹ️ Webhook não é mensagem de usuário, ignorando: {raw_data.get('type')}")
            return {"status": "ignored"}

        phone = raw_data.get("user", {}).get("phone")
        message = raw_data.get("message", {}).get("text")
        if phone and message:
            clean_phone = re.sub(r"[^\d]", "", phone)
            if not clean_phone.startswith("55"):
                clean_phone = f"55{clean_phone}"
            await bot.process_incoming_message(clean_phone, message)
            return {"status": "success"}
        else:
            logger.warning("⚠️ Dados insuficientes para processar")
            return {"status": "failed", "reason": "missing phone or message"}
    except Exception as e:
        logger.error(f"❌ Erro no webhook: {e}")
        return {"status": "error", "message": str(e)}

# ======================
# Dashboard simples
# ======================
@app.get("/")
async def dashboard():
    html = f"""
    <html>
        <head><title>🤖 WhatsApp Bot Dashboard</title></head>
        <body>
            <h1>Bot Online</h1>
            <p>Data/Hora: {datetime.now()}</p>
            <p>Status: Funcionando</p>
        </body>
    </html>
    """
    return HTMLResponse(html)

# ======================
# Teste de mensagem
# ======================
@app.get("/test-message")
async def test_response(phone: str = "5542988388120", message: str = "Oi"):
    await bot.process_incoming_message(phone, message)
    return {"status": "sent"}

# ======================
# Inicialização
# ======================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
