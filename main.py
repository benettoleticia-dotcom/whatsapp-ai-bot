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

# Configurações Evolution API - Gratuita e Open Source
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")  # URL da sua Evolution API
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "mude-me")  # Chave de autenticação
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "ana_bot")  # Nome da instância
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "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")

# Inicializa OpenAI
try:
    client = OpenAI(api_key=OPENAI_API_KEY)
    logger.info("✅ OpenAI client inicializado")
except Exception as e:
    logger.error(f"❌ Erro ao inicializar OpenAI: {e}")

# Sistema de memória com controle de pagamentos (mantido igual)
class PaymentMemorySystem:
    def __init__(self):
        self.user_data = {}
        self.conversations = {}
        self.payment_tracking = {}
        self.model_usage_stats = {
            'gpt-4o-mini': 0,
            'gpt-4o': 0, 
            'o1-preview': 0,
            'total_cost': 0.0
        }
        logger.info("✅ Sistema de memória com pagamentos inicializado")
    
    def get_user_profile(self, user_id):
        return self.user_data.get(user_id, {
            'user_id': user_id,
            'name': '',
            'location': '',
            'city': '',
            'messages_count': 0,
            'last_interaction': datetime.now(),
            'converted': False,
            'conversion_stage': 'initial',
            'asked_about_sex': False,
            'knows_about_packages': False,
            'made_country_joke': False,
            'link_sent': False,
            'package_interested': None,
            'awaiting_payment': False,
            'payment_confirmed': False
        })
    
    def update_user_profile(self, user_id, **kwargs):
        if user_id not in self.user_data:
            self.user_data[user_id] = self.get_user_profile(user_id)
        
        for key, value in kwargs.items():
            if value is not None:
                self.user_data[user_id][key] = value
        
        self.user_data[user_id]['last_interaction'] = datetime.now()
    
    def track_payment_intent(self, user_id, package_price):
        """Rastreia intenção de pagamento"""
        self.payment_tracking[user_id] = {
            'package': package_price,
            'timestamp': datetime.now(),
            'link_sent': True,
            'status': 'awaiting_payment'
        }
        logger.info(f"💰 Payment intent tracked: {user_id} - €{package_price}")
    
    def get_payment_status(self, user_id):
        """Retorna status do pagamento"""
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

