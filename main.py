import os
import asyncio
import random
import logging
import sqlite3
import json
import re
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import httpx
from openai import OpenAI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

app = FastAPI()

# Configurações
MAYTAPI_PRODUCT_ID = "f38c3b76-29d1-4f85-ab4e-c3c911b7116c"
MAYTAPI_PHONE_ID = "107677" 
MAYTAPI_TOKEN = "c9510ef0-09e6-4780-bb6a-72b137811069"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "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").strip()

client = OpenAI(api_key=OPENAI_API_KEY)

# Base de dados inteligente
class SmartDatabase:
    def __init__(self):
        self.conn = sqlite3.connect('ana_conversations.db', check_same_thread=False)
        self.init_tables()
    
    def init_tables(self):
        cursor = self.conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id TEXT PRIMARY KEY,
                name TEXT,
                location TEXT,
                city TEXT,
                messages_count INTEGER DEFAULT 0,
                last_interaction DATETIME,
                converted BOOLEAN DEFAULT FALSE,
                conversion_stage TEXT DEFAULT 'initial'
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                user_message TEXT,
                ai_response TEXT,
                message_type TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                conversion_stage TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                amount REAL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        self.conn.commit()
    
    def get_user_profile(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM user_profiles WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        
        if result:
            return {
                'user_id': result[0],
                'name': result[1],
                'location': result[2], 
                'city': result[3],
                'messages_count': result[4],
                'last_interaction': result[5],
                'converted': result[6],
                'conversion_stage': result[7]
            }
        return None
    
    def update_user_profile(self, user_id, **kwargs):
        cursor = self.conn.cursor()
        
        # Cria ou atualiza perfil
        cursor.execute('''
            INSERT OR REPLACE INTO user_profiles 
            (user_id, name, location, city, messages_count, last_interaction, converted, conversion_stage)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            kwargs.get('name'),
            kwargs.get('location'),
            kwargs.get('city'),
            kwargs.get('messages_count', 1),
            datetime.now(),
            kwargs.get('converted', False),
            kwargs.get('conversion_stage', 'initial')
        ))
        
        self.conn.commit()
    
    def log_conversation(self, user_id, user_message, ai_response, message_type, stage):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO conversations (user_id, user_message, ai_response, message_type, conversion_stage)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, user_message, ai_response, message_type, stage))
        self.conn.commit()

db = SmartDatabase()
user_histories = {}

class NaturalSalesBot:
    def __init__(self):
        self.max_context = 8
        
        # Cidades portuguesas para reconhecimento inteligente
        self.portuguese_cities = {
            'lisboa': 'Lisboa', 'porto': 'Porto', 'coimbra': 'Coimbra', 'braga': 'Braga',
            'aveiro': 'Aveiro', 'faro': 'Faro', 'cascais': 'Cascais', 'felgueiras': 'Felgueiras',
            'leiria': 'Leiria', 'setubal': 'Setúbal', 'vila nova de gaia': 'Vila Nova de Gaia',
            'alfama': 'Alfama', 'ribeira': 'Ribeira'
        }
    
    def extract_location_info(self, message):
        """Extrai informação de localização de forma inteligente"""
        message_lower = message.lower()
        
        # Detecta se mencionou Portugal (país)
        if 'portugal' in message_lower:
            return {'type': 'country', 'location': 'Portugal', 'city': None}
        
        # Procura cidades específicas
        for city_key, city_name in self.portuguese_cities.items():
            if city_key in message_lower:
                return {'type': 'city', 'location': city_name, 'city': city_name}
        
        return None
    
    def analyze_conversation_context(self, user_id, message):
        """Analisa contexto da conversa para evitar repetições"""
        profile = db.get_user_profile(user_id)
        history = user_histories.get(user_id, [])
        
        context = {
            'already_asked_location': False,
            'knows_location': False,
            'location_info': None,
            'messages_count': len(history),
            'stage': 'initial'
        }
        
        if profile:
            context['knows_location'] = bool(profile.get('city'))
            context['stage'] = profile.get('conversion_stage', 'initial')
        
        # Verifica se já perguntou localização nesta conversa
        for msg in history:
            if 'cidade' in msg.get('content', '').lower():
                context['already_asked_location'] = True
                break
        
        # Extrai informação de localização da mensagem atual
        location_info = self.extract_location_info(message)
        if location_info:
            context['location_info'] = location_info
            
        return context
    
    def determine_conversion_stage(self, user_id, message, context):
        """Determina estágio da conversa de forma inteligente"""
        message_lower = message.lower()
        
        # Palavras-chave por estágio
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
    
    def build_natural_prompt(self, user_id, message, context):
        """Constrói prompt natural baseado no contexto"""
        
        # Informações do usuário
        profile = db.get_user_profile(user_id)
        user_name = profile.get('name', 'cliente') if profile else 'cliente'
        user_location = profile.get('city') if profile else None
        
        # Localização da IA (sempre mesma cidade que o cliente)
        ai_location = user_location if user_location else "Porto"
        if context['location_info'] and context['location_info']['type'] == 'city':
            ai_location = context['location_info']['city']
        
        prompt = f"""
Você é uma mulher portuguesa real chamada Ana, que trabalha com conteúdo adulto e encontros presenciais.

PERSONALIDADE:
- Natural e espontânea como uma pessoa real
- Direta mas simpática
- Usa português de Portugal natural
- Não repete perguntas já feitas
- Varia suas respostas

LOCALIZAÇÃO: Você mora em {ai_location} (mesma cidade do cliente)

CONTEXTO ATUAL:
- Cliente: {user_name}
- Localização conhecida: {user_location or 'Não'}
- Mensagens trocadas: {context['messages_count']}
- Já perguntou cidade: {context['already_asked_location']}
- Estágio: {context['stage']}

DIRETRIZES DE CONVERSA:

1. ABERTURA: Se for primeira interação e não sabe a cidade, pergunte de onde fala
2. QUALIFICAÇÃO: Faça perguntas naturais sobre o que a pessoa busca
3. EXPLICAÇÃO: Quando perguntarem sobre serviços, explique que só sai com clientes das plataformas
4. PREÇO: Quando interessados, apresente €19,90 sem enrolação
5. FECHAMENTO: Envie link quando confirmarem interesse

REGRAS IMPORTANTES:
- NÃO repita perguntas já feitas
- Se disser "Portugal", responda como país, não cidade
- Para previews: "é só abrir o link que lá tem uma foto"
- Seja concisa (máximo 2 linhas por resposta)
- Use "kkk" ocasionalmente para naturalidade
- Delay natural entre respostas

TÉCNICAS DE VENDA (use naturalmente):
- "Só saio com meus clientes"
- "€19,90 - é baratinho para selecionar quem quer mesmo"
- "Não dá para sair com qualquer um"

LINKS:
- Pagamento: https://buy.stripe.com/14k4iR16VdNk43mfZ5
- Sempre mencione que é pagamento único

Responda de forma natural e humana, como se fosse uma conversa real.
"""
        
        return prompt

    async def get_natural_response(self, user_id: str, user_message: str, message_type: str = "text") -> str:
        try:
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
                    db.update_user_profile(
                        user_id, 
                        city=location_data['city'],
                        location=location_data['location'],
                        conversion_stage=stage,
                        messages_count=len(user_histories[user_id])
                    )
            
            # Constrói prompt natural
            system_prompt = {
                "role": "system",
                "content": self.build_natural_prompt(user_id, user_message, context)
            }
            
            # Trata mensagens de áudio
            if message_type == "audio":
                user_message = f"[Cliente enviou áudio] {user_message}"
            
            # Gera resposta mais criativa e natural
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[system_prompt] + user_histories[user_id],
                max_tokens=120,
                temperature=0.9,  # Mais criativa
                frequency_penalty=0.5,  # Evita repetições
                presence_penalty=0.3   # Mais variada
            )

            reply = response.choices[0].message.content.strip()
            user_histories[user_id].append({"role": "assistant", "content": reply})
            
            # Salva conversa
            db.log_conversation(user_id, user_message, reply, message_type, stage)
            
            # Detecta tentativa de conversão
            if "stripe.com" in reply:
                logger.info(f"💰 Link de venda enviado para {user_id}")
                # Agenda verificação de conversão
                asyncio.create_task(self.track_conversion(user_id))
            
            logger.info(f"🤖 [{stage}] {user_id}: {reply[:60]}...")
            return reply

        except Exception as e:
            logger.error(f"Erro GPT: {e}")
            return "Oi, tive um probleminha aqui. Pode mandar de novo?"
    
    async def track_conversion(self, user_id):
        """Rastreia possível conversão"""
        await asyncio.sleep(300)  # 5 minutos depois
        # Aqui você pode implementar verificação automática via Stripe webhook
        pass

    async def send_whatsapp_message(self, to: str, message: str):
        """Envia mensagem via Maytapi"""
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
            try:
                response = await client_http.post(url, headers=headers, json=payload)
                
                if response.status_code == 200:
                    logger.info(f"✅ Enviado: {message[:40]}...")
                    return True
                else:
                    logger.error(f"❌ Erro: {response.status_code}")
                    return False
                    
            except Exception as e:
                logger.error(f"❌ Exceção: {e}")
                return False

    async def transcribe_audio(self, audio_url):
        """Transcreve áudio usando Whisper da OpenAI"""
        try:
            # Baixa o áudio
            async with httpx.AsyncClient() as client_http:
                audio_response = await client_http.get(audio_url)
                if audio_response.status_code == 200:
                    # Salva temporariamente
                    with open("temp_audio.ogg", "wb") as f:
                        f.write(audio_response.content)
                    
                    # Transcreve com Whisper
                    with open("temp_audio.ogg", "rb") as audio_file:
                        transcription = client.audio.transcriptions.create(
                            model="whisper-1",
                            file=audio_file
                        )
                    
                    # Remove arquivo temporário
                    os.remove("temp_audio.ogg")
                    
                    return transcription.text
            
            return "Não consegui ouvir o áudio"
            
        except Exception as e:
            logger.error(f"Erro transcrição: {e}")
            return "Não consegui processar o áudio"

# Instancia bot
bot = NaturalSalesBot()

@app.post("/webhook")
async def webhook_handler(request: Request):
    try:
        data = await request.json()
        
        user = data.get("user", {})
        phone = user.get("phone")
        user_name = user.get("name", "")
        message_data = data.get("message", {})

        if not phone or not message_data or message_data.get("fromMe", False):
            return {"status": "ignored"}

        message_type = message_data.get("type", "text")
        user_message = ""
        
        # Processa diferentes tipos de mensagem
        if message_type == "text":
            user_message = message_data.get("text", "")
        elif message_type == "audio":
            audio_url = message_data.get("url", "")
            if audio_url:
                user_message = await bot.transcribe_audio(audio_url)
                logger.info(f"🎵 Áudio transcrito: {user_message}")
            else:
                user_message = "Recebi seu áudio"
        elif message_type in ["image", "video"]:
            caption = message_data.get("caption", "")
            if caption:
                user_message = caption
            else:
                user_message = f"Recebi sua {message_type}"
        else:
            return {"status": "ignored"}

        if not user_message.strip():
            return {"status": "ignored"}

        logger.info(f"👤 {user_name} ({phone}): [{message_type}] {user_message}")

        # Gera resposta natural
        reply = await bot.get_natural_response(phone, user_message, message_type)
        
        # Delay humano realista (10-45 segundos)
        delay = random.randint(10, 45)
        logger.info(f"⏰ Delay humano: {delay}s")
        await asyncio.sleep(delay)
        
        # Envia resposta
        success = await bot.send_whatsapp_message(phone, reply)
        
        return {"status": "success" if success else "error"}

    except Exception as e:
        logger.error(f"💥 Erro webhook: {e}")
        return {"status": "error"}

@app.get("/")
async def dashboard():
    """Dashboard simples"""
    cursor = db.conn.cursor()
    
    # Stats básicas
    cursor.execute("SELECT COUNT(*) FROM conversations WHERE date(timestamp) = date('now')")
    today_conversations = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM conversions WHERE date(timestamp) = date('now')")
    today_conversions = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(DISTINCT user_id) FROM conversations")
    total_users = cursor.fetchone()[0]
    
    conversion_rate = (today_conversions / today_conversations * 100) if today_conversations > 0 else 0
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head><title>Ana - Atendente Virtual</title>
    <style>
        body {{font-family: Arial; margin: 30px; background: #f8f9fa;}}
        .card {{background: white; padding: 25px; margin: 15px 0; border-radius: 12px; box-shadow: 0 3px 15px rgba(0,0,0,0.1);}}
        .metric {{font-size: 32px; font-weight: bold; color: #007bff;}}
        .success {{color: #28a745;}}
        .info {{color: #6c757d; font-size: 14px;}}
    </style>
    </head>
    <body>
        <h1>🤖 Ana - Atendente Virtual Natural</h1>
        
        <div class="card">
            <h2>📊 Performance Hoje</h2>
            <p>Conversas: <span class="metric">{today_conversations}</span></p>
            <p>Conversões: <span class="metric success">{today_conversions}</span></p>
            <p>Taxa: <span class="metric">{conversion_rate:.1f}%</span></p>
        </div>
        
        <div class="card">
            <h2>🧠 Sistema Inteligente</h2>
            <p>✅ Respostas naturais e variadas</p>
            <p>✅ Delay humano (10-45s)</p>
            <p>✅ Reconhece áudio automaticamente</p>
            <p>✅ Contexto de conversa inteligente</p>
            <p>✅ Localização adaptável</p>
            <p class="info">Total usuários: {total_users}</p>
        </div>
        
        <div class="card">
            <h2>🎯 Funcionalidades</h2>
            <p>📱 <strong>WhatsApp:</strong> +55 42 8838-8120</p>
            <p>💬 <strong>Suporta:</strong> Texto, Áudio, Imagem, Vídeo</p>
            <p>🔊 <strong>Transcrição:</strong> Áudios via Whisper AI</p>
            <p>💰 <strong>Produto:</strong> €19,90 pagamento único</p>
        </div>
    </body>
    </html>
    """
    
    return HTMLResponse(html)

@app.post("/conversion/{user_id}")
async def manual_conversion(user_id: str):
    """Registra conversão manual"""
    cursor = db.conn.cursor()
    cursor.execute('INSERT INTO conversions (user_id, amount) VALUES (?, ?)', (user_id, 19.90))
    db.conn.commit()
    
    # Atualiza perfil
    db.update_user_profile(user_id, converted=True, conversion_stage='converted')
    
    logger.info(f"💰 Conversão manual registrada: {user_id}")
    return {"status": "success", "amount": 19.90}

@app.get("/analytics")
async def analytics():
    """Analytics detalhados"""
    cursor = db.conn.cursor()
    
    cursor.execute('''
        SELECT conversion_stage, COUNT(*) 
        FROM conversations 
        WHERE date(timestamp) = date('now')
        GROUP BY conversion_stage
    ''')
    stages = dict(cursor.fetchall())
    
    cursor.execute('SELECT COUNT(*) FROM conversions')
    total_conversions = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(DISTINCT user_id) FROM conversations')
    total_users = cursor.fetchone()[0]
    
    return {
        "stages_today": stages,
        "total_conversions": total_conversions,
        "total_users": total_users,
        "conversion_rate": f"{(total_conversions/total_users*100) if total_users > 0 else 0:.1f}%"
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    logger.info(f"🚀 Ana - Sistema Natural iniciando na porta {port}")
    logger.info(f"🎵 Suporte a áudio: ✅")
    logger.info(f"⏰ Delay humano: 10-45 segundos")
    logger.info(f"🧠 IA natural e adaptável: ✅")
    uvicorn.run(app, host="0.0.0.0", port=port)
