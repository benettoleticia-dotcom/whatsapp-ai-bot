import os
import time
import random
import logging
from fastapi import FastAPI, Request
import httpx
from openai import OpenAI

# -------------------------
# Configuração de logs
# -------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

# -------------------------
# Inicializa FastAPI
# -------------------------
app = FastAPI()

# -------------------------
# Inicializa cliente OpenAI
# -------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
if not OPENAI_API_KEY:
    logger.warning("⚠️ OPENAI_API_KEY não definida, respostas GPT não funcionarão!")
client = OpenAI(api_key=OPENAI_API_KEY)

# -------------------------
# Configuração WhatsApp API (Maytapi)
# -------------------------
MAYTAPI_URL = os.getenv("MAYTAPI_URL", "").strip()
MAYTAPI_TOKEN = os.getenv("MAYTAPI_TOKEN", "").strip()
if not MAYTAPI_URL or not MAYTAPI_TOKEN:
    logger.warning("⚠️ MAYTAPI_URL ou MAYTAPI_TOKEN não configurados!")

# -------------------------
# Histórico por usuário
# -------------------------
user_histories = {}

# -------------------------
# Classe do Bot Inteligente
# -------------------------
class WhatsAppBotIntelligent:
    def __init__(self):
        self.max_context_messages = 6  # quantidade de mensagens no histórico

    async def get_gpt_response(self, user_id: str, user_message: str) -> str:
        try:
            if user_id not in user_histories:
                user_histories[user_id] = []

            user_histories[user_id].append({"role": "user", "content": user_message})
            user_histories[user_id] = user_histories[user_id][-self.max_context_messages:]

            system_prompt = {
                "role": "system",
                "content": (
                    "Você é um atendente simpático e humano. "
                    "Responda de forma natural, breve, sem parecer robótico. "
                    "Sempre leve a conversa em direção à venda de forma sutil e educada."
                ),
            }

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[system_prompt] + user_histories[user_id],
                max_tokens=300,
                temperature=0.7,
            )

            reply = response.choices[0].message.content.strip()
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

        async with httpx.AsyncClient() as client_http:
            try:
                response = await client_http.post(MAYTAPI_URL, headers=headers, json=payload)
                logger.info(f"💬 [BOT -> {to}]: {message}")
                return response.json()
            except Exception as e:
                logger.error(f"Erro ao enviar mensagem WhatsApp: {e}")
                return None

# -------------------------
# Instancia o bot
# -------------------------
bot = WhatsAppBotIntelligent()

# -------------------------
# Webhook do WhatsApp
# -------------------------
@app.post("/webhook")
async def webhook_handler(request: Request):
    data = await request.json()
    logger.info(f"📨 Webhook recebido: {data}")

    # Filtra mensagens de erro ou eventos que não são do usuário
    if data.get("type") != "message":
        logger.info(f"ℹ️ Webhook não é mensagem de usuário, ignorando: {data.get('type')}")
        return {"status": "ignored"}

    user = data.get("user", {})
    phone = user.get("phone")
    message_data = data.get("message", {})

    # Ignora mensagens do próprio bot ou dados insuficientes
    if not phone or not message_data or message_data.get("fromMe"):
        logger.warning("⚠️ Dados insuficientes ou mensagem do próprio bot, ignorando.")
        return {"status": "ignored"}

    user_message = message_data.get("text")
    if not user_message:
        logger.warning("⚠️ Mensagem sem texto, ignorando.")
        return {"status": "ignored"}

    # Gera resposta GPT
    reply = await bot.get_gpt_response(phone, user_message)

    # Delay humano antes de enviar
    delay = random.randint(5, 10)
    time.sleep(delay)

    # Envia mensagem
    await bot.send_whatsapp_message(phone, reply)

    return {"status": "ok", "reply": reply}

# -------------------------
# Rota root para teste
# -------------------------
@app.get("/")
async def root():
    return {"status": "ok", "message": "🚀 Bot WhatsApp rodando no Render"}

# -------------------------
# Inicializa Uvicorn com porta do Render
# -------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
