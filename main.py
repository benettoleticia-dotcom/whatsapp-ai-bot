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

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ana_evolution")

app = FastAPI()

# Configurações Evolution API
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "https://evo-api.onrender.com")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "test123")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "ana_bot")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Inicializa OpenAI
try:
    client = OpenAI(api_key=OPENAI_API_KEY)
    logger.info("✅ OpenAI client inicializado")
except Exception as e:
    logger.error(f"❌ Erro ao inicializar OpenAI: {e}")

class PaymentMemorySystem:
    def __init__(self):
        self.user_data = {}
        self.payment_tracking = {}
        self.model_usage_stats = {
            'gpt-4o-mini': 0,
            'gpt-4o': 0, 
            'o1-preview': 0,
            'total_cost': 0.0
        }
        logger.info("✅ Sistema de memória inicializado")
    
    def get_user_profile(self, user_id):
        return self.user_data.get(user_id, {
            'user_id': user_id,
            'name': '',
            'messages_count': 0,
            'last_interaction': datetime.now(),
            'conversion_stage': 'initial',
            'asked_about_sex': False,
            'knows_about_packages': False,
            'made_country_joke': False,
            'link_sent': False,
            'awaiting_payment': False
        })
    
    def update_user_profile(self, user_id, **kwargs):
        if user_id not in self.user_data:
            self.user_data[user_id] = self.get_user_profile(user_id)
        
        for key, value in kwargs.items():
            if value is not None:
                self.user_data[user_id][key] = value
        
        self.user_data[user_id]['last_interaction'] = datetime.now()
    
    def track_payment_intent(self, user_id, package_price):
        self.payment_tracking[user_id] = {
            'package': package_price,
            'timestamp': datetime.now(),
            'link_sent': True,
            'status': 'awaiting_payment'
        }
        logger.info(f"💰 Payment intent tracked: {user_id} - €{package_price}")
    
    def get_payment_status(self, user_id):
        return self.payment_tracking.get(user_id, {})
    
    def log_model_usage(self, model, estimated_tokens, estimated_cost):
        self.model_usage_stats[model] += 1
        self.model_usage_stats['total_cost'] += estimated_cost
    
    def get_daily_stats(self):
        total_calls = sum(self.model_usage_stats[model] for model in ['gpt-4o-mini', 'gpt-4o', 'o1-preview'])
        payment_intents = len(self.payment_tracking)
        return {
            'total_calls': total_calls,
            'mini_usage': self.model_usage_stats['gpt-4o-mini'],
            'gpt4_usage': self.model_usage_stats['gpt-4o'],
            'o1_usage': self.model_usage_stats['o1-preview'],
            'total_cost': self.model_usage_stats['total_cost'],
            'payment_intents': payment_intents
        }

