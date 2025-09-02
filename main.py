import json
import re
import random
import asyncio
from datetime import datetime
from typing import Optional, Dict
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import logging
import openai
import os

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI
app = FastAPI()

# Variáveis de ambiente
WHATSAPP_PRODUCT_ID = os.getenv("WHATSAPP_PRODUCT_ID", "ID_PRODUTO_DEFAULT")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID", "ID_TELEFONE_DEFAULT")
MAYTAPI_TOKEN = os.getenv("MAYTAPI_TOKEN", "TOKEN_DEFAULT")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", None)
if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY
else:
    logger.warning("⚠️ OPENAI_API_KEY não definida, respostas GPT não funcionarão!")

# ------------------------------
# Classe WhatsAppBotIntelligent
# ------------------------------
class ConversationStage:
    INICIAL = "inicial"
    INTERESSE = "interesse"
    FECHAMENTO = "fechamento"

class ClientProfile:
    def __init__(self):
        self.conversation_stage = ConversationStage.INICIAL
        self.conversion_score = 0.0
        self.messages_count = 0

class WhatsAppBotIntelligent:
    def __init__(self):
        self.client_profiles = {}         # {phone: ClientProfile}
        self.conversation_history = {}    # {phone: [{"role": "user"/"bot", "content": "mensagem"}]}
        self.analytics_data = {
            "clients_today": 0,
            "total_clients": 0,
            "conversion_rate": "0%",
            "status": "online",
            "attempts": 0,
            "conversions": 0
        }

    async def send_message(self, phone: str, message: str):
        """Envia mensagem com delay humanizado e atualiza histórico"""
        if phone not in self.conversation_history:
            self.conversation_history[phone] = []
        self.conversation_history[phone].append({"role": "bot", "content": message})

        if phone not in self.client_profiles:
            self.client_profiles[phone] = ClientProfile()
        profile = self.client_profiles[phone]
        profile.messages_count += 1

        # Analytics
        self.analytics_data["attempts"] += 1

        # Delay humanizado 5-10s
        delay_seconds = random.randint(5, 10)
        await asyncio.sleep(delay_seconds)

        # Log da mensagem
        logger.info(f"💬 [BOT -> {phone}]: {message}")

    def get_analytics(self):
        total_clients = len(self.client_profiles)
        self.analytics_data["total_clients"] = total_clients
        clients_today = sum(1 for profile in self.client_profiles.values() if profile.messages_count > 0)
        self.analytics_data["clients_today"] = clients_today
        if total_clients > 0:
            self.analytics_data["conversion_rate"] = f"{int((self.analytics_data['conversions']/total_clients)*100)}%"
        return self.analytics_data

# Inicializa bot
bot = WhatsAppBotIntelligent()

# ------------------------------
# Configurações de personalidade
# ------------------------------
BOT_PERSONALITY = {
    "name": "VitorBot",
    "age": 25,
    "style": "informal e amigável",
    "interests": ["tecnologia", "música", "cinema"],
    "greetings": ["Oi! 😃", "Olá! Como vai?", "E aí, tudo bem?"],
}

# Respostas pré-definidas
PREDEFINED_RESPONSES = [
    {"trigger": "oi", "responses": ["Oi! Tudo bem?", "Olá! Como vai você?"]},
    {"trigger": "quanto custa", "responses": ["O produto custa R$ 100.", "O valor é R$ 100, posso te passar o link."]},
    {"trigger": "tenho interesse", "responses": ["Que ótimo! Posso te enviar mais detalhes?", "Perfeito! Vou te passar as informações agora."]}
]

# ------------------------------
# Função principal de resposta
# ------------------------------
async def process_incoming_message_humanized(phone, message):
    if not bot:
        logger.warning("Bot não inicializado. Ignorando mensagem.")
        return

    # Delay proporcional ao tamanho da mensagem (simula digitando)
    delay_seconds = random.randint(3, 5) + len(message)/20
    await asyncio.sleep(delay_seconds)

    message_lower = message.lower()
    # Procura resposta pré-definida
    for entry in PREDEFINED_RESPONSES:
        if entry["trigger"] in message_lower:
            response = random.choice(entry["responses"])
            await bot.send_message(phone, response)
            return

    # Se não encontrou, usa GPT
    if OPENAI_API_KEY:
        try:
            # Histórico últimas 5 mensagens
            if phone not in bot.conversation_history:
                bot.conversation_history[phone] = []
            bot.conversation_history[phone].append({"role": "user", "content": message})
            history_messages = bot.conversation_history[phone][-5:]
            prompt_history = "\n".join([f"{m['role']}: {m['content']}" for m in history_messages])
            
            prompt = f"""
Você é {BOT_PERSONALITY['name']}, {BOT_PERSONALITY['age']} anos.
Estilo: {BOT_PERSONALITY['style']}.
Interesses: {', '.join(BOT_PERSONALITY['interests'])}.
Responda de forma natural e humana a mensagem abaixo, mantendo personalidade consistente:

{prompt_history}
Bot:
"""
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.9,
                presence_penalty=0.6,
                frequency_penalty=0.5
            )
            human_response = response.choices[0].message.content.strip()
            await bot.send_message(phone, human_response)
        except Exception as e:
            await bot.send_message(phone, "Desculpe, não consegui processar sua mensagem agora 😅")
            logger.error(f"Erro ao gerar resposta GPT: {e}")
    else:
        await bot.send_message(phone, "💡 Sem chave GPT. Apenas respostas pré-definidas disponíveis.")

