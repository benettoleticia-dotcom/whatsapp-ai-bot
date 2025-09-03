import os
import asyncio
import random
import logging
import sqlite3
import json
import re
from datetime import datetime, time
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

# Base de dados inteligente (melhorada)
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
                conversion_stage TEXT DEFAULT 'initial',
                mood_history TEXT DEFAULT '',
                preferred_time TEXT DEFAULT ''
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
                conversion_stage TEXT,
                sentiment_score REAL DEFAULT 0,
                emoji_used TEXT DEFAULT ''
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
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS followups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                scheduled_time DATETIME,
                message TEXT,
                sent BOOLEAN DEFAULT FALSE
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
                'conversion_stage': result[7],
                'mood_history': result[8] if len(result) > 8 else '',
                'preferred_time': result[9] if len(result) > 9 else ''
            }
        return None
    
    def update_user_profile(self, user_id, **kwargs):
        cursor = self.conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO user_profiles 
            (user_id, name, location, city, messages_count, last_interaction, converted, conversion_stage, mood_history, preferred_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            kwargs.get('name'),
            kwargs.get('location'),
            kwargs.get('city'),
            kwargs.get('messages_count', 1),
            datetime.now(),
            kwargs.get('converted', False),
            kwargs.get('conversion_stage', 'initial'),
            kwargs.get('mood_history', ''),
            kwargs.get('preferred_time', '')
        ))
        
        self.conn.commit()
    
    def log_conversation(self, user_id, user_message, ai_response, message_type, stage, sentiment=0, emoji=''):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO conversations (user_id, user_message, ai_response, message_type, conversion_stage, sentiment_score, emoji_used)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, user_message, ai_response, message_type, stage, sentiment, emoji))
        self.conn.commit()
    
    def schedule_followup(self, user_id, hours_delay, message):
        cursor = self.conn.cursor()
        scheduled_time = datetime.now() + datetime.timedelta(hours=hours_delay)
        cursor.execute('''
            INSERT INTO followups (user_id, scheduled_time, message)
            VALUES (?, ?, ?)
        ''', (user_id, scheduled_time, message))
        self.conn.commit()

db = SmartDatabase()
user_histories = {}

