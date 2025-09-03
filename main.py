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
logger = logging.getLogger("ana_payment")

app = FastAPI()

# Configurações
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

# Sistema de memória com controle de pagamentos
class PaymentMemorySystem:
    def __init__(self):
        self.user_data = {}
        self.conversations = {}
        self.payment_tracking = {}  # Rastreia processo de pagamento
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

# Bot com sistema de pagamento automático
class AnaPaymentBot:
    def __init__(self):
        self.memory = PaymentMemorySystem()
        self.max_context = 10
        
        # LINKS DE PAGAMENTO CONFIGURADOS
        self.payment_links = {
            19.90: "https://buy.stripe.com/5kA6qZ6rf6kSgQ8bIO",
            29.90: "https://buy.stripe.com/8wMdTreXLdNkeI08ww", 
            39.90: "https://buy.stripe.com/cN29Db5nbbFc43m9AJ",
            59.90: "https://buy.stripe.com/8x24gB2RE9tqdZQ9kZ6g80j"
        }
        
        # Configuração dos modelos
        self.models = {
            'fast': {'name': 'gpt-4o-mini', 'cost_per_1k_tokens': 0.00015},
            'balanced': {'name': 'gpt-4o', 'cost_per_1k_tokens': 0.0025},
            'intelligent': {'name': 'o1-preview', 'cost_per_1k_tokens': 0.015}
        }
        
        # Cidades portuguesas
        self.portuguese_cities = {
            'lisboa': 'Lisboa', 'porto': 'Porto', 'coimbra': 'Coimbra', 'braga': 'Braga',
            'aveiro': 'Aveiro', 'faro': 'Faro', 'cascais': 'Cascais', 'felgueiras': 'Felgueiras',
            'leiria': 'Leiria', 'setubal': 'Setúbal', 'vila nova de gaia': 'Vila Nova de Gaia'
        }
        
        # Explicações sobre assinantes (corrigidas)
        self.subscriber_explanations = [
            "Claro amor! Somente assinar um conteúdo meu e podemos marcar algo. Impossível sair com alguém que nem meu assinante seja 😉",
            "Sim lindinho! Mas só saio com meus assinantes. Precisa ser cliente primeiro, aí podemos nos encontrar 😘",
            "Óbvio que sim! Mas tenho que te conhecer como cliente antes. Assinando qualquer pacote já podemos marcar 🔥",
            "Claro querido! Mas só com assinantes né. Não dá para sair com qualquer um, precisa ser meu cliente primeiro 😏",
            "Sim amor! Só que trabalho apenas com meus assinantes. Assim que virar cliente, podemos nos ver 💕"
        ]
        
        # Piadas sobre país vs cidade (corrigidas)
        self.country_jokes = [
            "Portugal é um país, não uma cidade kkk! 😂 Perguntei qual CIDADE querido",
            "Kkk Portugal todo? 😅 Qual cidade específica amor?", 
            "Portugal inteiro? 😂 Me diz a cidade que você mora!",
            "Kkk país inteiro não né? 😄 Qual cidadezinha?",
            "Todo Portugal? 😂 Diz a cidade aí gato!"
        ]
        
        # Mensagens de apresentação dos pacotes
        self.package_presentations = [
            "Trabalho com 4 pacotes: €19,90 / €29,90 / €39,90 / €59,90. Qualquer um que compres já podes ter encontros comigo depois 😘",
            "Tenho 4 opções: €19,90 / €29,90 / €39,90 / €59,90. Com qualquer pacote já podemos marcar nosso encontro amor 🔥",
            "São 4 pacotes disponíveis: €19,90 / €29,90 / €39,90 / €59,90. Escolhe um e já somos íntimos 😉",
            "Ofereço 4 planos: €19,90 / €29,90 / €39,90 / €59,90. Qualquer um garante nosso encontro especial 💕"
        ]
        
        # Mensagens de confirmação de pagamento
        self.payment_confirmations = [
            "Perfeito! Aqui está o link do pagamento:",
            "Excelente escolha! Link para pagamento:",
            "Boa! Segue o link:",
            "Ótima escolha querido! Link aqui:",
            "Perfeito amor! Aqui o pagamento:"
        ]
        
        # Mensagens aguardando confirmação
        self.awaiting_messages = [
            "Aguardo confirmação do pagamento 😘 Assim que processar, te mando acesso!",
            "Esperando o pagamento ser processado 💕 Te aviso quando confirmar!",
            "Aguardando confirmação 😉 Logo que processar, liberamos tudo!",
            "Esperando o pagamento 🔥 Te notifico assim que confirmar!",
            "Aguardo processamento 😘 Em breve liberamos seu acesso!"
        ]
        
        logger.info("✅ Bot com sistema de pagamento inicializado")
    
    def detect_package_interest(self, message):
        """Detecta qual pacote o cliente quer"""
        message_lower = message.lower()
        
        # Detecta interesse específico em pacotes
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
        
        # Detecta perguntas sobre sexo
        sex_keywords = ['sexo', 'transar', 'fazer', 'sair', 'encontrar', 'programa']
        context['asking_about_sex'] = any(keyword in message.lower() for keyword in sex_keywords)
        
        # Detecta perguntas sobre preços
        price_keywords = ['preço', 'valor', 'quanto', 'assinatura', 'pacote', 'plano']
        context['asking_about_prices'] = any(keyword in message.lower() for keyword in price_keywords)
        
        # NOVO: Detecta intenção de compra
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
        
        # Instruções especiais baseadas no contexto
        special_instructions = ""
        
        # Piada do país
        if context['location_info'] and context['location_info']['type'] == 'country_only' and not context['made_country_joke']:
            special_instructions += f"IMPORTANTE: Cliente disse só 'Portugal'. Faz piada: '{random.choice(self.country_jokes)}' e depois diz que moras na mesma cidade."
        
        # Explicação sobre assinantes
        if context['asking_about_sex'] and not context['asked_about_sex']:
            special_instructions += f"IMPORTANTE: Cliente perguntou sobre sexo. Responde: '{random.choice(self.subscriber_explanations)}'"
        
        # Apresentação dos pacotes
        if context['asking_about_prices'] and not context['knows_about_packages']:
            special_instructions += f"IMPORTANTE: Cliente perguntou sobre preços. Apresenta: '{random.choice(self.package_presentations)}' e pergunta qual interessa."
        
        # NOVO: Sistema de pagamento automático
        if context['wants_to_buy'] and not context['link_sent']:
            if context['specific_package']:
                # Cliente escolheu pacote específico
                package_price = context['specific_package']
                payment_link = self.payment_links[package_price]
                special_instructions += f"""
IMPORTANTE: Cliente quer comprar €{package_price}!
1. Responde: '{random.choice(self.payment_confirmations)}'
2. Envia: '{payment_link}'
3. Depois: '{random.choice(self.awaiting_messages)}'
"""
            else:
                # Cliente quer comprar mas não especificou pacote
                special_instructions += f"IMPORTANTE: Cliente quer comprar! Apresenta os 4 pacotes e pergunta qual prefere: '{random.choice(self.package_presentations)}'"
        
        # Cliente aguardando pagamento
        if context['awaiting_payment']:
            special_instructions += "IMPORTANTE: Cliente já tem pagamento pendente. Pergunta se já pagou ou precisa do link novamente."
        
        # Contexto para mídia
        if message_type in ["image", "photo"]:
            special_instructions += "Cliente enviou FOTO! Reage: 'Que giro! 😍'"
        elif message_type == "audio":
            special_instructions += "Cliente enviou ÁUDIO. Menciona que ouviste e seja carinhosa."
        
        # Prompt otimizado
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
            
        elif model_tier == 'balanced':
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
            
        else:  # intelligent
            prompt = f"""Você é Ana, vendedora experiente portuguesa de {ai_location} especializada em conversão de leads.

ANÁLISE CONTEXTUAL:
- Estágio: {context['stage']}
- Cliente quer comprar: {context['wants_to_buy']}
- Pacote específico: {context['specific_package']}
- Link já enviado: {context['link_sent']}
- Aguardando pagamento: {context['awaiting_payment']}

{special_instructions}

SISTEMA DE CONVERSÃO AUTOMÁTICA:
- 4 pacotes: €19,90 / €29,90 / €39,90 / €59,90
- Links configurados para envio automático
- Processo: Interesse → Link → Confirmação → Conversão

ESTRATÉGIAS DE FECHAMENTO:
- Se demonstra interesse: acelera para pagamento
- Se hesita: reforça valor dos encontros
- Se questiona preço: mostra que é investimento
- Se já pagou: confirma e libera acesso

TÉCNICAS PSICOLÓGICAS:
- Escassez: "Não dá para sair com qualquer um"
- Urgência: "Assim que confirmar pagamento..."
- Reciprocidade: "Depois de cliente, nosso encontro"
- Social proof: "Meus clientes adoram"

Use inteligência superior para converter:"""
        
        return prompt

    async def process_payment_flow(self, user_id, context):
        """Processa fluxo de pagamento automaticamente"""
        messages_to_send = []
        
        # Se cliente quer comprar e escolheu pacote específico
        if context['wants_to_buy'] and context['specific_package'] and not context['link_sent']:
            package_price = context['specific_package']
            payment_link = self.payment_links[package_price]
            
            # Adiciona mensagens na sequência
            messages_to_send.append(random.choice(self.payment_confirmations))
            messages_to_send.append(payment_link)
            messages_to_send.append(random.choice(self.awaiting_messages))
            
            # Atualiza status
            self.memory.update_user_profile(user_id, 
                link_sent=True, 
                awaiting_payment=True,
                package_interested=package_price,
                conversion_stage='closing'
            )
            
            # Rastreia intenção de pagamento
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

    async def get_payment_response(self, user_id: str, user_message: str, message_type: str = "text"):
        """Sistema principal com pagamento automático"""
        try:
            logger.info(f"💰 Processando com pagamento: {user_id[-8:]} | {message_type} | {user_message[:50]}...")
            
            # Analisa contexto incluindo intenções de compra
            context = self.analyze_conversation_context(user_id, user_message)
            
            # Seleciona modelo
            model_tier = self.select_optimal_model(user_message, user_id)
            selected_model = self.models[model_tier]['name']
            
            # Determina estágio
            stage = context['stage']
            if context['asking_about_prices']: stage = 'pricing'
            elif context['asking_about_sex']: stage = 'explanation'
            elif context['wants_to_buy']: stage = 'closing'
            
            # Processa fluxo de pagamento automático PRIMEIRO
            payment_messages = await self.process_payment_flow(user_id, context)
            
            # Se gerou mensagens de pagamento, retorna elas
            if payment_messages:
                return payment_messages
            
            # Senão, continua com resposta normal
            update_data = {
                'messages_count': context['messages_count'] + 1,
                'conversion_stage': stage
            }
            
            # Atualiza localização
            if context['location_info']:
                if context['location_info']['type'] == 'country_only':
                    update_data['made_country_joke'] = True
                elif context['location_info']['type'] == 'city':
                    update_data['city'] = context['location_info']['city']
                    update_data['location'] = context['location_info']['location']
            
            # Marca interações importantes
            if context['asking_about_sex']:
                update_data['asked_about_sex'] = True
            if context['asking_about_prices']:
                update_data['knows_about_packages'] = True
            
            self.memory.update_user_profile(user_id, **update_data)
            
            # Constrói prompt
            prompt = self.build_payment_prompt(user_id, user_message, context, message_type, model_tier)
            
            # Processa mensagem
            processed_message = user_message
            if message_type == "audio":
                processed_message = f"[Cliente enviou áudio: {user_message}]"
            elif message_type in ["image", "photo"]:
                processed_message = f"[Cliente enviou foto{f' com legenda: {user_message}' if user_message.strip() else ''}]"
            elif message_type == "video":
                processed_message = f"[Cliente enviou vídeo{f': {user_message}' if user_message.strip() else ''}]"
            
            # Parâmetros do modelo
            model_params = {
                'gpt-4o-mini': {'temperature': 0.9, 'max_tokens': 250},
                'gpt-4o': {'temperature': 0.8, 'max_tokens': 350},
                'o1-preview': {'temperature': 1.0, 'max_tokens': 450}
            }
            params = model_params.get(selected_model, model_params['gpt-4o-mini'])
            
            # Gera resposta
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
            
            # Quebra mensagens
            messages = await self.split_message(reply)
            
            # Logs de conversão
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

    async def send_whatsapp_message(self, to: str, message: str):
        """Envia mensagem via Maytapi"""
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
        """Envia múltiplas mensagens com delays 10-30s"""
        for i, message in enumerate(messages):
            if i > 0:
                # Delay entre 10-30 segundos
                delay = random.randint(10, 30)
                logger.info(f"⏰ Delay entre mensagens: {delay}s")
                await asyncio.sleep(delay)
            
            success = await self.send_whatsapp_message(phone, message)
            if not success:
                logger.error(f"❌ Falha na mensagem {i+1}/{len(messages)}")
                break
            
            await asyncio.sleep(2)

    async def transcribe_audio(self, audio_url):
        """Transcrição de áudio melhorada"""
        try:
            logger.info(f"🎵 Transcrevendo áudio: {audio_url}")
            
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
                    logger.error(f"❌ Falha download áudio: {audio_response.status_code}")
            
            return "Não consegui baixar o áudio"
            
        except Exception as e:
            logger.error(f"❌ Erro transcrição: {e}")
            return "Recebi teu áudio mas não consegui processar"