class AnaEvolutionBot:
    def __init__(self):
        self.memory = PaymentMemorySystem()
        
        self.payment_links = {
            19.90: "https://buy.stripe.com/5kA6qZ6rf6kSgQ8bIO",
            29.90: "https://buy.stripe.com/8wMdTreXLdNkeI08ww", 
            39.90: "https://buy.stripe.com/cN29Db5nbbFc43m9AJ",
            59.90: "https://buy.stripe.com/8x24gB2RE9tqdZQ9kZ6g80j"
        }
        
        self.models = {
            'fast': {'name': 'gpt-4o-mini', 'cost_per_1k_tokens': 0.00015},
            'balanced': {'name': 'gpt-4o', 'cost_per_1k_tokens': 0.0025},
            'intelligent': {'name': 'o1-preview', 'cost_per_1k_tokens': 0.015}
        }
        
        self.portuguese_cities = {
            'lisboa': 'Lisboa', 'porto': 'Porto', 'coimbra': 'Coimbra', 'braga': 'Braga',
            'aveiro': 'Aveiro', 'faro': 'Faro', 'cascais': 'Cascais'
        }
        
        self.subscriber_explanations = [
            "Claro amor! Somente assinar um conteúdo meu e podemos marcar algo. Impossível sair com alguém que nem meu assinante seja 😉",
            "Sim lindinho! Mas só saio com meus assinantes. Precisa ser cliente primeiro, aí podemos nos encontrar 😘",
            "Óbvio que sim! Mas tenho que te conhecer como cliente antes. Assinando qualquer pacote já podemos marcar 🔥"
        ]
        
        self.country_jokes = [
            "Portugal é um país, não uma cidade kkk! 😂 Perguntei qual CIDADE querido",
            "Kkk Portugal todo? 😅 Qual cidade específica amor?", 
            "Portugal inteiro? 😂 Me diz a cidade que você mora!"
        ]
        
        self.package_presentations = [
            "Trabalho com 4 pacotes: €19,90 / €29,90 / €39,90 / €59,90. Qualquer um que compres já podes ter encontros comigo depois 😘",
            "Tenho 4 opções: €19,90 / €29,90 / €39,90 / €59,90. Com qualquer pacote já podemos marcar nosso encontro amor 🔥"
        ]
        
        self.payment_confirmations = [
            "Perfeito! Aqui está o link do pagamento:",
            "Excelente escolha! Link para pagamento:",
            "Boa! Segue o link:"
        ]
        
        self.awaiting_messages = [
            "Aguardo confirmação do pagamento 😘 Assim que processar, te mando acesso!",
            "Esperando o pagamento ser processado 💕 Te aviso quando confirmar!"
        ]
        
        logger.info("✅ Bot Evolution API inicializado")
    
    def detect_package_interest(self, message):
        message_lower = message.lower()
        
        if "19" in message or "primeiro" in message or "mais barato" in message:
            return 19.90
        elif "29" in message or "segundo" in message:
            return 29.90  
        elif "39" in message or "terceiro" in message:
            return 39.90
        elif "59" in message or "quarto" in message or "maior" in message:
            return 59.90
        
        return None
    
    def detect_purchase_intent(self, message):
        message_lower = message.lower()
        purchase_keywords = ['quero', 'comprar', 'pagar', 'aceito', 'vamos', 'sim', 'ok']
        return any(keyword in message_lower for keyword in purchase_keywords)
    
    def get_current_time_period(self):
        current_hour = datetime.now().hour
        if 6 <= current_hour < 12: return 'morning'
        elif 12 <= current_hour < 18: return 'afternoon'
        elif 18 <= current_hour < 22: return 'evening'
        else: return 'night'
    
    def extract_location_info(self, message):
        message_lower = message.lower()
        
        if 'portugal' in message_lower and not any(city in message_lower for city in self.portuguese_cities.keys()):
            return {'type': 'country_only', 'location': 'Portugal', 'city': None}
        
        for city_key, city_name in self.portuguese_cities.items():
            if city_key in message_lower:
                return {'type': 'city', 'location': city_name, 'city': city_name}
        
        return None
    
    def analyze_conversation_context(self, user_id, message):
        profile = self.memory.get_user_profile(user_id)
        
        context = {
            'location_info': self.extract_location_info(message),
            'messages_count': profile.get('messages_count', 0),
            'stage': profile.get('conversion_stage', 'initial'),
            'time_period': self.get_current_time_period(),
            'asked_about_sex': profile.get('asked_about_sex', False),
            'knows_about_packages': profile.get('knows_about_packages', False),
            'made_country_joke': profile.get('made_country_joke', False),
            'link_sent': profile.get('link_sent', False),
            'awaiting_payment': profile.get('awaiting_payment', False)
        }
        
        sex_keywords = ['sexo', 'transar', 'fazer', 'sair', 'encontrar']
        context['asking_about_sex'] = any(keyword in message.lower() for keyword in sex_keywords)
        
        price_keywords = ['preço', 'valor', 'quanto', 'assinatura', 'pacote']
        context['asking_about_prices'] = any(keyword in message.lower() for keyword in price_keywords)
        
        context['wants_to_buy'] = self.detect_purchase_intent(message)
        context['specific_package'] = self.detect_package_interest(message)
        
        return context
    
    def build_prompt(self, user_id, message, context):
        profile = self.memory.get_user_profile(user_id)
        
        time_moods = {
            'morning': 'energética e carinhosa',
            'afternoon': 'relaxada e conversadora',
            'evening': 'sedutora e direta', 
            'night': 'íntima e provocante'
        }
        mood = time_moods.get(context['time_period'], 'natural')
        
        special_instructions = ""
        
        if context['location_info'] and context['location_info']['type'] == 'country_only' and not context['made_country_joke']:
            special_instructions += f"IMPORTANTE: Cliente disse só 'Portugal'. Faz piada: '{random.choice(self.country_jokes)}'"
        
        if context['asking_about_sex'] and not context['asked_about_sex']:
            special_instructions += f"IMPORTANTE: Cliente perguntou sobre sexo. Responde: '{random.choice(self.subscriber_explanations)}'"
        
        if context['asking_about_prices'] and not context['knows_about_packages']:
            special_instructions += f"IMPORTANTE: Cliente perguntou sobre preços. Apresenta: '{random.choice(self.package_presentations)}'"
        
        if context['wants_to_buy'] and not context['link_sent']:
            if context['specific_package']:
                package_price = context['specific_package']
                payment_link = self.payment_links[package_price]
                special_instructions += f"""
IMPORTANTE: Cliente quer comprar €{package_price}!
1. Responde: '{random.choice(self.payment_confirmations)}'
2. Envia: '{payment_link}'
3. Depois: '{random.choice(self.awaiting_messages)}'
"""
            else:
                special_instructions += f"IMPORTANTE: Cliente quer comprar! Apresenta os 4 pacotes: '{random.choice(self.package_presentations)}'"
        
        prompt = f"""És Ana, portuguesa do Porto. Trabalhas com conteúdo adulto.

PERSONALIDADE: {mood}
CONTEXTO: Conversa #{context['messages_count']+1}

{special_instructions}

REGRAS:
• Português de Portugal natural
• Máximo 2 linhas por mensagem
• Varia respostas sempre
• Emojis apropriados

PACOTES: €19,90 / €29,90 / €39,90 / €59,90
REGRA: Só saio com assinantes

Resposta natural:"""
        
        return prompt

    async def send_evolution_message(self, phone: str, message: str):
        try:
            url = f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}"
            
            headers = {
                "Content-Type": "application/json",
                "apikey": EVOLUTION_API_KEY
            }
            
            clean_phone = phone.replace("@c.us", "").replace("+", "").replace("-", "").replace(" ", "")
            if not clean_phone.startswith("55"):
                clean_phone = "55" + clean_phone
            
            payload = {
                "number": clean_phone,
                "text": message
            }

            async with httpx.AsyncClient(timeout=30.0) as client_http:
                response = await client_http.post(url, headers=headers, json=payload)
                
                if response.status_code in [200, 201]:
                    logger.info(f"✅ Evolution API enviado: {message[:40]}...")
                    return True
                else:
                    logger.error(f"❌ Erro Evolution API: {response.status_code}")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ Exceção envio Evolution API: {e}")
            return False

    async def send_multiple_messages(self, phone: str, messages: list):
        for i, message in enumerate(messages):
            if i > 0:
                delay = random.randint(10, 30)
                await asyncio.sleep(delay)
            
            success = await self.send_evolution_message(phone, message)
            if not success:
                break
            
            await asyncio.sleep(2)

    async def process_payment_flow(self, user_id, context):
        messages_to_send = []
        
        if context['wants_to_buy'] and context['specific_package'] and not context['link_sent']:
            package_price = context['specific_package']
            payment_link = self.payment_links[package_price]
            
            messages_to_send.append(random.choice(self.payment_confirmations))
            messages_to_send.append(payment_link)
            messages_to_send.append(random.choice(self.awaiting_messages))
            
            self.memory.update_user_profile(user_id, 
                link_sent=True, 
                awaiting_payment=True,
                conversion_stage='closing'
            )
            
            self.memory.track_payment_intent(user_id, package_price)
            
        return messages_to_send

    async def split_message(self, message):
        if len(message) <= 120:
            return [message]
        
        sentences = re.split(r'[.!?]\s+', message)
        messages = []
        current = ""
        
        for sentence in sentences:
            if len(current + sentence) <= 120:
                current += sentence + ". " if not sentence.endswith(('!', '?')) else sentence + " "
            else:
                if current:
                    messages.append(current.strip())
                current = sentence + ". " if not sentence.endswith(('!', '?')) else sentence + " "
        
        if current:
            messages.append(current.strip())
        
        return messages if messages else [message]

    async def get_payment_response(self, user_id: str, user_message: str, message_type: str = "text"):
        try:
            logger.info(f"💰 Processando: {user_id[-8:]} | {message_type} | {user_message[:50]}...")
            
            context = self.analyze_conversation_context(user_id, user_message)
            
            stage = context['stage']
            if context['asking_about_prices']: stage = 'pricing'
            elif context['asking_about_sex']: stage = 'explanation'
            elif context['wants_to_buy']: stage = 'closing'
            
            payment_messages = await self.process_payment_flow(user_id, context)
            
            if payment_messages:
                return payment_messages
            
            update_data = {
                'messages_count': context['messages_count'] + 1,
                'conversion_stage': stage
            }
            
            if context['location_info']:
                if context['location_info']['type'] == 'country_only':
                    update_data['made_country_joke'] = True
                elif context['location_info']['type'] == 'city':
                    update_data['location'] = context['location_info']['location']
            
            if context['asking_about_sex']:
                update_data['asked_about_sex'] = True
            if context['asking_about_prices']:
                update_data['knows_about_packages'] = True
            
            self.memory.update_user_profile(user_id, **update_data)
            
            prompt = self.build_prompt(user_id, user_message, context)
            
            try:
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": user_message}
                    ],
                    temperature=0.9,
                    max_tokens=250
                )
                
                reply = response.choices[0].message.content.strip()
                self.memory.log_model_usage("gpt-4o-mini", 300, 0.0003)
                
            except Exception as e:
                logger.error(f"❌ Erro OpenAI: {e}")
                reply = "Oi querido, tive um probleminha técnico. Podes tentar de novo? 😊"
            
            messages = await self.split_message(reply)
            
            if any("€" in msg for msg in messages):
                logger.info(f"💰 PRICING: Pacotes apresentados")
            
            if any("stripe.com" in msg for msg in messages):
                logger.info(f"🔗 PAYMENT LINK: Link enviado")
            
            return messages

        except Exception as e:
            logger.error(f"💥 Erro geral: {e}")
            return ["Oi querido, tive um probleminha técnico. Podes tentar de novo? 😊"]