# Bot adaptado para Evolution API
class AnaEvolutionBot:
    def __init__(self):
        self.memory = PaymentMemorySystem()
        self.max_context = 10
        
        # LINKS DE PAGAMENTO (mantidos iguais)
        self.payment_links = {
            19.90: "https://buy.stripe.com/5kA6qZ6rf6kSgQ8bIO",
            29.90: "https://buy.stripe.com/8wMdTreXLdNkeI08ww", 
            39.90: "https://buy.stripe.com/cN29Db5nbbFc43m9AJ",
            59.90: "https://buy.stripe.com/8x24gB2RE9tqdZQ9kZ6g80j"
        }
        
        # Configuração dos modelos (mantida igual)
        self.models = {
            'fast': {'name': 'gpt-4o-mini', 'cost_per_1k_tokens': 0.00015},
            'balanced': {'name': 'gpt-4o', 'cost_per_1k_tokens': 0.0025},
            'intelligent': {'name': 'o1-preview', 'cost_per_1k_tokens': 0.015}
        }
        
        # Todas as listas de mensagens mantidas iguais
        self.portuguese_cities = {
            'lisboa': 'Lisboa', 'porto': 'Porto', 'coimbra': 'Coimbra', 'braga': 'Braga',
            'aveiro': 'Aveiro', 'faro': 'Faro', 'cascais': 'Cascais', 'felgueiras': 'Felgueiras',
            'leiria': 'Leiria', 'setubal': 'Setúbal', 'vila nova de gaia': 'Vila Nova de Gaia'
        }
        
        self.subscriber_explanations = [
            "Claro amor! Somente assinar um conteúdo meu e podemos marcar algo. Impossível sair com alguém que nem meu assinante seja 😉",
            "Sim lindinho! Mas só saio com meus assinantes. Precisa ser cliente primeiro, aí podemos nos encontrar 😘",
            "Óbvio que sim! Mas tenho que te conhecer como cliente antes. Assinando qualquer pacote já podemos marcar 🔥",
            "Claro querido! Mas só com assinantes né. Não dá para sair com qualquer um, precisa ser meu cliente primeiro 😊",
            "Sim amor! Só que trabalho apenas com meus assinantes. Assim que virar cliente, podemos nos ver 💕"
        ]
        
        self.country_jokes = [
            "Portugal é um país, não uma cidade kkk! 😂 Perguntei qual CIDADE querido",
            "Kkk Portugal todo? 😅 Qual cidade específica amor?", 
            "Portugal inteiro? 😂 Me diz a cidade que você mora!",
            "Kkk país inteiro não né? 😄 Qual cidadezinha?",
            "Todo Portugal? 😂 Diz a cidade aí gato!"
        ]
        
        self.package_presentations = [
            "Trabalho com 4 pacotes: €19,90 / €29,90 / €39,90 / €59,90. Qualquer um que compres já podes ter encontros comigo depois 😘",
            "Tenho 4 opções: €19,90 / €29,90 / €39,90 / €59,90. Com qualquer pacote já podemos marcar nosso encontro amor 🔥",
            "São 4 pacotes disponíveis: €19,90 / €29,90 / €39,90 / €59,90. Escolhe um e já somos íntimos 😉",
            "Ofereço 4 planos: €19,90 / €29,90 / €39,90 / €59,90. Qualquer um garante nosso encontro especial 💕"
        ]
        
        self.payment_confirmations = [
            "Perfeito! Aqui está o link do pagamento:",
            "Excelente escolha! Link para pagamento:",
            "Boa! Segue o link:",
            "Ótima escolha querido! Link aqui:",
            "Perfeito amor! Aqui o pagamento:"
        ]
        
        self.awaiting_messages = [
            "Aguardo confirmação do pagamento 😘 Assim que processar, te mando acesso!",
            "Esperando o pagamento ser processado 💕 Te aviso quando confirmar!",
            "Aguardando confirmação 😉 Logo que processar, liberamos tudo!",
            "Esperando o pagamento 🔥 Te notifico assim que confirmar!",
            "Aguardo processamento 😘 Em breve liberamos seu acesso!"
        ]
        
        logger.info("✅ Bot adaptado para Evolution API inicializado")
    
    # Métodos de detecção mantidos iguais
    def detect_package_interest(self, message):
        """Detecta qual pacote o cliente quer"""
        message_lower = message.lower()
        
        if "19" in message or "primeiro" in message or "mais barato" in message or "menor" in message:
            return 19.90
        elif "29" in message or "segundo" in message:
            return 29.90  
        elif "39" in message or "terceiro" in message:
            return 39.90
        elif "59" in message or "quarto" in message or "maior" in message or "mais caro" in message:
            return 59.90
        
        return None
    
    def detect_purchase_intent(self, message):
        """Detecta intenção de compra"""
        message_lower = message.lower()
        
        purchase_keywords = [
            'quero', 'comprar', 'pagar', 'aceito', 'vamos', 'sim', 'ok', 
            'feito', 'topo', 'bora', 'interesse', 'compro', 'pago'
        ]
        
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
    
    def analyze_message_complexity(self, message, user_context):
        message_lower = message.lower()
        word_count = len(message.split())
        
        complex_words = ['mas', 'porém', 'problema', 'não sei', 'dúvida', 'caro', 'muito']
        objection_words = ['não posso', 'não tenho', 'depois', 'pensar', 'talvez']
        
        complexity_score = word_count * 0.05
        complexity_score += sum(1 for word in complex_words if word in message_lower) * 0.5
        complexity_score += sum(1 for word in objection_words if word in message_lower) * 1.0
        
        if complexity_score <= 0.5: return 'simple'
        elif complexity_score <= 1.2: return 'medium'
        else: return 'complex'
    
    def select_optimal_model(self, message, user_id):
        user_profile = self.memory.get_user_profile(user_id)
        complexity = self.analyze_message_complexity(message, user_profile)
        
        if complexity == 'simple': return 'fast'
        elif complexity == 'medium': return 'balanced'
        else: return 'intelligent'
    
    def analyze_conversation_context(self, user_id, message):
        profile = self.memory.get_user_profile(user_id)
        
        context = {
            'knows_location': bool(profile.get('city')),
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
        
        sex_keywords = ['sexo', 'transar', 'fazer', 'sair', 'encontrar', 'programa']
        context['asking_about_sex'] = any(keyword in message.lower() for keyword in sex_keywords)
        
        price_keywords = ['preço', 'valor', 'quanto', 'assinatura', 'pacote', 'plano']
        context['asking_about_prices'] = any(keyword in message.lower() for keyword in price_keywords)
        
        context['wants_to_buy'] = self.detect_purchase_intent(message)
        context['specific_package'] = self.detect_package_interest(message)
        
        return context
    
    def build_payment_prompt(self, user_id, message, context, message_type, model_tier):
        profile = self.memory.get_user_profile(user_id)
        user_location = profile.get('city')
        ai_location = user_location if user_location else "Porto"
        
        time_moods = {
            'morning': 'energética e carinhosa ☀️',
            'afternoon': 'relaxada e conversadora 😊',
            'evening': 'sedutora e direta 🌙', 
            'night': 'íntima e provocante 😘'
        }
        mood = time_moods.get(context['time_period'], 'natural')
        
        special_instructions = ""
        
        if context['location_info'] and context['location_info']['type'] == 'country_only' and not context['made_country_joke']:
            special_instructions += f"IMPORTANTE: Cliente disse só 'Portugal'. Faz piada: '{random.choice(self.country_jokes)}' e depois diz que moras na mesma cidade."
        
        if context['asking_about_sex'] and not context['asked_about_sex']:
            special_instructions += f"IMPORTANTE: Cliente perguntou sobre sexo. Responde: '{random.choice(self.subscriber_explanations)}'"
        
        if context['asking_about_prices'] and not context['knows_about_packages']:
            special_instructions += f"IMPORTANTE: Cliente perguntou sobre preços. Apresenta: '{random.choice(self.package_presentations)}' e pergunta qual interessa."
        
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
                special_instructions += f"IMPORTANTE: Cliente quer comprar! Apresenta os 4 pacotes e pergunta qual prefere: '{random.choice(self.package_presentations)}'"
        
        if context['awaiting_payment']:
            special_instructions += "IMPORTANTE: Cliente já tem pagamento pendente. Pergunta se já pagou ou precisa do link novamente."
        
        if message_type in ["image", "photo"]:
            special_instructions += "Cliente enviou FOTO! Reage: 'Que giro! 😍'"
        elif message_type == "audio":
            special_instructions += "Cliente enviou ÁUDIO. Menciona que ouviste e seja carinhosa."
        
        if model_tier == 'fast':
            prompt = f"""És Ana, portuguesa de {ai_location}. Trabalhas com conteúdo adulto.

AGORA: {mood}
SITUAÇÃO: Msg #{context['messages_count']+1} | Estágio: {context['stage']}

{special_instructions}

REGRAS:
• Português natural, máximo 2 linhas
• Se pergunta preços = mostra 4 pacotes
• Se quer comprar = envia link + aguarda confirmação
• Varia respostas sempre

PACOTES: €19,90 / €29,90 / €39,90 / €59,90
REGRA: Só saio com assinantes

Resposta natural:"""
        else:
            prompt = f"""És Ana, portuguesa inteligente de {ai_location}. Trabalhas com conteúdo adulto.

PERSONALIDADE: {mood}
CONTEXTO: Conversa #{context['messages_count']+1} | {context['stage']}

{special_instructions}

DIRETRIZES:
• Português de Portugal natural
• Máximo 2 linhas por mensagem  
• Varia linguagem sempre
• Emojis apropriados

SISTEMA DE VENDAS:
→ Pergunta preços = apresenta 4 pacotes
→ Quer comprar = envia link correspondente + aguarda confirmação
→ Cliente específico = link direto
→ Cliente geral = pergunta qual pacote

PACOTES DISPONÍVEIS:
€19,90 / €29,90 / €39,90 / €59,90 - Todos dão direito a encontros

PROCESSO DE VENDA:
1. Apresenta pacotes
2. Cliente escolhe  
3. Envia link
4. "Aguardo confirmação do pagamento 😘"

Resposta inteligente:"""
        
        return prompt

    # FUNÇÃO PRINCIPAL: Envio via Evolution API
    async def send_evolution_message(self, phone: str, message: str):
        """Envia mensagem via Evolution API - Gratuita"""
        try:
            # URL da Evolution API para envio de texto
            url = f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}"
            
            headers = {
                "Content-Type": "application/json",
                "apikey": EVOLUTION_API_KEY
            }
            
            # Limpa o número de telefone (Evolution aceita formato internacional)
            clean_phone = phone.replace("@c.us", "").replace("+", "").replace("-", "").replace(" ", "")
            if not clean_phone.startswith("55"):
                clean_phone = "55" + clean_phone
            
            payload = {
                "number": clean_phone,
                "text": message
            }

            async with httpx.AsyncClient(timeout=30.0) as client_http:
                response = await client_http.post(url, headers=headers, json=payload)
                
                if response.status_code == 200 or response.status_code == 201:
                    logger.info(f"✅ Evolution API enviado: {message[:40]}...")
                    return True
                else:
                    logger.error(f"❌ Erro Evolution API: {response.status_code} - {response.text}")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ Exceção envio Evolution API: {e}")
            return False

    async def send_multiple_messages_evolution(self, phone: str, messages: list):
        """Envia múltiplas mensagens via Evolution API com delays"""
        for i, message in enumerate(messages):
            if i > 0:
                delay = random.randint(10, 30)
                logger.info(f"⏰ Delay entre mensagens: {delay}s")
                await asyncio.sleep(delay)
            
            success = await self.send_evolution_message(phone, message)
            if not success:
                logger.error(f"❌ Falha na mensagem {i+1}/{len(messages)}")
                break
            
            await asyncio.sleep(2)

    # Método process_payment_flow mantido igual
    async def process_payment_flow(self, user_id, context):
        """Processa fluxo de pagamento automaticamente"""
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
                package_interested=package_price,
                conversion_stage='closing'
            )
            
            self.memory.track_payment_intent(user_id, package_price)
            
            logger.info(f"💰 PAYMENT FLOW: Link €{package_price} enviado para {user_id[-8:]}")
            
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

    def estimate_tokens_and_cost(self, prompt, response, model_name):
        prompt_tokens = len(prompt) // 4
        response_tokens = len(response) // 4
        total_tokens = prompt_tokens + response_tokens
        
        model_config = None
        for config in self.models.values():
            if config['name'] == model_name:
                model_config = config
                break
        
        if model_config:
            estimated_cost = (total_tokens / 1000) * model_config['cost_per_1k_tokens']
        else:
            estimated_cost = 0.001
        
        return total_tokens, estimated_cost

    # Método principal adaptado para Evolution API
    async def get_payment_response(self, user_id: str, user_message: str, message_type: str = "text"):
        """Sistema principal com pagamento automático - adaptado para Evolution API"""
        try:
            logger.info(f"💰 Processando Evolution API: {user_id[-8:]} | {message_type} | {user_message[:50]}...")
            
            context = self.analyze_conversation_context(user_id, user_message)
            model_tier = self.select_optimal_model(user_message, user_id)
            selected_model = self.models[model_tier]['name']
            
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
                    update_data['city'] = context['location_info']['city']
                    update_data['location'] = context['location_info']['location']
            
            if context['asking_about_sex']:
                update_data['asked_about_sex'] = True
            if context['asking_about_prices']:
                update_data['knows_about_packages'] = True
            
            self.memory.update_user_profile(user_id, **update_data)
            
            prompt = self.build_payment_prompt(user_id, user_message, context, message_type, model_tier)
            
            processed_message = user_message
            if message_type == "audio":
                processed_message = f"[Cliente enviou áudio: {user_message}]"
            elif message_type in ["image", "photo"]:
                processed_message = f"[Cliente enviou foto{f' com legenda: {user_message}' if user_message.strip() else ''}]"
            elif message_type == "video":
                processed_message = f"[Cliente enviou vídeo{f': {user_message}' if user_message.strip() else ''}]"
            
            model_params = {
                'gpt-4o-mini': {'temperature': 0.9, 'max_tokens': 250},
                'gpt-4o': {'temperature': 0.8, 'max_tokens': 350},
                'o1-preview': {'temperature': 1.0, 'max_tokens': 450}
            }
            params = model_params.get(selected_model, model_params['gpt-4o-mini'])
            
            try:
                response = client.chat.completions.create(
                    model=selected_model,
                    messages=[
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": processed_message}
                    ],
                    **params,
                    frequency_penalty=0.6,
                    presence_penalty=0.4
                )
                
                reply = response.choices[0].message.content.strip()
                
                total_tokens, estimated_cost = self.estimate_tokens_and_cost(prompt, reply, selected_model)
                self.memory.log_model_usage(selected_model, total_tokens, estimated_cost)
                
            except Exception as e:
                logger.error(f"❌ Erro {selected_model}: {e}")
                fallback_response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "És Ana, portuguesa. Responde natural."},
                        {"role": "user", "content": user_message}
                    ],
                    temperature=0.9,
                    max_tokens=200
                )
                reply = fallback_response.choices[0].message.content.strip()
                self.memory.log_model_usage("gpt-4o-mini", 300, 0.0003)
            
            messages = await self.split_message(reply)
            
            if any("€" in msg for msg in messages):
                logger.info(f"💰 PRICING: Pacotes apresentados para {user_id[-8:]}")
            
            if any("diferença" in msg.lower() or "inclui" in msg.lower() for msg in messages):
                logger.info(f"📋 COMPARISON: Diferenças explicadas para {user_id[-8:]}")
            
            if any("stripe.com" in msg for msg in messages):
                logger.info(f"🔗 PAYMENT LINK: Link enviado para {user_id[-8:]}")
            
            logger.info(f"✅ Resposta {model_tier}: {len(messages)} msgs")
            return messages

        except Exception as e:
            logger.error(f"💥 Erro geral: {e}")
            return ["Oi querido, tive um probleminha técnico. Podes tentar de novo? 😊"]

    # TRANSCRIÇÃO DE ÁUDIO PARA EVOLUTION API
    async def transcribe_audio_evolution(self, audio_url):
        """Transcrição de áudio adaptada para Evolution API"""
        try:
            logger.info(f"🎵 Transcrevendo áudio Evolution: {audio_url}")
            
            async with httpx.AsyncClient(timeout=90.0) as client_http:
                audio_response = await client_http.get(audio_url)
                if audio_response.status_code == 200:
                    audio_filename = f"temp_audio_{random.randint(1000,9999)}.ogg"
                    with open(audio_filename, "wb") as f:
                        f.write(audio_response.content)
                    
                    logger.info(f"🎵 Áudio baixado: {len(audio_response.content)} bytes")
                    
                    with open(audio_filename, "rb") as audio_file:
                        transcription = client.audio.transcriptions.create(
                            model="whisper-1",
                            file=audio_file,
                            language="pt"
                        )
                    
                    os.remove(audio_filename)
                    
                    transcribed_text = transcription.text
                    logger.info(f"🎵 Áudio transcrito: {transcribed_text[:100]}...")
                    return transcribed_text
                else:
