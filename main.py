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
WHATSAPP_PRODUCT_ID = os.getenv("WHATSAPP_PRODUCT_ID", "ID_PRODUTO_DEFAULT")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID", "ID_TELEFONE_DEFAULT")
MAYTAPI_TOKEN = os.getenv("MAYTAPI_TOKEN", "TOKEN_DEFAULT")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", None)
if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY
else:
    logger.warning("⚠️ OPENAI_API_KEY não definida, respostas GPT não funcionarão!")

# Inicializa sistema do bot
try:
    bot = WhatsAppBotIntelligent()
except Exception as e:
    logger.error(f"❌ Classe WhatsAppBotIntelligent não encontrada: {e}")
    bot = None

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
    """
    Processa a mensagem simulando comportamento humano:
    - Delay aleatório 5-10s
    - Resposta pré-definida ou GPT se não achar trigger
    """
    if not bot:
        logger.warning("Bot não inicializado. Ignorando mensagem.")
        return
    delay_seconds = random.randint(5, 10)
    await asyncio.sleep(delay_seconds)

    message_lower = message.lower()
    # Procura resposta pré-definida
    for entry in PREDEFINED_RESPONSES:
        if entry["trigger"] in message_lower:
            response = random.choice(entry["responses"])
            await bot.send_message(phone, response)
            return

    # Se não encontrou, gera resposta via GPT
    if OPENAI_API_KEY:
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
    else:
        await bot.send_message(phone, "💡 Sem chave GPT. Apenas respostas pré-definidas disponíveis.")

# Webhook POST
@app.post("/webhook")
async def receive_message(request: Request):
    try:
        raw_data = await request.json()
        logger.info(f"📨 Dados recebidos do webhook: {json.dumps(raw_data, indent=2)}")

        # Ignora mensagens enviadas pelo próprio bot
        from_me = False
        if "message" in raw_data and isinstance(raw_data["message"], dict):
            from_me = raw_data["message"].get("fromMe", False)
        if from_me:
            logger.info("ℹ️ Mensagem enviada pelo bot, ignorando para evitar loop")
            return {"status": "ignored", "reason": "fromMe"}

        # Ignora mensagens de status
        msg_type = raw_data.get("type") or raw_data.get("messageType") or "text"
        if msg_type in ["ack", "delivery", "read"]:
            logger.info(f"ℹ️ Mensagem ignorada do tipo {msg_type}")
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
        if not message:
            for key, value in raw_data.items():
                if isinstance(value, dict):
                    for msg_field in message_fields:
                        if msg_field in value and value[msg_field]:
                            message = value[msg_field] if isinstance(value[msg_field], str) else value[msg_field].get("text")
                            if message:
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
        logger.info(f"   - Sender: {sender}")
        logger.info(f"   - Message: {message}")
        logger.info(f"   - Type: {msg_type}")

        if phone and message:
            clean_phone = re.sub(r"[^\d]", "", str(phone))
            if not clean_phone.startswith("55"):
                clean_phone = f"55{clean_phone}"
            logger.info(f"📞 Telefone limpo: {clean_phone}")
            await process_incoming_message_humanized(clean_phone, str(message))
            logger.info(f"✅ Mensagem processada com sucesso para {clean_phone}")
        else:
            logger.warning("⚠️ Dados insuficientes para processar mensagem")

        return {"status": "success", "received": True, "processed": bool(phone and message)}

    except Exception as e:
        logger.error(f"❌ Erro no webhook: {e}")
        return {"status": "error", "message": str(e), "received": True}

# Webhook GET
@app.get("/webhook")
async def verify_webhook(request: Request):
    return {"status": "Webhook ativo", "timestamp": datetime.now(), "method": "GET"}

# Dashboard completo
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
            <h2>📊 Estatísticas Tempo Real</h2>
            <p>Clientes hoje: <span class="metric">{analytics.get('clients_today', 0)}</span></p>
            <p>Total clientes: <span class="metric">{analytics.get('total_clients', 0)}</span></p>
            <p>Taxa conversão: <span class="metric">{analytics.get('conversion_rate', '0%')}</span></p>
            <p>Status: <span class="success">{analytics.get('status', 'Loading...')}</span></p>
        </div>
        <div class="card">
            <h2>🎯 Performance</h2>
            <p>Links enviados: <span class="metric">{analytics.get('attempts', 0)}</span></p>
            <p>Conversões: <span class="metric">{analytics.get('conversions', 0)}</span></p>
        </div>
        <div class="card">
            <h2>🔧 Debug & Testes</h2>
            <div class="debug">
                <strong>Webhook URL:</strong> /webhook<br>
                <strong>WhatsApp Number:</strong> +55 42 98838-8120<br>
                <strong>Maytapi Product ID:</strong> {WHATSAPP_PRODUCT_ID}<br>
                <strong>Phone ID:</strong> {WHATSAPP_PHONE_ID}
            </div>
            <p><a href="/test-message?phone=5542988388120&message=oi" target="_blank">🧪 Testar: "oi"</a></p>
            <p><a href="/test-message?phone=5542988388120&message=tenho interesse" target="_blank">🧪 Testar: "tenho interesse"</a></p>
            <p><a href="/test-message?phone=5542988388120&message=quanto custa" target="_blank">🧪 Testar: "quanto custa"</a></p>
            <p><a href="/analytics" target="_blank">📊 Analytics JSON</a></p>
        </div>
        <div class="card">
            <h2>📱 Como Testar no WhatsApp</h2>
            <p>1. Mande mensagem para: <strong>+55 42 98838-8120</strong></p>
            <p>2. Exemplo: "Oi tudo bem"</p>
            <p>3. A IA deve responder automaticamente</p>
            <p>4. Continue a conversa para testar o funil de vendas</p>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(html)

# Analytics JSON
@app.get("/analytics")  
async def get_analytics():
    return bot.get_analytics() if bot else {}

# Teste de mensagens com delay humanizado
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
    print("="*60)
    print("🤖 ATENDENTE VIRTUAL - VERSÃO COMPLETA HUMANIZADA")
    print("="*60)
    uvicorn.run(app, host="0.0.0.0", port=8000)