# Instância global
ana_bot = AnaEvolutionBot()

@app.post("/webhook/evolution")
async def evolution_webhook(request: Request):
    try:
        logger.info("🚀 Webhook Evolution API recebido")
        
        data = await request.json()
        
        webhook_data = data.get("data", {})
        key_info = webhook_data.get("key", {})
        phone = key_info.get("remoteJid", "")
        from_me = key_info.get("fromMe", False)
        
        if from_me:
            return {"status": "ignored"}
        
        message_data = webhook_data.get("message", {})
        message_text = ""
        message_type = "text"
        
        if "conversation" in message_data:
            message_text = message_data["conversation"]
        elif "extendedTextMessage" in message_data:
            message_text = message_data["extendedTextMessage"]["text"]
        else:
            return {"status": "ignored"}

        if not phone or not message_text:
            return {"status": "ignored"}

        user_name = phone.split("@")[0][-8:] if "@" in phone else phone[-8:]
        logger.info(f"👤 {user_name} | {message_text[:50]}")

        initial_delay = random.randint(10, 30)
        await asyncio.sleep(initial_delay)
        
        messages = await ana_bot.get_payment_response(phone, message_text, message_type)
        await ana_bot.send_multiple_messages(phone, messages)
        
        payment_status = ana_bot.memory.get_payment_status(phone)
        is_payment_flow = any("stripe.com" in msg for msg in messages)
        
        return {
            "status": "success",
            "messages_sent": len(messages),
            "payment_flow_triggered": is_payment_flow,
            "platform": "evolution_api"
        }

    except Exception as e:
        logger.error(f"💥 ERRO: {e}")
        return {"status": "error", "error": str(e)}

