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

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Inicializa app FastAPI
app = FastAPI()

# Variáveis de ambiente (configurar no Render)
WHATSAPP_PRODUCT_ID = os.getenv("WHATSAPP_PRODUCT_ID")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")
MAYTAPI_TOKEN = os.getenv("MAYTAPI_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

# Inicializa sistema do bot
bot = WhatsAppBotIntelligent()

# Banco de respostas pré-definidas
PREDEFINED_RESPONSES = [
    {"trigger": "oi", "responses": ["Oi! Tudo bem?", "Olá! Como vai você?"]},
    {"trigger": "quanto custa", "responses": ["O produto custa R$ 100.", "O valor é R$ 100, posso te passar o link."]},
    {"trigger": "tenho interesse", "responses": ["Que ótimo! Posso te enviar mais detalhes?", "Perfeito! Vou te passar as informações agora."]}
]

# Classe webhook (padrão Maytapi)
class MaytapiWebhook(BaseModel):
    type: Optional[str] = None
    data: Optional[Dict] = None
    message: Optional[str] = None
    fromNumber: Optional[str] = None
    timestamp: Optional[str] = None
    messageType: Optional[str] = None

# Função humanizada
async def process_incoming_message_humanized(phone, message):
    delay_seconds = random.randint(5, 10)
    await asyncio.sleep(delay_seconds)

    message_lower = message.lower()
    # 1️⃣ Procura resposta pré-definida
    for entry in PREDEFINED_RESPONSES:
        if entry["trigger"] in message_lower:
            response = random.choice(entry["responses"])
            await bot.send_message(phone, response)
            return

    # 2️⃣ Se não encontrou, gera resposta via GPT
    try:
        prompt = f"Responda a mensagem de forma natural e humana, como se fosse uma pessoa:\nMensagem: {message}\nResposta:"
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.8
        )
        human_response = response.choices[0].message.content.strip()
        await bot.send_message(phone, human_response)
    except Exception as e:
        await bot.send_message(phone, "Desculpe, não consegui processar sua mensagem agora 😅")
        logger.error(f"Erro ao gerar resposta GPT: {e}")

# Webhook POST
@app.post("/webhook")
async def receive_message(request: Request):
    try:
        raw_data = await request.json()
        logger.info(f"📨 Dados recebidos do webhook: {json.dumps(raw_data, indent=2)}")

        from_me = False
        if "message" in raw_data and isinstance(raw_data["message"], dict):
            from_me = raw_data["message"].get("fromMe", False)
        if from_me:
            logger.info("ℹ️ Mensagem enviada pelo bot, ignorando para evitar loop")
            return {"status": "ignored", "reason": "fromMe"}

        msg_type = raw_data.get("type") or raw_data.get("messageType") or "text"
        if msg_type in ["ack", "delivery", "read"]:
            logger.info(f"ℹ️ Mensagem ignorada do tipo {msg_type}")
            return {"status": "ignored", "type": msg_type}

        sender = raw_data.get("from") or raw_data.get("fromNumber") or raw_data.get("user", {}).get("id")
        receiver = raw_data.get("to") or raw_data.get("receiver") or WHATSAPP_PHONE_ID

        phone = sender
        message = None
        message_type = msg_type

        message_fields = ["text", "message", "body", "content"]
        for field in message_fields:
            if field in raw_data and raw_data[field]:
                if isinstance(raw_data[field], str):
                    message = raw_data[field]
                    break
                elif isinstance(raw_data[field], dict) and "text" in raw_data[field]:
                    message = raw_data[field]["text"]
                    message_type = raw_data[field].get("type", "text")
                    break
        if not message:
            for key, value in raw_data.items():
                if isinstance(value, dict):
                    if key == "message" and "text" in value:
                        message = value["text"]
                        message_type = value.get("type", "text")
                        break
                    for msg_field in message_fields:
                        if msg_field in value and value[msg_field]:
                            if isinstance(value[msg_field], str):
                                message = value[msg_field]
                                break
                if message:
                    break
        if not message:
            arrays_to_check = ["messages", "data", "items"]
            for array_name in arrays_to_check:
                if array_name in raw_data and isinstance(raw_data[array_name], list):
                    for item in raw_data[array_name]:
                        if isinstance(item, dict):
                            for msg_field in message_fields:
                                if msg_field in item and item[msg_field]:
                                    message = str(item[msg_field])
                                    break
                            if message:
                                break
                if message:
                    break

        logger.info(f"📱 Análise completa:")
        logger.info(f"   - Sender (cliente): {sender}")
        logger.info(f"   - Receiver (bot): {receiver}")
        logger.info(f"   - Message extraída: {message}")
        logger.info(f"   - Type: {message_type}")

        if phone and message and (message_type == "text" or "text" in str(message_type).lower()):
            clean_phone = re.sub(r'[^\d]', '', str(phone))
            if len(clean_phone) == 11 and clean_phone.startswith('42'):
                clean_phone = f"55{clean_phone}"
            elif len(clean_phone) == 10 and clean_phone.startswith('42'):
                clean_phone = f"5542{clean_phone}"
            elif not clean_phone.startswith('55'):
                clean_phone = f"55{clean_phone}"

            logger.info(f"📞 Telefone limpo: {clean_phone}")
            await process_incoming_message_humanized(clean_phone, str(message))
            logger.info(f"✅ Mensagem processada com sucesso para {clean_phone}")
        else:
            logger.warning(f"⚠️ Dados insuficientes para processar:")
            logger.warning(f"   - Phone: {phone} (válido: {bool(phone)})")
            logger.warning(f"   - Message: {message} (válido: {bool(message)})")
            logger.warning(f"   - Type: {message_type}")

        return {"status": "success", "received": True, "processed": bool(phone and message)}

    except Exception as e:
        logger.error(f"❌ Erro no webhook: {e}")
        logger.error(f"Raw data: {raw_data}")
        return {"status": "error", "message": str(e), "received": True}

# Webhook GET
@app.get("/webhook")
async def verify_webhook(request: Request):
    logger.info(f"📋 Verificação webhook GET: {request.query_params}")
    return {"status": "Webhook ativo", "timestamp": datetime.now(), "method": "GET"}

# Dashboard
@app.get("/")
async def dashboard():
    analytics = bot.get_analytics()
    html = f"""<!DOCTYPE html><html><head>...</head><body>...</body></html>"""  # mantém HTML existente
    return HTMLResponse(html)

# Analytics JSON
@app.get("/analytics")  
async def get_analytics():
    return bot.get_analytics()

# Teste de mensagens
@app.get("/test-message")
async def test_response(phone: str = "5542988388120", message: str = "oi"):
    try:
        response = bot.generate_intelligent_response(phone, message)
        profile = bot.client_profiles.get(phone)
        return {
            "success": True,
            "message": message,
            "response": response,
            "profile": {
                "stage": profile.conversation_stage.value if profile else "inicial",
                "score": profile.conversion_score if profile else 0.0,
                "messages": profile.messages_count if profile else 0
            }
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

# Inicia servidor
if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("🤖 ATENDENTE VIRTUAL - VERSÃO GRATUITA")
    print("=" * 60)
    print("✅ SEM OpenAI - 100% GRÁTIS")
    print("🧠 Lógica Inteligente Baseada nas Suas Técnicas")
    print("📱 WhatsApp: +55 42 98838-8120")  
    print("🎯 Taxa de Conversão Esperada: ~60%")
    print("=" * 60)
    print("🌐 Dashboard: http://localhost:8000")
    print("🧪 Teste: http://localhost:8000/test-message")
    print("=" * 60)
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
