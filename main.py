import os
import httpx
from fastapi import FastAPI, Request
import logging
import openai

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

app = FastAPI()

# Pegando variáveis de ambiente
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MAYTAPI_TOKEN = os.getenv("MAYTAPI_TOKEN")
MAYTAPI_BASE_URL = os.getenv("MAYTAPI_BASE_URL")

openai.api_key = OPENAI_API_KEY

@app.post("/webhook")
async def webhook(req: Request):
    data = await req.json()
    logger.info(f"📨 Webhook recebido: {data}")

    message = data.get("message", {})
    user = data.get("user", {})
    msg_type = message.get("type")
    text = message.get("text", "")
    conversation = data.get("conversation")
    reply_url = data.get("reply", MAYTAPI_BASE_URL)

    # Ignora mensagens sem texto ou de nós mesmos
    if not message or message.get("fromMe", False):
        logger.warning("⚠️ Mensagem do próprio bot ou vazia, ignorando.")
        return {"status": "ignored"}

    # Limpeza de caracteres invisíveis
    text = text.replace("\n", " ").strip()

    try:
        if msg_type == "text":
            # Gera resposta GPT
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[{"role": "user", "content": text}],
                max_tokens=200
            )
            reply_text = response.choices[0].message.content.strip()

        elif msg_type == "image":
            caption = message.get("caption", "")
            caption = caption.replace("\n", " ").strip()
            reply_text = f"Recebi sua imagem! {caption}" if caption else "Recebi sua imagem!"

        else:
            reply_text = "Desculpe, não consigo processar este tipo de mensagem no momento."

        # Envia resposta via Maytapi
        headers = {"Authorization": f"Bearer {MAYTAPI_TOKEN}"}
        payload = {"text": reply_text, "to_number": conversation, "type": "text"}
        async with httpx.AsyncClient() as client:
            r = await client.post(reply_url, headers=headers, json=payload)
            r.raise_for_status()

        logger.info(f"💬 [BOT -> {conversation}]: {reply_text}")

    except Exception as e:
        logger.error(f"Erro ao processar mensagem: {e}")
        reply_text = "Desculpe, não consegui processar sua mensagem agora 😅"

    return {"status": "ok"}
