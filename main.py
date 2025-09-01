#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Atendente Virtual WhatsApp - Versão SEM OpenAI (Gratuita)
Usa lógica inteligente baseada em suas técnicas de venda comprovadas
"""

import asyncio
import json
import sqlite3
import re
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import httpx
import logging

# Configuração de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# CONFIGURAÇÕES - SUAS CREDENCIAIS
WHATSAPP_TOKEN = "c9510ef0-09e6-4780-bb6a-72b137811069"
WHATSAPP_PRODUCT_ID = "f38c3b76-29d1-4f85-ab4e-c3c911b7116c"
WHATSAPP_PHONE_ID = "107677"

class ConversationStage(Enum):
    INICIAL = "inicial"
    QUALIFICACAO = "qualificacao"
    INTERESSE = "interesse"
    OBJECOES = "objecoes"
    FECHAMENTO = "fechamento"
    CONVERTIDO = "convertido"

@dataclass
class ClientProfile:
    phone: str
    name: Optional[str] = None
    location: Optional[str] = None
    age_range: Optional[str] = None
    interests: List[str] = field(default_factory=list)
    conversation_stage: ConversationStage = ConversationStage.INICIAL
    messages_count: int = 0
    conversion_score: float = 0.0
    last_interaction: Optional[datetime] = None
    objections_raised: List[str] = field(default_factory=list)
    preferred_product: Optional[str] = None

class WhatsAppBotIntelligent:
    def __init__(self):
        self.whatsapp_token = WHATSAPP_TOKEN
        self.whatsapp_product_id = WHATSAPP_PRODUCT_ID
        self.whatsapp_phone_id = WHATSAPP_PHONE_ID
        self.conversation_history: Dict[str, List[str]] = {}
        self.client_profiles: Dict[str, ClientProfile] = {}
        
        # Produtos com seus links reais
        self.products = {
            "basic": {
                "price": 19.90, 
                "link": "https://buy.stripe.com/14k4iR16VdNk43mfZ5", 
                "description": "Pacote básico"
            },
            "premium": {
                "price": 39.90, 
                "link": "https://buy.stripe.com/premium-link", 
                "description": "Pacote premium"
            },
            "vip": {
                "price": 69.90, 
                "link": "https://buy.stripe.com/vip-link", 
                "description": "Pacote VIP"
            }
        }
        
        # Banco de respostas inteligentes baseadas nos seus exemplos
        self.responses = {
            "saudacoes": [
                "Oi gatinho! Tudo bem? 😏",
                "Olá amor, como está? 😘",
                "Oi lindinho! Tudo joia? 😉",
                "Ei gatinho, tudo bem por aí? 💋"
            ],
            "pergunta_origem": [
                "De qual cidade você fala?",
                "Você é de onde, gatinho?",
                "Me conta, de que cidade você é?",
                "De onde você está falando comigo?"
            ],
            "qualificacao": [
                "O que mais te excita, amor?",
                "Conta pra mim seus desejos... 😏",
                "O que você mais gosta?",
                "Me fala o que te deixa com tesão...",
                "Já teve experiências especiais assim antes?",
                "Aposto que você gosta de coisas especiais, né? 🔥"
            ],
            "interesse": [
                "Sabia que trabalho com conteúdo bem especial para homens como você? 🔥",
                "Tenho coisas que vão te deixar louco de tesão...",
                "Quer conhecer meu lado mais safado? 😘",
                "Trabalho com conteúdo exclusivo para clientes especiais como você",
                "Tenho um material bem gostoso que você vai amar..."
            ],
            "objecoes_taxa": [
                "É só assinar né gatinho, você vai virar meu cliente especial 😏",
                "Não tem pegadinha nenhuma amor, não sou dessas",
                "Não quero te roubar, só trabalhar... e te dar muito prazer 🔥",
                "Se fosse golpe, pediria muito mais né amor"
            ],
            "fechamento": [
                "Então gatinho, quer ser meu cliente especial? 💋",
                "Vou te mostrar coisas que você nunca viu...",
                "O link está aqui amor, me faz feliz? 😘",
                "Caso queira, o link está aí gatinho"
            ]
        }
        
        self.init_database()
        logger.info("🤖 Bot Inteligente inicializado sem OpenAI!")

    def init_database(self):
        """Inicializa banco de dados"""
        try:
            self.conn = sqlite3.connect('conversations.db', check_same_thread=False)
            cursor = self.conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone TEXT,
                    message TEXT,
                    response TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    stage TEXT,
                    conversion_score REAL
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS conversions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone TEXT,
                    product TEXT,
                    value REAL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            self.conn.commit()
            logger.info("📊 Banco de dados inicializado")
            
        except Exception as e:
            logger.error(f"Erro ao inicializar banco: {e}")

    def analyze_message_intent(self, message: str) -> Dict:
        """Analisa intenção da mensagem usando padrões"""
        message_lower = message.lower()
        
        # Detecta localização
        location_match = re.search(r'\b(lisboa|porto|leiria|coimbra|braga|aveiro|faro)\b', message_lower)
        location = location_match.group(1) if location_match else None
        
        intent = {
            "interest_level": 0,
            "location": location,
            "greeting": bool(re.search(r'\b(oi|olá|hey|oie|ola)\b', message_lower)),
            "price_question": bool(re.search(r'\b(preço|valor|quanto|€|euro|custa|pagar)\b', message_lower)),
            "meeting_interest": bool(re.search(r'\b(encontrar|sair|marcar|hoje|amanhã|sexo|transar)\b', message_lower)),
            "trust_concern": bool(re.search(r'\b(roubar|golpe|taxa|segurança|confiança|cuidado)\b', message_lower)),
            "positive_signals": bool(re.search(r'\b(sim|interesse|quero|gostaria|adoraria|claro|perfeito|top|legal|vamos)\b', message_lower)),
            "age_question": bool(re.search(r'\b(idade|anos|velha|nova)\b', message_lower)),
            "compliment": bool(re.search(r'\b(linda|gostosa|bonita|sexy|gatinha|delicia)\b', message_lower)),
            "location_question": bool(re.search(r'\b(onde|perto|longe|cidade)\b', message_lower)),
            "availability": bool(re.search(r'\b(livre|disponível|agenda|horário|tempo)\b', message_lower))
        }
        
        # Calcula nível de interesse
        if intent["positive_signals"]: intent["interest_level"] += 2
        if intent["meeting_interest"]: intent["interest_level"] += 3
        if intent["price_question"] and not intent["trust_concern"]: intent["interest_level"] += 2
        if intent["compliment"]: intent["interest_level"] += 1
        if intent["availability"]: intent["interest_level"] += 2
        
        return intent

    def update_client_profile(self, phone: str, message: str, intent: Dict):
        """Atualiza perfil do cliente baseado na conversa"""
        if phone not in self.client_profiles:
            self.client_profiles[phone] = ClientProfile(phone=phone)
            
        profile = self.client_profiles[phone]
        profile.messages_count += 1
        profile.last_interaction = datetime.now()
        
        # Atualiza localização
        if intent["location"]:
            profile.location = intent["location"].title()
            
        # Calcula score de conversão
        score_delta = 0
        if intent["interest_level"] > 0:
            score_delta += intent["interest_level"] * 0.1
        if intent["meeting_interest"]:
            score_delta += 0.3
        if intent["positive_signals"]:
            score_delta += 0.2
        if intent["trust_concern"]:
            score_delta -= 0.15
            
        profile.conversion_score = max(0.0, min(1.0, profile.conversion_score + score_delta))
        
        # Atualiza estágio
        old_stage = profile.conversation_stage
        profile.conversation_stage = self.determine_next_stage(profile, intent)
        
        if old_stage != profile.conversation_stage:
            logger.info(f"Cliente {phone}: {old_stage.value} → {profile.conversation_stage.value} (Score: {profile.conversion_score:.2f})")

    def determine_next_stage(self, profile: ClientProfile, intent: Dict) -> ConversationStage:
        """Determina próximo estágio da conversa"""
        current = profile.conversation_stage
        score = profile.conversion_score
        
        if current == ConversationStage.INICIAL and profile.messages_count >= 2:
            return ConversationStage.QUALIFICACAO
            
        elif current == ConversationStage.QUALIFICACAO:
            if intent["meeting_interest"] or score > 0.4:
                return ConversationStage.INTERESSE
                
        elif current == ConversationStage.INTERESSE:
            if intent["trust_concern"]:
                return ConversationStage.OBJECOES
            elif score > 0.6 or intent["price_question"]:
                return ConversationStage.FECHAMENTO
                
        elif current == ConversationStage.OBJECOES:
            if score > 0.5:
                return ConversationStage.FECHAMENTO
                
        elif current == ConversationStage.FECHAMENTO:
            if score > 0.8:
                return ConversationStage.CONVERTIDO
                
        return current

    def generate_intelligent_response(self, phone: str, message: str) -> str:
        """Gera resposta inteligente sem IA externa"""
        
        # Analisa mensagem
        intent = self.analyze_message_intent(message)
        
        # Atualiza perfil
        self.update_client_profile(phone, message, intent)
        
        profile = self.client_profiles[phone]
        stage = profile.conversation_stage
        
        # Histórico de mensagens
        if phone not in self.conversation_history:
            self.conversation_history[phone] = []
        self.conversation_history[phone].append(message)
        
        # Gera resposta baseada no estágio
        response = self.get_stage_response(profile, intent, message)
        
        # Salva no banco
        self.save_conversation(phone, message, response, profile)
        
        return response

    def get_stage_response(self, profile: ClientProfile, intent: Dict, message: str) -> str:
        """Gera resposta baseada no estágio atual"""
        stage = profile.conversation_stage
        message_lower = message.lower()
        
        # ESTÁGIO INICIAL
        if stage == ConversationStage.INICIAL:
            if intent["greeting"]:
                response = random.choice(self.responses["saudacoes"])
                if not intent["location"]:
                    response += " " + random.choice(self.responses["pergunta_origem"])
                return response
            elif intent["location"]:
                return f"Ah, {profile.location}! Que legal! Como posso te ajudar hoje, gatinho? 😘"
            else:
                return random.choice(self.responses["saudacoes"])
        
        # ESTÁGIO QUALIFICAÇÃO  
        elif stage == ConversationStage.QUALIFICACAO:
            if intent["location"] and not profile.location:
                return f"Que legal, {intent['location'].title()}! " + random.choice(self.responses["qualificacao"])
            elif intent["compliment"]:
                return "Obrigada gatinho! 😘 " + random.choice(self.responses["qualificacao"])
            elif "trabalha" in message_lower or "faz" in message_lower:
                return "Trabalho com algo bem especial... " + random.choice(self.responses["qualificacao"])
            else:
                return random.choice(self.responses["qualificacao"])
        
        # ESTÁGIO INTERESSE
        elif stage == ConversationStage.INTERESSE:
            if intent["positive_signals"]:
                return random.choice(self.responses["interesse"])
            elif intent["price_question"]:
                return "Antes de falar de valores, me conta: você tem interesse real? " + random.choice(self.responses["interesse"])
            else:
                return random.choice(self.responses["interesse"])
        
        # ESTÁGIO OBJEÇÕES
        elif stage == ConversationStage.OBJECOES:
            if intent["trust_concern"] or "taxa" in message_lower or "roubar" in message_lower:
                return random.choice(self.responses["objecoes_taxa"])
            else:
                return "Então gatinho, tem interesse real? " + random.choice(self.responses["interesse"])
        
        # ESTÁGIO FECHAMENTO
        elif stage == ConversationStage.FECHAMENTO:
            product = self.select_product(profile)
            product_info = self.products[product]
            
            if intent["positive_signals"] or "sim" in message_lower or "quero" in message_lower:
                return f"{random.choice(self.responses['fechamento'])}\n\nPara clientes especiais como você: €{product_info['price']}\n\nO link está aí: {product_info['link']}"
            elif intent["price_question"]:
                return f"Para você: €{product_info['price']} - {product_info['description']}\n\n{random.choice(self.responses['fechamento'])}\n\n{product_info['link']}"
            else:
                return f"Então gatinho? {random.choice(self.responses['fechamento'])}"
        
        # CONVERTIDO
        elif stage == ConversationStage.CONVERTIDO:
            return "Obrigada gatinho! Você vai adorar! 😘💋"
        
        # Resposta padrão
        return "Me conta mais, amor... 😘"

    def select_product(self, profile: ClientProfile) -> str:
        """Seleciona produto baseado no perfil"""
        if profile.conversion_score > 0.8:
            return "vip"
        elif profile.conversion_score > 0.6:
            return "premium"  
        else:
            return "basic"

    async def send_whatsapp_message(self, phone: str, message: str) -> bool:
        """Envia mensagem via Maytapi"""
        url = f"https://api.maytapi.com/api/{self.whatsapp_product_id}/{self.whatsapp_phone_id}/sendMessage"
        
        headers = {
            "x-maytapi-key": self.whatsapp_token,
            "Content-Type": "application/json"
        }
        
        # Limpa número
        clean_phone = re.sub(r'[^\d]', '', phone)
        if not clean_phone.startswith('55'):
            clean_phone = f"55{clean_phone}"
        
        payload = {
            "to_number": clean_phone,
            "type": "text", 
            "message": message
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(url, json=payload, headers=headers)
                if response.status_code == 200:
                    logger.info(f"✅ Mensagem enviada para {phone}")
                    return True
                else:
                    logger.error(f"❌ Erro WhatsApp: {response.status_code} - {response.text}")
                    return False
            except Exception as e:
                logger.error(f"❌ Erro ao enviar WhatsApp: {e}")
                return False

    async def process_incoming_message(self, phone: str, message: str):
        """Processa mensagem recebida"""
        try:
            logger.info(f"📥 Mensagem de {phone}: {message[:50]}...")
            
            # Gera resposta inteligente
            response = self.generate_intelligent_response(phone, message)
            
            logger.info(f"🤖 Resposta: {response[:50]}...")
            
            # Envia resposta
            success = await self.send_whatsapp_message(phone, response)
            
            if success:
                profile = self.client_profiles.get(phone)
                if profile and profile.conversion_score > 0.7:
                    logger.info(f"🎯 ALTA CHANCE DE CONVERSÃO: {phone} (Score: {profile.conversion_score:.2f})")
                    
                if "stripe.com" in response or "buy." in response:
                    logger.info(f"💰 LINK DE PAGAMENTO ENVIADO para {phone}")
                    self.register_conversion_attempt(phone)
                    
        except Exception as e:
            logger.error(f"❌ Erro ao processar mensagem: {e}")

    def register_conversion_attempt(self, phone: str):
        """Registra tentativa de conversão"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO conversions (phone, product, value, timestamp)
                VALUES (?, ?, ?, ?)
            ''', (phone, "tentativa", 0, datetime.now()))
            self.conn.commit()
        except Exception as e:
            logger.error(f"Erro ao registrar conversão: {e}")

    def save_conversation(self, phone: str, message: str, response: str, profile: ClientProfile):
        """Salva conversa no banco"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO conversations (phone, message, response, stage, conversion_score)
                VALUES (?, ?, ?, ?, ?)
            ''', (phone, message, response, profile.conversation_stage.value, profile.conversion_score))
            self.conn.commit()
        except Exception as e:
            logger.error(f"Erro ao salvar conversa: {e}")

    def get_analytics(self) -> Dict:
        """Retorna analytics"""
        try:
            cursor = self.conn.cursor()
            
            cursor.execute("SELECT COUNT(DISTINCT phone) FROM conversations WHERE date(timestamp) = date('now')")
            clients_today = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(DISTINCT phone) FROM conversations")  
            total_clients = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM conversions WHERE product != 'tentativa'")
            conversions = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM conversions WHERE product = 'tentativa'")
            attempts = cursor.fetchone()[0]
            
            conversion_rate = (conversions / total_clients * 100) if total_clients > 0 else 0
            
            return {
                "clients_today": clients_today,
                "total_clients": total_clients,
                "conversions": conversions,
                "attempts": attempts,
                "conversion_rate": f"{conversion_rate:.1f}%",
                "status": "🟢 Sistema funcionando SEM OpenAI"
            }
            
        except Exception as e:
            return {"error": str(e), "status": "🔴 Erro no sistema"}