@app.get("/")
async def dashboard():
    stats = ana_bot.memory.get_daily_stats()
    total_users = len(ana_bot.memory.user_data)
    payment_intents = stats.get('payment_intents', 0)
    
    conversion_rate = (payment_intents / max(total_users, 1)) * 100
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>🚀 Ana Bot - Evolution API</title>
        <meta charset="utf-8">
        <style>
            body {{
                font-family: 'Arial', sans-serif;
                margin: 0;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 20px;
            }}
            .container {{
                max-width: 800px;
                margin: 0 auto;
            }}
            .card {{
                background: rgba(255,255,255,0.15);
                padding: 20px;
                border-radius: 10px;
                margin: 20px 0;
            }}
            .metric {{
                font-size: 24px;
                font-weight: bold;
                color: #00ff88;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🚀 Ana Bot - Evolution API</h1>
            
            <div class="card">
                <h2>📊 Performance</h2>
                <p>Usuários: <span class="metric">{total_users}</span></p>
                <p>Pagamentos: <span class="metric">{payment_intents}</span></p>
                <p>Conversão: <span class="metric">{conversion_rate:.1f}%</span></p>
                <p>Chamadas IA: <span class="metric">{stats['total_calls']}</span></p>
            </div>
            
            <div class="card">
                <h2>⚙️ Configuração</h2>
                <p>API: {EVOLUTION_API_URL}</p>
                <p>Instância: {EVOLUTION_INSTANCE}</p>
                <p>Webhook: /webhook/evolution</p>
            </div>
            
            <div class="card">
                <h2>💳 Links Stripe</h2>
                <p>€19,90: {ana_bot.payment_links[19.90][:50]}...</p>
                <p>€29,90: {ana_bot.payment_links[29.90][:50]}...</p>
                <p>€39,90: {ana_bot.payment_links[39.90][:50]}...</p>
                <p>€59,90: {ana_bot.payment_links[59.90][:50]}...</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return HTMLResponse(html)

@app.get("/health")
async def health():
    return {
        "status": "healthy_evolution",
        "platform": "evolution_api",
        "timestamp": datetime.now(),
        "features": ["automatic_payments", "evolution_integration"],
        "cost": "FREE",
        "api_url": EVOLUTION_API_URL,
        "instance": EVOLUTION_INSTANCE
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    logger.info("🚀 ANA BOT - EVOLUTION API INICIANDO")
    logger.info(f"Evolution API: {EVOLUTION_API_URL}")
    logger.info(f"Instância: {EVOLUTION_INSTANCE}")
    logger.info("✅ Sistema de pagamentos ativo")
    uvicorn.run(app, host="0.0.0.0", port=port)
