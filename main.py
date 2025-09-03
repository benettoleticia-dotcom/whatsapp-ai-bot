import os
import asyncio
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

# Configurações fixas do Maytapi (baseadas nos logs)
MAYTAPI_PRODUCT_ID = "f38c3b76-29d1-4f85-ab4e-c3c911b7116c"
MAYTAPI_PHONE_ID = "107677" 
MAYTAPI_TOKEN = "c9510ef0-09e6-4780-bb6a-72b137811069"

# Inicializa cliente OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "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").strip()
if not OPENAI_API_KEY:
    logger.warning("⚠️ OPENAI_API_KEY não definida, respostas GPT não funcionarão!")
client = OpenAI(api_key=OPENAI_API_KEY)

# Armazena histórico por usuário
user_histories = {}

class WhatsAppBotIntelligent:
    def __init__(self):
        self.max_context_messages = 6
        
    async def get_gpt_response(self, user_id: str, user_message: str) -> str:
        try:
            if user_id not in user_histories:
                user_histories[user_id] = []

            user_histories[user_id].append({"role": "user", "content": user_message})
            user_histories[user_id] = user_histories[user_id][-self.max_context_messages:]

            system_prompt = {
                "role": "system",
                "content": (
                    "Você é Ana, uma atendente virtual sedutora e inteligente especializada em vendas. "
                    "Seja carinhosa mas provocante, use linguagem informal portuguesa (gatinho, amor, né, kkk). "
                    "Suas respostas devem ser naturais e envolventes, criando conexão emocional. "
                    "Sempre conduza a conversa sutilmente em direção à venda de conteúdo premium. "
                    "Use emojis com moderação (😘😏💋🔥). Seja transparente sobre preços quando perguntada. "
                    "Suas técnicas: 1) Crie rapport 2) Identifique interesse 3) Apresente valor 4) Feche venda."
                ),
            }

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[system_prompt] + user_histories[user_id],
                max_tokens=200,  # Reduzido para respostas mais concisas
                temperature=0.8,  # Mais criativa
            )

            reply = response.choices[0].message.content.strip()
            user_histories[user_id].append({"role": "assistant", "content": reply})
            
            logger.info(f"🤖 GPT gerou resposta: {reply[:100]}...")
            return reply

        except Exception as e:
            logger.error(f"Erro ao gerar resposta GPT: {e}")
            return "Oi gatinho! Tive um probleminha técnico aqui, pode mandar de novo? 😘"

    async def send_whatsapp_message(self, to: str, message: str):
        """Envia mensagem via Maytapi com URL e payload corretos"""
        
        # URL correta baseada nos logs recebidos
        url = f"https://api.maytapi.com/api/{MAYTAPI_PRODUCT_ID}/{MAYTAPI_PHONE_ID}/sendMessage"
        
        headers = {
            "Content-Type": "application/json", 
            "x-maytapi-key": MAYTAPI_TOKEN
        }
        
        # Limpa o número do telefone (remove @c.us se existir)
        clean_phone = to.replace("@c.us", "").replace("+", "").replace("-", "").replace(" ", "")
        
        payload = {
            "to_number": clean_phone,
            "type": "text",
            "message": message
        }
        
        logger.info(f"📤 Enviando para {clean_phone}: {message[:50]}...")
        logger.info(f"🔗 URL: {url}")
        logger.info(f"📋 Payload: {payload}")

        async with httpx.AsyncClient(timeout=30.0) as client_http:
            try:
                response = await client_http.post(url, headers=headers, json=payload)
                
                logger.info(f"📡 Status resposta Maytapi: {response.status_code}")
                logger.info(f"📡 Resposta completa: {response.text}")
                
                if response.status_code == 200:
                    logger.info(f"✅ Mensagem enviada com sucesso!")
                    return response.json()
                else:
                    logger.error(f"❌ Erro Maytapi: {response.status_code} - {response.text}")
                    return None
                    
            except Exception as e:
                logger.error(f"❌ Exceção ao enviar: {e}")
                return None

# Instancia o bot
bot = WhatsAppBotIntelligent()

@app.post("/webhook")
async def webhook_handler(request: Request):
    try:
        data = await request.json()
        logger.info(f"📨 Webhook recebido: {data}")

        user = data.get("user", {})
        phone = user.get("phone")
        user_name = user.get("name", "Cliente")
        message_data = data.get("message", {})

        # Verifica se tem dados suficientes
        if not phone or not message_data:
            logger.warning("⚠️ Dados insuficientes, ignorando.")
            return {"status": "ignored", "reason": "insufficient_data"}

        # Ignora mensagens próprias
        if message_data.get("fromMe", False):
            logger.info("📤 Mensagem própria, ignorando.")
            return {"status": "ignored", "reason": "own_message"}

        # Extrai texto da mensagem
        user_message = message_data.get("text")
        if not user_message or not user_message.strip():
            logger.warning("⚠️ Mensagem sem texto, ignorando.")
            return {"status": "ignored", "reason": "no_text"}

        logger.info(f"👤 {user_name} ({phone}): {user_message}")

        # Gera resposta da IA
        reply = await bot.get_gpt_response(phone, user_message)
        
        # Delay humano (async)
        delay = random.randint(2, 6)
        logger.info(f"⏰ Aguardando {delay}s para parecer mais humano...")
        await asyncio.sleep(delay)
        
        # Envia resposta
        result = await bot.send_whatsapp_message(phone, reply)
        
        if result:
            return {"status": "success", "reply": reply[:100], "sent": True}
        else:
            return {"status": "error", "reply": reply[:100], "sent": False}

    except Exception as e:
        logger.error(f"💥 Erro no webhook: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/")
async def root():
    return {
        "status": "online", 
        "message": "🤖 Atendente Virtual Ana funcionando!",
        "maytapi_configured": bool(MAYTAPI_TOKEN and MAYTAPI_PRODUCT_ID),
        "openai_configured": bool(OPENAI_API_KEY)
    }

@app.get("/test")
async def test_ia():
    """Endpoint para testar a IA"""
    try:
        response = await bot.get_gpt_response("test_user", "Oi tudo bem?")
        return {"status": "success", "response": response}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# Inicializa servidor
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    logger.info(f"🚀 Iniciando servidor na porta {port}")
    logger.info(f"🔑 OpenAI configurada: {'✅' if OPENAI_API_KEY else '❌'}")
    logger.info(f"📱 Maytapi configurada: {'✅' if MAYTAPI_TOKEN else '❌'}")
    uvicorn.run(app, host="0.0.0.0", port=port)
