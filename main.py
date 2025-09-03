import os
import logging
import requests
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from openai import OpenAI

# Configuração de logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

# Inicializa o FastAPI
app = FastAPI()

# Carrega variáveis de ambiente
MAYTAPI_TOKEN = os.getenv("MAYTAPI_TOKEN")
MAYTAPI_BASE_URL = os.getenv("MAYTAPI_BASE_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not MAYTAPI_TOKEN or not MAYTAPI_BASE_URL or not OPENAI_API_KEY:
    logger.error("⚠️ Variáveis de ambiente ausentes. Verifique no Render!")
    raise Exception("Variáveis de ambiente não configuradas corretamente.")

# Inicializa o cliente OpenAI
client = OpenAI(api_key=OPENAI_API_KEY)


# Função para enviar mensagem pelo WhatsApp via Maytapi
def send_whatsapp_message(to: str, message: str):
    try:
        payload = {
            "to_number": to,
            "type": "text",
            "message": message
        }
        headers = {
            "x-maytapi-key": MAYTAPI_TOKEN,
            "Content-Type": "application/json"
        }

        response = requests.post(MAYTAPI_BASE_URL, json=payload, headers=headers)

        if response.status_code == 200:
            logger.info(f"💬 [BOT -> {to}]: {message}")
        else:
            logger.error(f"Erro ao enviar mensagem WhatsApp: {response.text}")
    except Exception as e:
        logger.error(f"Erro na função send_whatsapp_message: {e}")


# Função para gerar resposta com OpenAI
def generate_openai_response(user_message: str) -> str:
    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Você é um assistente útil que responde de forma simpática e clara."},
                {"role": "user", "content": user_message}
            ],
            temperature=0.7,
            max_tokens=500
        )
        return completion.choices[0].message.content
    except Exception as e:
        logger.error(f"Erro ao gerar resposta com OpenAI: {e}")
        return "Desculpe, ocorreu um erro ao processar sua mensagem. 😔"


# Endpoint inicial para teste
@app.get("/")
async def root():
    return {"status": "ok", "message": "🚀 Bot do WhatsApp está rodando!"}


# Webhook para receber mensagens do WhatsApp
@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
        logger.info(f"📨 Webhook recebido: {data}")

        # Extrai informações da mensagem
        message = data.get("message", {})
        message_type = message.get("type")
        user = data.get("user", {})
        user_id = user.get("id")
        user_name = user.get("name")

        if not user_id or not message_type:
            logger.warning("⚠️ Mensagem vazia ou número inválido.")
            return JSONResponse(content={"status": "ignored"})

        # Só processa mensagens de texto
        if message_type == "text":
            user_text = message.get("text", "").strip()

            if not user_text:
                logger.warning("⚠️ Mensagem de texto vazia ignorada.")
                return JSONResponse(content={"status": "ignored"})

            logger.info(f"👤 {user_name} ({user_id}): {user_text}")

            # Gera resposta com GPT
            bot_reply = generate_openai_response(user_text)

            # Envia resposta pelo WhatsApp
            send_whatsapp_message(user_id, bot_reply)

        else:
            logger.info(f"📷 Mensagem ignorada (tipo: {message_type})")

        return JSONResponse(content={"status": "success"})

    except Exception as e:
        logger.error(f"Erro ao processar mensagem: {e}")
        return JSONResponse(content={"status": "error", "detail": str(e)})