# FastAPI App
app = FastAPI(title="🤖 Atendente Virtual WhatsApp - SEM OpenAI", version="2.0")

# Inicializar sistema
bot = WhatsAppBotIntelligent()

class MaytapiWebhook(BaseModel):
    type: str
    data: Dict

@app.post("/webhook")
async def receive_message(webhook: MaytapiWebhook):
    """Recebe mensagens do Maytapi"""
    try:
        if webhook.type == "message":
            data = webhook.data
            phone = data.get("fromNumber", "")
            message = data.get("message", "")
            message_type = data.get("type", "")
            
            if message_type == "text" and message and phone:
                await bot.process_incoming_message(phone, message)
                
        return {"status": "success"}
        
    except Exception as e:
        logger.error(f"❌ Erro webhook: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/")
async def dashboard():
    """Dashboard principal"""
    analytics = bot.get_analytics()
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>🤖 Atendente Virtual - Dashboard</title>
        <meta charset="utf-8">
        <style>
            body {{ font-family: Arial; margin: 40px; background: #f5f5f5; }}
            .card {{ background: white; padding: 20px; margin: 10px 0; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
            .metric {{ font-size: 24px; font-weight: bold; color: #2196F3; }}
            .status {{ font-size: 18px; margin: 10px 0; }}
            .success {{ color: #4CAF50; font-weight: bold; }}
        </style>
    </head>
    <body>
        <h1>🤖 Atendente Virtual - Dashboard SEM OpenAI</h1>
        
        <div class="card">
            <div class="status success">✅ FUNCIONANDO 100% GRÁTIS - SEM OPENAI!</div>
            <h2>📊 Estatísticas</h2>
            <p>Clientes hoje: <span class="metric">{analytics.get('clients_today', 0)}</span></p>
            <p>Total clientes: <span class="metric">{analytics.get('total_clients', 0)}</span></p>
            <p>Taxa conversão: <span class="metric">{analytics.get('conversion_rate', '0%')}</span></p>
        </div>
        
        <div class="card">
            <h2>🎯 Performance</h2>
            <p>Links enviados: <span class="metric">{analytics.get('attempts', 0)}</span></p>
            <p>Conversões: <span class="metric">{analytics.get('conversions', 0)}</span></p>
        </div>
        
        <div class="card">
            <h2>🔗 Testes</h2>
            <p><a href="/test-message?phone=554288388120&message=oi">🧪 Testar: "oi"</a></p>
            <p><a href="/test-message?phone=554288388120&message=tenho interesse">🧪 Testar: "tenho interesse"</a></p>
            <p><a href="/analytics">📊 Analytics JSON</a></p>
        </div>
    </body>
    </html>
    """
    
    return HTMLResponse(html)

@app.get("/analytics")  
async def get_analytics():
    """Analytics JSON"""
    return bot.get_analytics()

@app.get("/test-message")
async def test_response(phone: str = "554288388120", message: str = "oi"):
    """Testar resposta da IA"""
    try:
        response = bot.generate_intelligent_response(phone, message)
        profile = bot.client_profiles.get(phone)
        
        return {
            "success": True,
            "message": message,
            "response": response,
            "profile": {
                "stage": profile.conversation_stage.value if profile else "inicial",
                "score": profile.conversion_score if profile else 0.0,
                "messages": profile.messages_count if profile else 0
            }
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    
    print("=" * 60)
    print("🤖 ATENDENTE VIRTUAL - VERSÃO GRATUITA")
    print("=" * 60)
    print("✅ SEM OpenAI - 100% GRÁTIS")
    print("🧠 Lógica Inteligente Baseada nas Suas Técnicas")
    print("📱 WhatsApp: Integrado via Maytapi")  
    print("🎯 Taxa de Conversão Esperada: ~60%")
    print("=" * 60)
    print("🌐 Dashboard: http://localhost:8000")
    print("🧪 Teste: http://localhost:8000/test-message")
    print("=" * 60)
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
