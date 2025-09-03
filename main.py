import os
import asyncio
import random
import logging
import json
import re
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import httpx
from openai import OpenAI

# Configuração de logging compatível com Render
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ana_bot")

app = FastAPI()

# Configurações (usando variáveis de ambiente do Render)
MAYTAPI_PRODUCT_ID = os.getenv("MAYTAPI_PRODUCT_ID", "f38c3b76-29d1-4f85-ab4e-c3c911b7116c")
MAYTAPI_PHONE_ID = os.getenv("MAYTAPI_PHONE_ID", "107677")
MAYTAPI_TOKEN = os.getenv("MAYTAPI_TOKEN", "c9510ef0-09e6-4780-bb6a-72b137811069")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "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")

# Inicializa OpenAI
try:
    client = OpenAI(api_key=OPENAI_API_KEY)
    logger.info("✅ OpenAI client inicializado")
except Exception as e:
    logger.error(f"❌ Erro ao inicializar OpenAI: {e}")

# Sistema de memória SIMPLIFICADO (sem SQLite para evitar problemas no Render)
class SimpleMemorySystem:
    def __init__(self):
        self.user_data = {}  # Memória em RAM (resetará com restart, mas funcional)
        self.conversations = {}
        logger.info("✅ Sistema de memória simples inicializado")
    
    def get_user_profile(self, user_id):
        return self.user_data.get(user_id, {
            'user_id': user_id,
            'name': '',
            'location': '',
            'city': '',
            'messages_count': 0,
            'last_interaction': datetime.now(),
            'converted': False,
            'conversion_stage': 'initial'
        })
    
    def update_user_profile(self, user_id, **kwargs):
        if user_id not in self.user_data:
            self.user_data[user_id] = self.get_user_profile(user_id)
        
        # Atualiza campos
        for key, value in kwargs.items():
            if value is not None:
                self.user_data[user_id][key] = value
        
        self.user_data[user_id]['last_interaction'] = datetime.now()
        logger.info(f"👤 Perfil atualizado: {user_id}")
    
    def log_conversation(self, user_id, user_message, ai_response, message_type, stage):
        if user_id not in self.conversations:
            self.conversations[user_id] = []
        
        self.conversations[user_id].append({
            'user_message': user_message,
            'ai_response': ai_response,
            'message_type': message_type,
            'stage': stage,
            'timestamp': datetime.now()
        })
        
        # Mantém apenas últimas 50 conversas por usuário (economia de memória)
        if len(self.conversations[user_id]) > 50:
            self.conversations[user_id] = self.conversations[user_id][-50:]

# Instância global da memória
memory = SimpleMemorySystem()
user_histories = {}  # Cache das conversas

