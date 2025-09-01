#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sistema de Atendente Virtual Inteligente para WhatsApp
Criado para vendas de conteúdo adulto premium
"""

import asyncio
import json
import sqlite3
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum
import openai
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
import httpx
import logging

# Configuração de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# CONFIGURAÇÕES - SUAS CREDENCIAIS
OPENAI_API_KEY = "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"
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

class WhatsAppAI:
    def __init__(self):
        self.openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)
        self.whatsapp_token = WHATSAPP_TOKEN
        self.whatsapp_product_id = WHATSAPP_PRODUCT_ID
        self.whatsapp_phone_id = WHATSAPP_PHONE_ID
        self.conversation_history: Dict[str, List[Dict]] = {}
        self.client_profiles: Dict[str, ClientProfile] = {}
        
        # Produtos disponíveis com seus links reais
        self.products = {
            "basic": {
                "price": 19.90, 
                "link": "https://buy.stripe.com/14k4iR16VdNk43mfZ5", 
                "description": "Pacote básico - ideal para começar"
            },
            "premium": {
                "price": 39.90, 
                "link": "https://buy.stripe.com/premium-link-aqui", 
                "description": "Pacote premium - mais conteúdo"
            },
            "vip": {
                "price": 69.90, 
                "link": "https://buy.stripe.com/vip-link-aqui", 
                "description": "Pacote VIP - experiência completa"
            },
            "exclusive": {
                "price": 100.00, 
                "link": "https://buy.stripe.com/exclusive-link-aqui", 
                "description": "Pacote exclusivo - tudo incluído"
            }
        }
        
        self.init_database()
        logger.info("🤖 Sistema WhatsApp AI inicializado com sucesso!")

    def init_database(self):
        """Inicializa o banco de dados SQLite"""
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
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS client_profiles (
                    phone TEXT PRIMARY KEY,
                    location TEXT,
                    interests TEXT,
                    conversion_score REAL,
                    last_interaction DATETIME
                )
            ''')
            
            self.conn.commit()
            logger.info("📊 Banco de dados inicializado")
            
        except Exception as e:
            logger.error(f"Erro ao inicializar banco: {e}")

    def get_system_prompt(self, profile: ClientProfile) -> str:
        """Gera o prompt personalizado para cada cliente"""
        return f"""
Você é Ana, uma atendente virtual especializada em vendas. Seu objetivo é converter clientes de forma natural e eficiente.

INFORMAÇÕES DO CLIENTE:
- Telefone: {profile.phone}
- Localização: {profile.location or 'Não informada'}
- Estágio atual: {profile.conversation_stage.value}
- Mensagens trocadas: {profile.messages_count}
- Score de conversão: {profile.conversion_score:.2f}/1.0
- Última interação: {profile.last_interaction or 'Primeira vez'}

PRODUTOS DISPONÍVEIS:
- Básico: €19,90 - {self.products['basic']['description']}
- Premium: €39,90 - {self.products['premium']['description']}
- VIP: €69,90 - {self.products['vip']['description']}
- Exclusivo: €100,00 - {self.products['exclusive']['description']}

PERSONALIDADE E ESTILO:
- Seja sedutora, provocante e envolvente
- Use linguagem informal portuguesa (né, kkk, amor, gatinho, etc.)
- Seja safadinha mas elegante - crie tensão sexual
- Faça insinuações sutis e provocações
- Use emojis sensuais: 😏😘🔥💋
- Seja sempre transparente sobre preços
- Crie desejo antes de vender

ESTRATÉGIA POR ESTÁGIO:

🔸 INICIAL (primeiras mensagens):
- "Oi gatinho! Tudo bem? 😏"
- "Olá amor, como está? 😘" 
- Pergunte de onde fala com charme
- Seja acolhedora e sedutora

🔸 QUALIFICAÇÃO (mensagens 2-6):
- "O que mais te excita?" "Conta pra mim seus desejos..."
- "Já teve experiências especiais assim antes?"
- Use provocações: "Aposto que você gosta de..." 
- Construa tensão sexual sem mencionar preços
- "Me conta o que te deixa com tesão..."

🔸 INTERESSE (mensagens 6-10):
- "Sabia que trabalho com conteúdo bem especial para homens como você? 🔥"
- "Tenho coisas que vão te deixar louco de tesão..."
- "Quer conhecer meu lado mais safado?"
- Ainda NÃO fale preços - construa mais desejo