# Instância global
ana_payment_bot = AnaPaymentBot()

@app.post("/webhook")
async def payment_webhook(request: Request):
    """Webhook com sistema de pagamento automático"""
    try:
        logger.info("💰 Webhook com sistema de pagamento recebido")
        
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
                logger.info(f"🎵 Processando áudio de {user_name}")
                user_message = await ana_payment_bot.transcribe_audio(audio_url)
                if not user_message or "não consegui" in user_message.lower():
                    user_message = "Recebi teu áudio mas houve problema na transcrição"
            else:
                user_message = "Recebi teu áudio"
        elif message_type in ["image", "video", "photo"]:
            caption = message_data.get("caption", "")
            user_message = caption
            logger.info(f"📸 {message_type}: {caption or 'sem legenda'}")
        else:
            logger.info(f"📋 Tipo não suportado: {message_type}")
            return {"status": "ignored"}

        # Log principal
        logger.info(f"👤 {user_name[:15]} | {phone[-8:]} | [{message_type}] {user_message[:80]}")

        # Delay inicial 10-30 segundos
        initial_delay = random.randint(10, 30)
        logger.info(f"⏰ Delay inicial: {initial_delay}s")
        await asyncio.sleep(initial_delay)
        
        # Gera resposta com sistema de pagamento
        messages = await ana_payment_bot.get_payment_response(phone, user_message, message_type)
        
        # Envia mensagens
        await ana_payment_bot.send_multiple_messages(phone, messages)
        
        # Verifica se foi conversão
        payment_status = ana_payment_bot.memory.get_payment_status(phone)
        is_payment_flow = any("stripe.com" in msg for msg in messages)
        
        return {
            "status": "success_with_payments",
            "messages_sent": len(messages),
            "delay_used": f"{initial_delay}s",
            "payment_flow_triggered": is_payment_flow,
            "payment_status": payment_status.get('status', 'no_payment'),
            "features": ["payments_automatic", "4_packages", "confirmation_tracking"]
        }

    except Exception as e:
        logger.error(f"💥 ERRO: {e}")
        return {"status": "error", "error": str(e)}