class RenderCompatibleBot:
    def __init__(self):
        self.max_context = 8
        
        # Cidades portuguesas
        self.portuguese_cities = {
            'lisboa': 'Lisboa', 'porto': 'Porto', 'coimbra': 'Coimbra', 'braga': 'Braga',
            'aveiro': 'Aveiro', 'faro': 'Faro', 'cascais': 'Cascais', 'felgueiras': 'Felgueiras',
            'leiria': 'Leiria', 'setubal': 'Setúbal', 'vila nova de gaia': 'Vila Nova de Gaia'
        }
        
        logger.info("✅ Bot inicializado com compatibilidade Render")
    
    def get_current_time_period(self):
        """Determina período do dia"""
        current_hour = datetime.now().hour
        
        if 6 <= current_hour < 12:
            return 'morning'
        elif 12 <= current_hour < 18:
            return 'afternoon'  
        elif 18 <= current_hour < 22:
            return 'evening'
        else:
            return 'night'
    
    def extract_location_info(self, message):
        """Extrai localização"""
        message_lower = message.lower()
        
        if 'portugal' in message_lower:
            return {'type': 'country', 'location': 'Portugal', 'city': None}
        
        for city_key, city_name in self.portuguese_cities.items():
            if city_key in message_lower:
                return {'type': 'city', 'location': city_name, 'city': city_name}
        
        return None
    
    def analyze_conversation_context(self, user_id, message):
        """Análise contextual simplificada"""
        profile = memory.get_user_profile(user_id)
        history = user_histories.get(user_id, [])
        
        context = {
            'already_asked_location': False,
            'knows_location': bool(profile.get('city')),
            'location_info': self.extract_location_info(message),
            'messages_count': len(history),
            'stage': profile.get('conversion_stage', 'initial'),
            'time_period': self.get_current_time_period()
        }
        
        # Verifica se já perguntou localização
        for msg in history:
            if 'cidade' in msg.get('content', '').lower():
                context['already_asked_location'] = True
                break
        
        return context
    
    def determine_conversion_stage(self, user_id, message, context):
        """Determina estágio da conversa"""
        message_lower = message.lower()
        
        interest_keywords = ['interesse', 'quero', 'comprar', 'valores', 'preço', 'quanto', 'cliente', 'plataforma']
        service_keywords = ['sexo', 'sair', 'encontrar', 'transar', 'serviços']
        closing_keywords = ['sim', 'vamos', 'ok', 'feito', 'pago']
        
        if any(keyword in message_lower for keyword in closing_keywords) and context['stage'] in ['pricing', 'explanation']:
            return 'closing'
        elif any(keyword in message_lower for keyword in interest_keywords):
            return 'pricing'
        elif any(keyword in message_lower for keyword in service_keywords):
            return 'explanation'
        elif context['messages_count'] <= 2:
            return 'initial'
        else:
            return 'qualification'
    
    def build_natural_prompt(self, user_id, message, context, message_type):
        """Prompt otimizado para Render"""
        
        profile = memory.get_user_profile(user_id)
        user_name = profile.get('name', 'cliente') if profile else 'cliente'
        user_location = profile.get('city') if profile else None
        
        ai_location = user_location if user_location else "Porto"
        if context['location_info'] and context['location_info']['type'] == 'city':
            ai_location = context['location_info']['city']
        
        # Prompt mais conciso para evitar problemas de token no Render
        time_mood = {
            'morning': 'energética e carinhosa ☀️',
            'afternoon': 'relaxada e conversadora 😊', 
            'evening': 'sedutora e direta 🌙',
            'night': 'íntima e provocante 😘'
        }
        
        mood = time_mood.get(context['time_period'], 'natural')
        
        # Contexto para fotos
        photo_context = ""
        if message_type in ["image", "photo"]:
            photo_context = "Cliente enviou FOTO! Reage com entusiasmo: 'Que giro! 😍' ou similar."
        
        prompt = f"""És Ana, portuguesa de {ai_location}. Trabalhas com conteúdo adulto.

AGORA: {mood}
SITUAÇÃO: Cliente {user_name} | Msg #{context['messages_count']+1} | {context['stage']}
{photo_context}

COMO RESPONDER:
• Português de Portugal natural
• Máximo 2 linhas por mensagem  
• Varia respostas, nunca repete
• Usa emojis quando apropriado

REGRAS:
→ Primeira vez + não sabe cidade = "De onde me falas?"
→ Pergunta serviços = "Só saio com meus clientes das plataformas"  
→ Interesse preço = "€19,90 pagamento único, baratinho"
→ Comprar = https://buy.stripe.com/14k4iR16VdNk43mfZ5

EXEMPLOS:
- "Oi! De onde me falas?" (primeira vez)
- "Que giro essa foto! 😍" (recebeu foto)
- "€19,90, bem baratinho para selecionar quem quer mesmo"
- "Kkk não dá para sair com qualquer um né 😉"

Responde natural como WhatsApp real:"""
        
        return prompt

    async def split_message(self, message):
        """Quebra mensagens longas"""
        if len(message) <= 100:
            return [message]
        
        # Quebra simples por frases
        sentences = re.split(r'[.!?]\s+', message)
        messages = []
        current = ""
        
        for sentence in sentences:
            if len(current + sentence) <= 100:
                current += sentence + ". "
            else:
                if current:
                    messages.append(current.strip())
                current = sentence + ". "
        
        if current:
            messages.append(current.strip())
        
        return messages if messages else [message]

    async def get_natural_response(self, user_id: str, user_message: str, message_type: str = "text"):
        """Gera resposta natural (compatível com Render)"""
        try:
            logger.info(f"🤖 Processando: {user_id[:8]}... | {message_type} | {user_message[:50]}...")
            
            # Analisa contexto
            context = self.analyze_conversation_context(user_id, user_message)
            
            # Determina estágio
            stage = self.determine_conversion_stage(user_id, user_message, context)
            
            # Atualiza histórico
            if user_id not in user_histories:
                user_histories[user_id] = []
            
            user_histories[user_id].append({"role": "user", "content": user_message})
            user_histories[user_id] = user_histories[user_id][-self.max_context:]
            
            # Atualiza localização se detectada
            if context['location_info']:
                location_data = context['location_info']
                if location_data['type'] == 'city':
                    memory.update_user_profile(
                        user_id, 
                        city=location_data['city'],
                        location=location_data['location'],
                        conversion_stage=stage,
                        messages_count=len(user_histories[user_id])
                    )
            
            # Constrói prompt
            system_prompt = {
                "role": "system",
                "content": self.build_natural_prompt(user_id, user_message, context, message_type)
            }
            
            # Processa mensagem baseada no tipo
            processed_message = user_message
            if message_type == "audio":
                processed_message = f"[Áudio] {user_message}"
            elif message_type in ["image", "photo"]:
                if user_message.strip():
                    processed_message = f"[Foto com legenda: {user_message}]"
                else:
                    processed_message = "[Enviou uma foto]"
            elif message_type == "video":
                processed_message = f"[Vídeo] {user_message if user_message.strip() else 'sem legenda'}"
            
            # Gera resposta com tratamento de erro
            try:
                response = client.chat.completions.create(
                    model="gpt-4o-mini",  # Modelo mais estável para Render
                    messages=[system_prompt] + user_histories[user_id],
                    temperature=0.9,
                    max_tokens=300,
                    frequency_penalty=0.6,
                    presence_penalty=0.4
                )
                
                reply = response.choices[0].message.content.strip()
                
            except Exception as e:
                logger.error(f"❌ Erro OpenAI: {e}")
                # Fallback para erro de API
                replies = [
                    "Oi! Tive um probleminha técnico 😅",
                    "Desculpa, pode repetir?", 
                    "Falha na conexão, tenta de novo"
                ]
                reply = random.choice(replies)
            
            # Quebra mensagem se necessário
            messages = await self.split_message(reply)
            
            # Adiciona ao histórico
            user_histories[user_id].append({"role": "assistant", "content": reply})
            
            # Salva conversa
            memory.log_conversation(user_id, user_message, reply, message_type, stage)
            
            # Log de conversão
            if any("stripe.com" in msg for msg in messages):
                logger.info(f"💰 CONVERSÃO: Link enviado para {user_id[:8]}...")
            
            logger.info(f"✅ Resposta gerada: {len(messages)} mensagens")
            return messages

        except Exception as e:
            logger.error(f"💥 Erro geral: {e}")
            return ["Oi querido, tive um problema. Podes tentar de novo? 😊"]

    async def send_whatsapp_message(self, to: str, message: str):
        """Envia mensagem via Maytapi (com tratamento de erro)"""
        try:
            url = f"https://api.maytapi.com/api/{MAYTAPI_PRODUCT_ID}/{MAYTAPI_PHONE_ID}/sendMessage"
            
            headers = {
                "Content-Type": "application/json", 
                "x-maytapi-key": MAYTAPI_TOKEN
            }
            
            clean_phone = to.replace("@c.us", "").replace("+", "").replace("-", "").replace(" ", "")
            
            payload = {
                "to_number": clean_phone,
                "type": "text",
                "message": message
            }

            async with httpx.AsyncClient(timeout=30.0) as client_http:
                response = await client_http.post(url, headers=headers, json=payload)
                
                if response.status_code == 200:
                    logger.info(f"✅ Enviado: {message[:40]}...")
                    return True
                else:
                    logger.error(f"❌ Erro Maytapi: {response.status_code}")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ Exceção envio: {e}")
            return False

    async def send_multiple_messages(self, phone: str, messages: list):
        """Envia múltiplas mensagens com delays"""
        for i, message in enumerate(messages):
            if i > 0:
                delay = random.uniform(2, 6)  # Delay entre mensagens
                await asyncio.sleep(delay)
            
            success = await self.send_whatsapp_message(phone, message)
            if not success:
                logger.error(f"❌ Falha na mensagem {i+1}/{len(messages)}")
                break
            
            await asyncio.sleep(1)  # Pausa mínima entre envios

    async def transcribe_audio(self, audio_url):
        """Transcreve áudio (com fallback)"""
        try:
            async with httpx.AsyncClient(timeout=60.0) as client_http:
                audio_response = await client_http.get(audio_url)
                if audio_response.status_code == 200:
                    with open("temp_audio.ogg", "wb") as f:
                        f.write(audio_response.content)
                    
                    with open("temp_audio.ogg", "rb") as audio_file:
                        transcription = client.audio.transcriptions.create(
                            model="whisper-1",
                            file=audio_file
                        )
                    
                    os.remove("temp_audio.ogg")
                    return transcription.text
            
            return "Não consegui processar o áudio"
            
        except Exception as e:
            logger.error(f"❌ Erro transcrição: {e}")
            return "Áudio recebido mas não consegui ouvir"