🔸 OBJEÇÕES (se aparecerem):
- "É só assinar né gatinho, você vai virar meu cliente especial 😏"
- "Não tem pegadinha nenhuma amor, não sou dessas"
- "Não quero te roubar, só trabalhar... e te dar muito prazer 🔥"
- "Se fosse golpe, pediria muito mais né amor"

🔸 FECHAMENTO (score > 0.6):
- "Então gatinho, quer ser meu cliente especial? 💋"
- "Vou te mostrar coisas que você nunca viu..."
- Seja direta mas sensual: "O link está aqui amor, me faz feliz? 😘"
- Envie o link com charme

REGRAS IMPORTANTES:
- SÓ mencione preços quando o cliente demonstrar interesse real
- SEMPRE seja transparente - "sem pegadinhas"
- Responda objeções com naturalidade, como nos exemplos
- Use as frases exatas que funcionam
- Quando enviar link, diga: "O link está aí" + link

SINAIS PARA AVANÇAR ESTÁGIOS:
- Cliente pergunta sobre valores = INTERESSADO
- Cliente menciona experiências ruins = OBJEÇÕES
- Cliente pergunta "como funciona" = PRONTO PARA FECHAR
- Cliente demonstra pressa = FECHAR RÁPIDO

Mantenha conversas fluidas e naturais. Você é muito boa no que faz!
"""

    def analyze_message_intent(self, message: str) -> Dict:
        """Analisa a intenção e sentimento da mensagem"""
        message_lower = message.lower()
        
        # Extrai localização se mencionada
        location_match = re.search(r'\b(lisboa|porto|leiria|coimbra|braga|aveiro|faro)\b', message_lower)
        location = location_match.group(1) if location_match else None
        
        intent_analysis = {
            "interest_level": 0,
            "objections": [],
            "questions": [],
            "location": location,
            "price_concern": bool(re.search(r'\b(preço|valor|quanto|€|euro|caro|barato|custa)\b', message_lower)),
            "meeting_interest": bool(re.search(r'\b(encontrar|sair|marcar|hoje|amanhã|fim.de.semana|disponível)\b', message_lower)),
            "trust_concern": bool(re.search(r'\b(roubar|golpe|taxa|segurança|confiança|já.aconteceu|cuidado)\b', message_lower)),
            "positive_signals": bool(re.search(r'\b(interesse|quero|gostaria|adoraria|sim|claro|perfeito|top|legal)\b', message_lower)),
            "urgency": bool(re.search(r'\b(hoje|agora|rápido|urgente)\b', message_lower))
        }
        
        # Calcula nível de interesse
        if intent_analysis["positive_signals"]:
            intent_analysis["interest_level"] += 2
        if intent_analysis["meeting_interest"]:
            intent_analysis["interest_level"] += 3
        if intent_analysis["price_concern"] and not intent_analysis["trust_concern"]:
            intent_analysis["interest_level"] += 1
            
        return intent_analysis

    def update_conversion_score(self, profile: ClientProfile, intent: Dict):
        """Atualiza score baseado na análise da mensagem"""
        score_delta = 0
        
        # Sinais positivos
        if intent["interest_level"] > 0:
            score_delta += intent["interest_level"] * 0.15
            
        if intent["meeting_interest"]:
            score_delta += 0.25
            
        if intent["positive_signals"]:
            score_delta += 0.2
            
        if intent["urgency"]:
            score_delta += 0.15
            
        # Sinais negativos
        if intent["trust_concern"]:
            score_delta -= 0.1
            
        # Aplica mudança no score
        profile.conversion_score = max(0.0, min(1.0, profile.conversion_score + score_delta))
        
        # Atualiza localização se detectada
        if intent["location"]:
            profile.location = intent["location"].title()

    def determine_next_stage(self, profile: ClientProfile, intent: Dict) -> ConversationStage:
        """Determina o próximo estágio baseado no contexto"""
        current = profile.conversation_stage
        score = profile.conversion_score
        
        # Transições de estágio
        if current == ConversationStage.INICIAL and profile.messages_count >= 2:
            return ConversationStage.QUALIFICACAO
            
        elif current == ConversationStage.QUALIFICACAO:
            if intent["meeting_interest"] or score > 0.3:
                return ConversationStage.INTERESSE
                
        elif current == ConversationStage.INTERESSE:
            if intent["trust_concern"]:
                return ConversationStage.OBJECOES
            elif score > 0.6 or intent["price_concern"]:
                return ConversationStage.FECHAMENTO
                
        elif current == ConversationStage.OBJECOES:
            if score > 0.5:
                return ConversationStage.FECHAMENTO
                
        elif current == ConversationStage.FECHAMENTO:
            if score > 0.8:
                return ConversationStage.CONVERTIDO
                
        return current

    def select_optimal_product(self, profile: ClientProfile, intent: Dict) -> str:
        """Seleciona o produto ideal baseado no perfil e comportamento"""
        score = profile.conversion_score
        
        # Lógica de seleção baseada no score e sinais
        if score > 0.8 or intent.get("urgency", False):
            return "vip"  # Cliente muito interessado
        elif score > 0.6:
            return "premium"  # Cliente interessado
        elif score > 0.4:
            return "basic"  # Cliente testando águas
        else:
            return "basic"  # Começar com o mais acessível

    async def generate_intelligent_response(self, client_phone: str, message: str) -> str:
        """Gera resposta inteligente usando GPT-4"""
        
        # Obtém ou cria perfil
        if client_phone not in self.client_profiles:
            self.client_profiles[client_phone] = ClientProfile(phone=client_phone)
            
        profile = self.client_profiles[client_phone]
        profile.messages_count += 1
        profile.last_interaction = datetime.now()
        
        # Analisa a mensagem
        intent = self.analyze_message_intent(message)
        
        # Atualiza score e estágio
        self.update_conversion_score(profile, intent)
        old_stage = profile.conversation_stage
        profile.conversation_stage = self.determine_next_stage(profile, intent)
        
        # Log da progressão
        if old_stage != profile.conversation_stage:
            logger.info(f"Cliente {client_phone}: {old_stage.value} → {profile.conversation_stage.value} (Score: {profile.conversion_score:.2f})")
        
        # Prepara contexto da conversa
        if client_phone not in self.conversation_history:
            self.conversation_history[client_phone] = []
            
        conversation = self.conversation_history[client_phone][-8:]  # Últimas 8 mensagens
        
        # Adiciona instruções específicas do estágio
        stage_instructions = self.get_stage_instructions(profile, intent)
        
        # Monta mensagens para GPT
        messages = [
            {"role": "system", "content": self.get_system_prompt(profile) + stage_instructions},
            *conversation,
            {"role": "user", "content": message}
        ]
        
        try:
            # Chama GPT-4
            response = self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=messages,
                max_tokens=120,
                temperature=0.8,
                frequency_penalty=0.3
            )
            
            ai_response = response.choices[0].message.content.strip()
            
            # Pós-processamento da resposta
            ai_response = self.post_process_response(ai_response, profile, intent)
            
            # Salva conversa
            conversation.extend([
                {"role": "user", "content": message},
                {"role": "assistant", "content": ai_response}
            ])
            self.conversation_history[client_phone] = conversation
            
            # Salva no banco
            self.save_to_database(client_phone, message, ai_response, profile)
            
            return ai_response
            
        except Exception as e:
            logger.error(f"Erro GPT-4: {e}")
            return "Oi! Houve um probleminha técnico aqui. Pode mandar de novo? 😊"

    def get_stage_instructions(self, profile: ClientProfile, intent: Dict) -> str:
        """Instruções específicas baseadas no estágio atual"""
        stage = profile.conversation_stage
        
        if stage == ConversationStage.INICIAL:
            return "\n\nESTÁGIO INICIAL: Seja acolhedora, pergunte de onde fala, crie rapport inicial."
            
        elif stage == ConversationStage.QUALIFICACAO:
            return "\n\nESTÁGIO QUALIFICAÇÃO: Identifique interesses, construa confiança, NÃO mencione preços ainda."
            
        elif stage == ConversationStage.INTERESSE:
            return "\n\nESTÁGIO INTERESSE: Cliente demonstrou interesse. Explique que trabalha com 'conteúdo exclusivo para clientes especiais'."
            
        elif stage == ConversationStage.OBJECOES:
            return f"\n\nESTÁGIO OBJEÇÕES: Use exatamente estas frases: 'É só assinar né, você vai estar virando meu cliente' e 'Não tem taxas extras como já deve ter visto por aí'."
            
        elif stage == ConversationStage.FECHAMENTO:
            product = self.select_optimal_product(profile, intent)
            product_info = self.products[product]
            return f"\n\nESTÁGIO FECHAMENTO: Hora de fechar! Ofereça {product_info['description']} por €{product_info['price']} e envie: 'O link está aí, caso queira: {product_info['link']}'"
            
        return ""

    def post_process_response(self, response: str, profile: ClientProfile, intent: Dict) -> str:
        """Pós-processa a resposta para garantir qualidade"""
        
        # Remove possíveis repetições
        response = re.sub(r'(.+?)\1+', r'\1', response)
        
        # Garante que links só aparecem no fechamento
        if profile.conversation_stage != ConversationStage.FECHAMENTO:
            response = re.sub(r'https?://[^\s]+', '', response)
            
        # Limita tamanho da resposta
        if len(response) > 200:
            response = response[:200] + "..."
            
        return response.strip()

    async def send_whatsapp_message(self, phone: str, message: str) -> bool:
        """Envia mensagem via Maytapi"""
        url = f"https://api.maytapi.com/api/{self.whatsapp_product_id}/{self.whatsapp_phone_id}/sendMessage"
        
        headers = {
            "x-maytapi-key": self.whatsapp_token,
            "Content-Type": "application/json"
        }
        
        # Limpa o número de telefone
        clean_phone = re.sub(r'[^\d]', '', phone)
        if not clean_phone.startswith('351'):  # Adiciona código Portugal se necessário
            clean_phone = f"351{clean_phone}"
        
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
        """Processa mensagem recebida e responde automaticamente"""
        try:
            logger.info(f"📥 Mensagem recebida de {phone}: {message[:50]}...")
            
            # Gera resposta inteligente
            ai_response = await self.generate_intelligent_response(phone, message)
            
            logger.info(f"🤖 Resposta gerada: {ai_response[:50]}...")
            
            # Envia resposta
            success = await self.send_whatsapp_message(phone, ai_response)
            
            if success:
                # Verifica potencial conversão
                profile = self.client_profiles.get(phone)
                if profile and profile.conversion_score > 0.7:
                    logger.info(f"🎯 ALTA CHANCE DE CONVERSÃO: {phone} (Score: {profile.conversion_score:.2f})")
                    
                if "stripe.com" in ai_response or "buy." in ai_response:
                    logger.info(f"💰 LINK DE PAGAMENTO ENVIADO para {phone}")
                    self.register_conversion_attempt(phone)
                    
        except Exception as e:
            logger.error(f"❌ Erro ao processar mensagem de {phone}: {e}")

    def register_conversion_attempt(self, phone: str):
        """Registra tentativa de conversão"""
        profile = self.client_profiles.get(phone)
        if profile:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO conversions (phone, product, value, timestamp)
                VALUES (?, ?, ?, ?)
            ''', (phone, "tentativa", 0, datetime.now()))
            self.conn.commit()

    def save_to_database(self, phone: str, message: str, response: str, profile: ClientProfile):
        """Salva conversa no banco de dados"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO conversations (phone, message, response, stage, conversion_score)
                VALUES (?, ?, ?, ?, ?)
            ''', (phone, message, response, profile.conversation_stage.value, profile.conversion_score))
            
            # Atualiza perfil do cliente
            cursor.execute('''
                INSERT OR REPLACE INTO client_profiles (phone, location, conversion_score, last_interaction)
                VALUES (?, ?, ?, ?)
            ''', (phone, profile.location, profile.conversion_score, datetime.now()))
            
            self.conn.commit()
        except Exception as e:
            logger.error(f"Erro ao salvar no banco: {e}")

    def get_analytics_summary(self) -> Dict:
        """Retorna resumo analítico das conversas"""
        cursor = self.conn.cursor()
        
        try:
            # Estatísticas básicas
            cursor.execute("SELECT COUNT(DISTINCT phone) FROM conversations WHERE date(timestamp) = date('now')")
            clients_today = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(DISTINCT phone) FROM conversations")
            total_clients = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM conversions WHERE product != 'tentativa'")
            real_conversions = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM conversions WHERE product = 'tentativa'")
            conversion_attempts = cursor.fetchone()[0]
            
            # Taxa de conversão
            conversion_rate = (real_conversions / total_clients * 100) if total_clients > 0 else 0
            
            # Clientes por estágio
            cursor.execute("SELECT stage, COUNT(*) FROM conversations WHERE date(timestamp) = date('now') GROUP BY stage")
            today_stages = dict(cursor.fetchall())
            
            return {
                "clients_today": clients_today,
                "total_clients": total_clients,
                "real_conversions": real_conversions,
                "conversion_attempts": conversion_attempts,
                "conversion_rate": f"{conversion_rate:.1f}%",
                "today_stages": today_stages,
                "status": "🟢 Sistema funcionando"
            }
            
        except Exception as e:
            logger.error(f"Erro analytics: {e}")
            return {"error": str(e), "status": "🔴 Erro no sistema"}

# FastAPI Application
app = FastAPI(title="🤖 Atendente Virtual WhatsApp", version="1.0")

# Inicialização global
ai_assistant = WhatsAppAI()

class MaytapiWebhook(BaseModel):
    """Modelo para webhook do Maytapi"""
    type: str
    data: Dict

@app.post("/webhook")
async def receive_whatsapp_message(webhook: MaytapiWebhook):
    """Recebe mensagens do Maytapi webhook"""
    try:
        if webhook.type == "message":
            data = webhook.data
            
            # Extrai informações da mensagem
            phone = data.get("fromNumber", "")
            message_text = data.get("message", "")
            message_type = data.get("type", "")
            
            # Só processa mensagens de texto
            if message_type == "text" and message_text and phone:
                logger.info(f"📨 Nova mensagem de {phone}")
                await ai_assistant.process_incoming_message(phone, message_text)
                
        return {"status": "success", "message": "Processado com sucesso"}
        
    except Exception as e:
        logger.error(f"❌ Erro no webhook: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/webhook")
async def verify_webhook(request: Request):
    """Verificação do webhook (se necessário)"""
    return {"status": "Webhook ativo", "timestamp": datetime.now()}

@app.get("/")
async def dashboard():
    """Dashboard principal"""
    analytics = ai_assistant.get_analytics_summary()
    
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
        </style>
    </head>
    <body>
        <h1>🤖 Atendente Virtual - Dashboard</h1>
        
        <div class="card">
            <h2>📊 Estatísticas de Hoje</h2>
            <div class="status">{analytics.get('status', 'Carregando...')}</div>
            <p>Clientes hoje: <span class="metric">{analytics.get('clients_today', 0)}</span></p>
            <p>Total de clientes: <span class="metric">{analytics.get('total_clients', 0)}</span></p>
            <p>Taxa de conversão: <span class="metric">{analytics.get('conversion_rate', '0%')}</span></p>
        </div>
        
        <div class="card">
            <h2>🎯 Performance</h2>
            <p>Conversões realizadas: <span class="metric">{analytics.get('real_conversions', 0)}</span></p>
            <p>Links enviados: <span class="metric">{analytics.get('conversion_attempts', 0)}</span></p>
        </div>
        
        <div class="card">
            <h2>⚙️ Sistema</h2>
            <p>Status: <span class="metric">🟢 Online</span></p>
            <p>Última atualização: <span class="metric">{datetime.now().strftime('%H:%M:%S')}</span></p>
        </div>
        
        <div class="card">
            <h2>🔗 Endpoints Úteis</h2>
            <p><a href="/analytics">📊 Analytics JSON</a></p>
            <p><a href="/test-message?phone=351912345678&message=Oi">🧪 Testar Mensagem</a></p>
        </div>
    </body>
    </html>
    """
    
    return HTMLResponse(html)

@app.get("/analytics")
async def get_analytics():
    """Endpoint JSON com analytics"""
    return ai_assistant.get_analytics_summary()

@app.get("/test-message")
async def test_ai_response(phone: str = "351912345678", message: str = "Oi tudo bem"):
    """Endpoint para testar a IA sem WhatsApp"""
    try:
        response = await ai_assistant.generate_intelligent_response(phone, message)
        profile = ai_assistant.client_profiles.get(phone)
        
        return {
            "success": True,
            "user_message": message,
            "ai_response": response,
            "client_profile": {
                "stage": profile.conversation_stage.value if profile else "inicial",
                "score": profile.conversion_score if profile else 0.0,
                "messages_count": profile.messages_count if profile else 0,
                "location": profile.location if profile else None
            }
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

# Importação adicional para HTML response
from fastapi.responses import HTMLResponse

if __name__ == "__main__":
    import uvicorn
    
    print("=" * 60)
    print("🤖 ATENDENTE VIRTUAL INTELIGENTE")
    print("=" * 60)
    print("📱 WhatsApp: Integrado via Maytapi")
    print("🧠 IA: GPT-4 Configurado") 
    print("📊 Analytics: Ativo")
    print("🎯 Taxa de Conversão Esperada: ~66%")
    print("=" * 60)
    print("🌐 Dashboard: http://localhost:8000")
    print("🧪 Teste: http://localhost:8000/test-message")
    print("📊 Analytics: http://localhost:8000/analytics")
    print("=" * 60)
    
    # Executa o servidor
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