class NaturalSalesBot:
    def __init__(self):
        self.max_context = 10
        
        # Cidades portuguesas para reconhecimento inteligente
        self.portuguese_cities = {
            'lisboa': 'Lisboa', 'porto': 'Porto', 'coimbra': 'Coimbra', 'braga': 'Braga',
            'aveiro': 'Aveiro', 'faro': 'Faro', 'cascais': 'Cascais', 'felgueiras': 'Felgueiras',
            'leiria': 'Leiria', 'setubal': 'Setúbal', 'vila nova de gaia': 'Vila Nova de Gaia',
            'alfama': 'Alfama', 'ribeira': 'Ribeira'
        }
        
        # Personalidades baseadas no horário
        self.time_personalities = {
            'morning': {  # 6-12h
                'mood': 'energética e animada',
                'greetings': ['Bom dia, amor! ☀️', 'Oi querido! Como acordaste?', 'Bom dia! Que energia boa!'],
                'style': 'mais carinhosa e maternal'
            },
            'afternoon': {  # 12-18h
                'mood': 'relaxada e conversadora',
                'greetings': ['Oi! Boa tarde 😊', 'Hey! Como está a tarde?', 'Olá querido!'],
                'style': 'mais casual e amigável'
            },
            'evening': {  # 18-22h
                'mood': 'sedutora e direta',
                'greetings': ['Oi gato! Boa noite 🌙', 'Hey... boa noite 😏', 'Olá lindinho'],
                'style': 'mais sedutora e ousada'
            },
            'night': {  # 22-6h
                'mood': 'íntima e provocante',
                'greetings': ['Oi amor... ainda acordado? 😘', 'Hey... noite quente né? 🔥', 'Olá gostoso'],
                'style': 'mais provocante e íntima'
            }
        }
        
        # Emojis contextuais inteligentes
        self.contextual_emojis = {
            'happy': ['😊', '😘', '🥰', '💕', '❤️'],
            'excited': ['🔥', '😍', '🤩', '✨', '💫'],
            'playful': ['😏', '😉', '🙈', '😜', '🤭'],
            'loving': ['💖', '💗', '💝', '🌹', '💋'],
            'cool': ['😎', '✌️', '👌', '🆒', '💪']
        }
        
        # Sistema de análise de sentimento
        self.sentiment_keywords = {
            'positive': ['legal', 'gosto', 'amo', 'adoro', 'gostoso', 'lindo', 'perfeito', 'incrível'],
            'negative': ['chato', 'ruim', 'não gosto', 'irritante', 'cansado', 'estressado'],
            'excited': ['quero', 'vamos', 'ansioso', 'louco', 'desejo', 'tesão'],
            'neutral': ['ok', 'tudo bem', 'normal', 'talvez']
        }
    
    def get_current_time_period(self):
        """Determina período do dia para personalidade"""
        current_hour = datetime.now().hour
        
        if 6 <= current_hour < 12:
            return 'morning'
        elif 12 <= current_hour < 18:
            return 'afternoon'
        elif 18 <= current_hour < 22:
            return 'evening'
        else:
            return 'night'
    
    def analyze_sentiment(self, message):
        """Analisa sentimento da mensagem"""
        message_lower = message.lower()
        sentiment_scores = {'positive': 0, 'negative': 0, 'excited': 0, 'neutral': 0}
        
        for sentiment, keywords in self.sentiment_keywords.items():
            for keyword in keywords:
                if keyword in message_lower:
                    sentiment_scores[sentiment] += 1
        
        # Retorna sentimento dominante
        max_sentiment = max(sentiment_scores, key=sentiment_scores.get)
        score = sentiment_scores[max_sentiment]
        
        return max_sentiment if score > 0 else 'neutral', score
    
    def get_contextual_emoji(self, sentiment, context):
        """Escolhe emoji baseado no sentimento e contexto"""
        if sentiment in ['positive', 'excited']:
            return random.choice(self.contextual_emojis['happy'] + self.contextual_emojis['excited'])
        elif sentiment == 'negative':
            return random.choice(['😔', '😅', '🤗'])  # Emojis empáticos
        elif 'foto' in context.lower() or 'imagem' in context.lower():
            return random.choice(['😍', '🔥', '😘'])
        else:
            return random.choice(self.contextual_emojis['playful'])
    
    def extract_location_info(self, message):
        """Extrai informação de localização de forma inteligente"""
        message_lower = message.lower()
        
        if 'portugal' in message_lower:
            return {'type': 'country', 'location': 'Portugal', 'city': None}
        
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
            'stage': 'initial',
            'time_period': self.get_current_time_period(),
            'user_sentiment': 'neutral'
        }
        
        if profile:
            context['knows_location'] = bool(profile.get('city'))
            context['stage'] = profile.get('conversion_stage', 'initial')
        
        # Analisa sentimento
        sentiment, score = self.analyze_sentiment(message)
        context['user_sentiment'] = sentiment
        context['sentiment_score'] = score
        
        # Verifica histórico
        for msg in history:
            if 'cidade' in msg.get('content', '').lower():
                context['already_asked_location'] = True
                break
        
        # Extrai localização
        location_info = self.extract_location_info(message)
        if location_info:
            context['location_info'] = location_info
            
        return context
    
    def determine_conversion_stage(self, user_id, message, context):
        """Determina estágio da conversa de forma inteligente"""
        message_lower = message.lower()
        
        interest_keywords = ['interesse', 'quero', 'comprar', 'valores', 'preço', 'quanto', 'cliente', 'plataforma']
        service_keywords = ['sexo', 'sair', 'encontrar', 'transar', 'serviços', 'fazer', 'program']
        closing_keywords = ['sim', 'vamos', 'ok', 'feito', 'pago', 'compro', 'aceito']
        
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
        """Constrói prompt SUPER natural com personalidade adaptável"""
        
        profile = db.get_user_profile(user_id)
        user_name = profile.get('name', 'cliente') if profile else 'cliente'
        user_location = profile.get('city') if profile else None
        
        ai_location = user_location if user_location else "Porto"
        if context['location_info'] and context['location_info']['type'] == 'city':
            ai_location = context['location_info']['city']
        
        # Personalidade baseada no horário
        time_personality = self.time_personalities[context['time_period']]
        
        # Contexto especial para diferentes tipos
        special_context = ""
        if message_type in ["image", "photo"]:
            special_context = "O cliente enviou uma FOTO! Reage com entusiasmo e naturalidade."
        elif message_type == "audio":
            special_context = "Cliente enviou áudio. Seja mais carinhosa."
        
        # Adaptação ao sentimento do usuário
        mood_adaptation = ""
        if context['user_sentiment'] == 'excited':
            mood_adaptation = "Cliente está empolgado! Seja mais ousada e direta."
        elif context['user_sentiment'] == 'negative':
            mood_adaptation = "Cliente parece chateado. Seja mais carinhosa e empática."
        elif context['user_sentiment'] == 'positive':
            mood_adaptation = "Cliente está animado! Mantenha o clima positivo."
        
        # Escolhe emoji contextual
        emoji = self.get_contextual_emoji(context['user_sentiment'], message + message_type)
        
        prompt = f"""És Ana, portuguesa de {ai_location}. Trabalhas com conteúdo adulto e és super natural.

PERSONALIDADE AGORA ({context['time_period']}):
{time_personality['mood']} - {time_personality['style']}

SITUAÇÃO:
Cliente: {user_name} | Local: {user_location or 'Desconhecido'} | Msg #{context['messages_count']+1} | Fase: {context['stage']}
{special_context}
{mood_adaptation}

COMO RESPONDER:
• Usa português de Portugal autêntico
• {time_personality['style']} 
• Varia muito as respostas, nunca repetes
• Usa "{emoji}" quando apropriado
• Máximo 2 linhas por mensagem
• Se foto → reage com "Que giro! {emoji}" ou similar

DIRETRIZES RÁPIDAS:
→ Primeira vez + não sabe cidade = "De onde me falas?"
→ Pergunta sobre serviços = "Só saio com meus clientes das plataformas"
→ Interesse no preço = "€19,90 pagamento único, baratinho para selecionar"
→ Quer comprar = link: https://buy.stripe.com/14k4iR16VdNk43mfZ5

EXEMPLOS POR HORÁRIO:
Manhã: "{random.choice(time_personality['greetings'])}"
Tarde: "Hey! Como está a tarde? {emoji}"
Noite: "Oi gato... {emoji}"

REGRA OURO: Fala como se fosses uma amiga real pelo WhatsApp. Zero robotização!

Resposta natural ({time_personality['mood']}):