# Instância global do bot
bot = RenderCompatibleBot()

@app.post("/webhook")
async def webhook_handler(request: Request):
    """Webhook handler compatível com Render"""
    try:
        # Log da requisição
        logger.info("📨 Webhook recebido")
        
        data = await request.json()
        
        user = data.get("user", {})
        phone = user.get("phone")
        user_name = user.get("name", "")
        message_data = data.get("message", {})

        # Validações
        if not phone or not message_data or message_data.get("fromMe", False):
            logger.info("⏭️ Mensagem ignorada")
            return {"status": "ignored"}

        message_type = message_data.get("type", "text")
        user_message = ""
        
        # Processa diferentes tipos
        if message_type == "text":
            user_message = message_data.get("text", "")
        elif message_type == "audio":
            audio_url = message_data.get("url", "")
            if audio_url:
                user_message = await bot.transcribe_audio(audio_url)
                logger.info(f"🎵 Áudio: {user_message[:50]}...")
            else:
                user_message = "Recebi teu áudio"
        elif message_type in ["image", "video", "photo"]:
            caption = message_data.get("caption", "")
            user_message = caption
            logger.info(f"📸 {message_type.capitalize()}: {caption or 'sem legenda'}")
        else:
            logger.info(f"📋 Tipo não suportado: {message_type}")
            return {"status": "ignored"}

        # Log principal
        logger.info(f"👤 {user_name[:20]} | {phone[-8:]} | [{message_type}] {user_message[:100]}")

        # Delay inicial
        initial_delay = random.randint(3, 10)
        logger.info(f"⏰ Delay: {initial_delay}s")
        await asyncio.sleep(initial_delay)
        
        # Gera resposta
        messages = await bot.get_natural_response(phone, user_message, message_type)
        
        # Envia mensagens
        await bot.send_multiple_messages(phone, messages)
        
        logger.info(f"✅ Conversa processada com sucesso")
        return {"status": "success", "messages_sent": len(messages)}

    except Exception as e:
        logger.error(f"💥 ERRO CRÍTICO: {e}")
        return {"status": "error", "error": str(e)}