@app.get("/")
async def payment_dashboard():
    """Dashboard com sistema de pagamento"""
    try:
        stats = ana_payment_bot.memory.get_daily_stats()
        total_users = len(ana_payment_bot.memory.user_data)
        payment_intents = stats.get('payment_intents', 0)
        
        # Calcula conversões estimadas
        conversion_rate = (payment_intents / max(total_users, 1)) * 100
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>💰 Ana Bot - SISTEMA DE PAGAMENTO AUTOMÁTICO</title>
            <meta charset="utf-8">
            <style>
                body {{
                    font-family: 'Segoe UI', system-ui;
                    margin: 0;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    min-height: 100vh;
                }}
                .container {{
                    max-width: 1200px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .header {{
                    text-align: center;
                    margin-bottom: 30px;
                }}
                .cards {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
                    gap: 20px;
                    margin-bottom: 20px;
                }}
                .card {{
                    background: rgba(255,255,255,0.15);
                    backdrop-filter: blur(15px);
                    padding: 25px;
                    border-radius: 15px;
                    border: 2px solid rgba(255,255,255,0.3);
                }}
                .metric {{
                    font-size: 32px;
                    font-weight: bold;
                    color: #00ff88;
                    text-shadow: 0 0 10px rgba(0,255,136,0.5);
                }}
                .payment-link {{
                    background: rgba(0,0,0,0.3);
                    padding: 12px;
                    border-radius: 8px;
                    margin: 8px 0;
                    font-family: monospace;
                    font-size: 12px;
                    word-break: break-all;
                }}
                .feature {{
                    margin: 8px 0;
                    padding: 12px;
                    background: rgba(255,255,255,0.1);
                    border-radius: 8px;
                    border-left: 4px solid #00ff88;
                }}
                .status {{
                    display: inline-block;
                    padding: 6px 12px;
                    border-radius: 15px;
                    font-size: 14px;
                    font-weight: bold;
                    background: #00ff88;
                    color: #000;
                }}
                .pulse {{
                    animation: pulse 2s infinite;
                }}
                @keyframes pulse {{
                    0% {{ opacity: 1; }}
                    50% {{ opacity: 0.8; }}
                    100% {{ opacity: 1; }}
                }}
                .price {{
                    font-size: 24px;
                    font-weight: bold;
                    color: #ffd700;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 class="pulse">💰 ANA BOT - PAGAMENTO AUTOMÁTICO</h1>
                    <p>Sistema completo de conversão com links automáticos!</p>
                    <div class="status">PAGAMENTOS ATIVADOS</div>
                </div>
                
                <div class="cards">
                    <div class="card">
                        <h2>📊 Performance de Vendas</h2>
                        <p>Usuários Ativos: <span class="metric">{total_users}</span></p>
                        <p>Intenções de Pagamento: <span class="metric">{payment_intents}</span></p>
                        <p>Taxa de Conversão: <span class="metric">{conversion_rate:.1f}%</span></p>
                        <p>Chamadas IA: <span class="metric">{stats['total_calls']}</span></p>
                        <p>Custo Hoje: <span class="metric">${stats['total_cost']:.4f}</span></p>
                    </div>
                    
                    <div class="card">
                        <h2>💳 Links de Pagamento Configurados</h2>
                        <div class="feature">
                            <span class="price">€19,90</span><br>
                            <div class="payment-link">{ana_payment_bot.payment_links[19.90]}</div>
                        </div>
                        <div class="feature">
                            <span class="price">€29,90</span><br>
                            <div class="payment-link">{ana_payment_bot.payment_links[29.90]}</div>
                        </div>
                        <div class="feature">
                            <span class="price">€39,90</span><br>
                            <div class="payment-link">{ana_payment_bot.payment_links[39.90]}</div>
                        </div>
                        <div class="feature">
                            <span class="price">€59,90</span><br>
                            <div class="payment-link">{ana_payment_bot.payment_links[59.90]}</div>
                        </div>
                    </div>
                    
                    <div class="card">
                        <h2>🤖 Fluxo de Conversão Automático</h2>
                        <div class="feature">1️⃣ Cliente demonstra interesse</div>
                        <div class="feature">2️⃣ Ana apresenta 4 pacotes automaticamente</div>
                        <div class="feature">3️⃣ Cliente escolhe ou Ana detecta preferência</div>
                        <div class="feature">4️⃣ Link de pagamento enviado automaticamente</div>
                        <div class="feature">5️⃣ Mensagem "Aguardo confirmação" automática</div>
                        <div class="feature">6️⃣ Status rastreado no sistema</div>
                    </div>
                    
                    <div class="card">
                        <h2>🎯 Gatilhos de Detecção</h2>
                        <div class="feature"><strong>Interesse Geral:</strong> "quero", "comprar", "aceito", "vamos", "sim"</div>
                        <div class="feature"><strong>Pacote €19,90:</strong> "19", "primeiro", "mais barato", "menor"</div>
                        <div class="feature"><strong>Pacote €29,90:</strong> "29", "segundo"</div>
                        <div class="feature"><strong>Pacote €39,90:</strong> "39", "terceiro"</div>
                        <div class="feature"><strong>Pacote €59,90:</strong> "59", "quarto", "maior", "mais caro"</div>
                    </div>
                    
                    <div class="card">
                        <h2>✅ Todas as Correções Mantidas</h2>
                        <div class="feature">🕐 Delays 10-30 segundos</div>
                        <div class="feature">🎵 Transcrição áudio melhorada</div>
                        <div class="feature">😂 Piadas automáticas "Portugal vs cidade"</div>
                        <div class="feature">🔥 5 variações explicação assinantes</div>
                        <div class="feature">💰 Sistema 4 pacotes completo</div>
                        <div class="feature">🤖 IA híbrida com seleção de modelos</div>
                    </div>
                    
                    <div class="card">
                        <h2>🎛️ Mensagens Automáticas</h2>
                        <p><strong>Confirmação:</strong> "Perfeito! Aqui está o link do pagamento:"</p>
                        <p><strong>Aguardando:</strong> "Aguardo confirmação do pagamento 😘 Assim que processar, te mando acesso!"</p>
                        <p><strong>Apresentação:</strong> "Trabalho com 4 pacotes: €19,90 / €29,90 / €39,90 / €59,90"</p>
                    </div>
                </div>
                
                <div class="card">
                    <h2>🚀 Como Testar o Sistema</h2>
                    <p>1️⃣ <strong>Pergunta preços:</strong> "Quanto custa?" → Ana mostra 4 pacotes</p>
                    <p>2️⃣ <strong>Escolha específica:</strong> "Quero o de €19,90" → Link automático</p>
                    <p>3️⃣ <strong>Interesse geral:</strong> "Quero comprar" → Ana pergunta qual pacote</p>
                    <p>4️⃣ <strong>Verificar aguardo:</strong> Ana sempre diz que aguarda confirmação</p>
                    <p>5️⃣ <strong>Teste variações:</strong> Perguntas similares → Respostas diferentes</p>
                </div>
                
                <div class="card">
                    <h2>📈 ROI Projetado</h2>
                    <p>Com {payment_intents} intenções de pagamento hoje:</p>
                    <p>• Conversão 50% = {payment_intents * 0.5:.0f} vendas</p>
                    <p>• Ticket médio €35 = €{payment_intents * 0.5 * 35:.0f} receita estimada</p>
                    <p>• Custo IA: ${stats['total_cost']:.2f} (R$ {stats['total_cost'] * 5.5:.2f})</p>
                    <p>• ROI: <span class="metric">{((payment_intents * 0.5 * 35 * 5.5) / max(stats['total_cost'] * 5.5, 0.01)):.0f}x</span></p>
                </div>
            </div>
            
            <script>
                setTimeout(() => location.reload(), 30000);
            </script>
        </body>
        </html>
        """
        
        return HTMLResponse(html)
        
    except Exception as e:
        return HTMLResponse(f"<h1>Erro: {e}</h1>")

@app.get("/payments")
async def payment_status():
    """Status dos pagamentos em tempo real"""
    payment_tracking = ana_payment_bot.memory.payment_tracking
    
    active_payments = []
    for user_id, payment_info in payment_tracking.items():
        active_payments.append({
            "user": user_id[-8:],
            "package": f"€{payment_info['package']}",
            "status": payment_info['status'],
            "timestamp": payment_info['timestamp'].strftime('%H:%M:%S'),
            "link_sent": payment_info['link_sent']
        })
    
    return {
        "active_payments": active_payments,
        "total_payment_intents": len(payment_tracking),
        "system_status": "operational"
    }

@app.get("/health")
async def health():
    """Health check com info de pagamentos"""
    return {
        "status": "healthy_with_payments",
        "timestamp": datetime.now(),
        "features": ["automatic_payments", "4_packages", "link_tracking"],
        "payment_links_configured": len(ana_payment_bot.payment_links)
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    logger.info("🚀 ANA BOT - SISTEMA DE PAGAMENTO AUTOMÁTICO INICIANDO")
    logger.info("💳 4 links de pagamento configurados:")
    for price, link in ana_payment_bot.payment_links.items():
        logger.info(f"   €{price}: {link[:50]}...")
    logger.info("✅ Detecção automática de interesse")
    logger.info("✅ Links enviados automaticamente") 
    logger.info("✅ Confirmação de pagamento rastreada")
    logger.info("✅ Todas as correções anteriores mantidas")
    logger.info("🎯 Sistema completo de conversão ativado!")
    uvicorn.run(app, host="0.0.0.0", port=port)
