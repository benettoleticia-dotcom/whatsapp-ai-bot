import os
import time
import random
import logging
from fastapi import FastAPI, Request
import httpx
from openai import OpenAI

# Configuração de logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

# Inicializa FastAPI
app = FastAPI()

# Inicializa cliente OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logger.warning("⚠️ OPENAI_API_KEY não definida, respostas GPT não funcionarão!")
client = OpenAI(api_key=OPENAI_API_KEY)

# Configuração WhatsApp API (Maytapi ou similar)
MAYTAPI_URL = os.getenv("MAYTAPI_URL")  # exemplo: https://api.maytapi.com/api/...
MAYTAPI_TOKEN = os.getenv("MAYTAPI_TOKEN")

# Armazena histórico por usuário (apenas últimas mensagens para reduzir custo)
user_histories = {}

# Classe do bot inteligente
class WhatsAppBotIntelligent:
    def __init__(self):
        self.max_context_messages = 6  # limita quantas mensagens guarda por usuário

    async def get_gpt_response(self, user_id: str, user_message: str) -> str:
        try:
            # Inicializa histórico se não existir
            if user_id not in user_histories:
                user_histories[user_id] = []

            # Adiciona mensagem do usuário no histórico
            user_histories[user_id].append({"role": "user", "content": user_message})

            # Mantém apenas as últimas mensagens
            user_histories[user_id] = user_histories[user_id][-self.max_context_messages:]

            # Prompt de "personalidade"
            system_prompt = {
                "role": "system",
                "content": (
                    "Você é um atendente simpático e humano. "
                    "Responda de forma natural, breve, sem parecer robótico. "
                    "Sempre leve a conversa em direção à venda, mas de forma sutil e educada."
                ),
            }

            # Chamada ao modelo GPT com limite de tokens e modelo econômico
            response = client.chat.completions.create(
                model="gpt-4o-mini",  # modelo barato e rápido
                messages=[system_prompt] + user_histories[user_id],
                max_tokens=300,
                temperature=0.7,
            )

            reply = response.choices[0].message.content.strip()

            # Adiciona resposta do bot ao histórico
            user_histories[user_id].append({"role": "assistant", "content": reply})

            return reply

        except Exception as e:
            logger.error(f"Erro ao gerar resposta GPT: {e}")
            return "Desculpe, não consegui processar sua mensagem agora 😅"

    async def send_whatsapp_message(self, to: str, message: str):
        if not MAYTAPI_URL or not MAYTAPI_TOKEN:
            logger.error("❌ Configuração do Maytapi faltando.")
            return

        headers = {"Content-Type": "application/json", "x-maytapi-key": MAYTAPI_TOKEN}
        payload = {"to_number": to, "text": message, "type": "text"}

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(MAYTAPI_URL, headers=headers, json=payload)
                logger.info(f"💬 [BOT -> {to}]: {message}")
                return response.json()
            except Exception as e:
                logger.error(f"Erro ao enviar mensagem WhatsApp: {e}")
                return None

# Instancia o bot
bot = WhatsAppBotIntelligent()

# Rota principal (Webhook do WhatsApp)
@app.post("/")
async def webhook_handler(request: Request):
    data = await request.json()
    logger.info(f"📨 Dados recebidos do webhook: {data}")

    user = data.get("user", {})
    phone = user.get("phone")
    message_data = data.get("message", {})

    # Valida mensagem recebida
    if not phone or not message_data or message_data.get("fromMe"):
        logger.warning("⚠️ Dados insuficientes ou mensagem do próprio bot, ignorando.")
        return {"status": "ignored"}

    user_message = message_data.get("text")
    if not user_message:
        logger.warning("⚠️ Mensagem sem texto, ignorando.")
        return {"status": "ignored"}

    # Gera resposta com GPT
    reply = await bot.get_gpt_response(phone, user_message)

    # Simula delay humano (3s a 8s)
    delay = random.randint(3, 8)
    time.sleep(delay)

    # Envia resposta pelo WhatsApp
    await bot.send_whatsapp_message(phone, reply)

    return {"status": "ok", "reply": reply}