@app.get("/")
async def health_check():
    """Health check para Render"""
    try:
        # Testa OpenAI
        test_response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "test"}],
            max_tokens=5
        )
        openai_status = "✅ OK"
    except:
        openai_status = "❌ ERRO"
    
    # Stats básicas
    total_users = len(memory.user_data)
    total_conversations = sum(len(convs) for convs in memory.conversations.values())
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>🤖 Ana Bot - Render Deploy</title>
        <meta charset="utf-8">
        <style>
            body {{font-family: Arial; margin: 30px; background: #f0f8ff;}}
            .card {{background: white; padding: 20px; margin: 15px 0; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);}}
            .status {{font-size: 18px; margin: 10px 0;}}
            .success {{color: #28a745;}}
            .error {{color: #dc3545;}}
            .info {{color: #17a2b8;}}
        </style>
    </head>
    <body>
        <h1>🤖 Ana Bot - Status Deploy</h1>
        
        <div class="card">
            <h2>📊 Status do Sistema</h2>
            <div class="status">OpenAI API: <span class="{('success' if '✅' in openai_status else 'error')}">{openai_status}</span></div>
            <div class="status">Memória: <span class="success">✅ Ativa</span></div>
            <div class="status">Webhook: <span class="success">✅ Funcional</span></div>
            <div class="status">Deploy: <span class="success">✅ Render OK</span></div>
        </div>
        
        <div class="card">
            <h2>📈 Estatísticas</h2>
            <p><strong>Usuários:</strong> {total_users}</p>
            <p><strong>Conversas:</strong> {total_conversations}</p>
            <p><strong>Tempo Online:</strong> {datetime.now().strftime('%H:%M:%S')}</p>
            <p><strong>Servidor:</strong> Render Cloud</p>
        </div>
        
        <div class="card">
            <h2>⚙️ Configurações</h2>
            <p>✅ Memória em RAM (não precisa SQLite)</p>
            <p>✅ Logs detalhados</p>
            <p>✅ Tratamento de erros</p>
            <p>✅ Timeouts configurados</p>
            <p>✅ Fallbacks implementados</p>
        </div>
        
        <div class="card">
            <h2>🎯 Funcionalidades</h2>
            <p>🤖 Respostas naturais GPT-4</p>
            <p>📸 Suporte a fotos e vídeos</p>
            <p>🎵 Transcrição de áudio</p>
            <p>💬 Múltiplas mensagens</p>
            <p>⏰ Delays humanos</p>
            <p>💰 Sistema de conversão</p>
        </div>
    </body>
    </html>
    """
    
    return HTMLResponse(html)

@app.get("/health")
async def health():
    """Health endpoint simples para Render"""
    return {"status": "healthy", "timestamp": datetime.now()}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    logger.info(f"🚀 Ana Bot iniciando na porta {port}")
    logger.info("✅ Versão compatível com Render")
    logger.info("✅ Memória em RAM")
    logger.info("✅ Tratamento de erros robusto") 
    uvicorn.run(app, host="0.0.0.0", port=port)
