import os
import logging
import httpx
from fastapi import FastAPI, Request
from openai import OpenAI

# Configuração de logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

# Inicializa FastAPI
app = FastAPI()

# Variáveis de ambiente
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MAYTAPI_TOKEN = os.getenv("MAYTAPI_TOKEN")
MAYTAPI_BASE_URL = os.getenv("MAYTAPI_BASE_URL")  # Exemplo: https://api.maytapi.com/api/<product_id>/<phone_id>

# Configuração do cliente OpenAI
client = OpenAI(api_key=OPENAI_API_KEY)


# Função para gerar resposta com GPT
async def gerar_resposta(mensagem_usuario: str) -> str:
    try:
        resposta = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Você é um assistente educado e objetivo que responde mensagens de WhatsApp de forma clara e natural."},
                {"role": "user", "content": mensagem_usuario}
            ],
            max_tokens=300,
            temperature=0.7
        )
        conteudo = resposta.choices[0].message.content.strip()
        return conteudo
    except Exception as e:
        logger.error(f"Erro ao gerar resposta GPT: {e}")
        return "Desculpe, não consegui processar sua mensagem agora 😅"


# Função para enviar mensagem pelo Maytapi
async def enviar_mensagem(numero: str, texto: str):
    try:
        url = f"{MAYTAPI_BASE_URL}/sendMessage"
        payload = {
            "to_number": numero,
            "type": "text",
            "text": texto,
        }
        headers = {"x-maytapi-key": MAYTAPI_TOKEN}

        async with httpx.AsyncClient() as client_http:
            response = await client_http.post(url, json=payload, headers=headers)

        if response.status_code == 200:
            logger.info(f"💬 [BOT -> {numero}]: {texto}")
        else:
            logger.error(f"Erro ao enviar mensagem WhatsApp: {response.text}")

    except Exception as e:
        logger.error(f"Erro inesperado ao enviar mensagem: {e}")


# Rota raiz
@app.get("/")
async def root():
    return {"status": "ok", "message": "🤖 Bot WhatsApp rodando com Maytapi + OpenAI"}


# Rota Webhook
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    logger.info(f"📨 Webhook recebido: {data}")

    try:
        # Valida se é mensagem do usuário
        if data.get("type") != "message":
            logger.info(f"ℹ️ Webhook não é mensagem de usuário, ignorando: {data.get('type')}")
            return {"status": "ignored"}

        msg = data.get("message", {})
        texto_usuario = msg.get("text")
        numero = data.get("user", {}).get("id")

        if not texto_usuario or not numero:
            logger.warning("⚠️ Mensagem vazia ou número inválido.")
            return {"status": "ignored"}

        # Gera resposta com GPT
        resposta = await gerar_resposta(texto_usuario)

        # Envia resposta pelo Maytapi
        await enviar_mensagem(numero, resposta)

        return {"status": "success"}

    except Exception as e:
        logger.error(f"Erro ao processar webhook: {e}")
        return {"status": "error", "detail": str(e)}