# ------------------------------
# Webhook POST
# ------------------------------
@app.post("/webhook")
async def receive_message(request: Request):
    try:
        raw_data = await request.json()
        logger.info(f"📨 Dados recebidos do webhook: {json.dumps(raw_data, indent=2)}")

        # Ignora mensagens enviadas pelo bot
        from_me = raw_data.get("message", {}).get("fromMe", False)
        if from_me:
            return {"status": "ignored", "reason": "fromMe"}

        # Ignora mensagens de status
        msg_type = raw_data.get("type") or raw_data.get("messageType") or "text"
        if msg_type in ["ack", "delivery", "read"]:
            return {"status": "ignored", "type": msg_type}

        # Extrai sender
        sender = raw_data.get("from") or raw_data.get("fromNumber") or raw_data.get("user", {}).get("id")
        phone = sender

        # Extrai mensagem
        message = None
        message_fields = ["text", "message", "body", "content"]
        for field in message_fields:
            if field in raw_data and raw_data[field]:
                if isinstance(raw_data[field], str):
                    message = raw_data[field]
                    break
                elif isinstance(raw_data[field], dict) and "text" in raw_data[field]:
                    message = raw_data[field]["text"]
                    break

        if phone and message:
            clean_phone = re.sub(r"[^\d]", "", str(phone))
            if not clean_phone.startswith("55"):
                clean_phone = f"55{clean_phone}"
            await process_incoming_message_humanized(clean_phone, str(message))

        return {"status": "success", "received": True, "processed": bool(phone and message)}

    except Exception as e:
        logger.error(f"❌ Erro no webhook: {e}")
        return {"status": "error", "message": str(e), "received": True}

# ------------------------------
# Webhook GET
# ------------------------------
@app.get("/webhook")
async def verify_webhook(request: Request):
    return {"status": "Webhook ativo", "timestamp": datetime.now(), "method": "GET"}

# ------------------------------
# Dashboard
# ------------------------------
@app.get("/")
async def dashboard():
    analytics = bot.get_analytics() if bot else {}
    html = f"""
<!DOCTYPE html>
<html>
<head>
<title>🤖 Atendente Virtual - Dashboard</title>
<meta charset="utf-8">
<meta http-equiv="refresh" content="30">
<style>
body {{ font-family: Arial; margin: 40px; background: #f5f5f5; }}
.card {{ background: white; padding: 20px; margin: 10px 0; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
.metric {{ font-size: 24px; font-weight: bold; color: #2196F3; }}
.status {{ font-size: 18px; margin: 10px 0; }}
.success {{ color: #4CAF50; font-weight: bold; }}
.debug {{ background: #f8f9fa; padding: 10px; border-left: 4px solid #007bff; margin: 10px 0; font-family: monospace; }}
</style>
</head>
<body>
<h1>🤖 Atendente Virtual - Dashboard</h1>
<div class="card">
<div class="status success">✅ SISTEMA FUNCIONANDO</div>
<p>Clientes hoje: <span class="metric">{analytics.get('clients_today', 0)}</span></p>
<p>Total clientes: <span class="metric">{analytics.get('total_clients', 0)}</span></p>
<p>Taxa conversão: <span class="metric">{analytics.get('conversion_rate', '0%')}</span></p>
</div>
</body>
</html>
"""
    return HTMLResponse(html)

# ------------------------------
# Analytics JSON
# ------------------------------
@app.get("/analytics")  
async def get_analytics():
    return bot.get_analytics() if bot else {}

# ------------------------------
# Teste de mensagens
# ------------------------------
@app.get("/test-message")
async def test_response(phone: str = "5542988388120", message: str = "oi"):
    try:
        clean_phone = re.sub(r"[^\d]", "", str(phone))
        if not clean_phone.startswith("55"):
            clean_phone = f"55{clean_phone}"
        await process_incoming_message_humanized(clean_phone, message)
        profile = bot.client_profiles.get(clean_phone) if bot else None
        return {
            "success": True,
            "message": message,
            "profile": {
                "stage": profile.conversation_stage if profile else "inicial",
                "score": profile.conversion_score if profile else 0.0,
                "messages": profile.messages_count if profile else 0
            }
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

# ------------------------------
# Rodar servidor
# ------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
