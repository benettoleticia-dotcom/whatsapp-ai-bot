from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import os
import hashlib
import hmac
import random
import re
import json
from datetime import datetime, timedelta
import asyncio
from telegram_client import send_telegram_message, start_telegram_client, stop_telegram_client, listen_for_messages

import logging

# Configuração de logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI()

# ADICIONAR AO MAIN.PY EXISTENTE

# CONFIGURAÇÃO DO SISTEMA DE ENTREGA
class AutoDeliverySystem:
    def __init__(self):
        # STRIPE WEBHOOK SECRET (para validar pagamentos reais)
        self.stripe_webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_sua_chave_aqui")
        
        # CONTEÚDOS ORGANIZADOS POR PACOTE
        self.content_packages = {
            19.90: {
                "name": "Pacote Básico",
                "photos": [
                    "https://drive.google.com/file/d/1abc.../view?usp=sharing",
                    "https://drive.google.com/file/d/2def.../view?usp=sharing",
                    # ... 18 links mais (total 20)
                ],
                "videos": [
                    "https://drive.google.com/file/d/3ghi.../view?usp=sharing",
                    "https://drive.google.com/file/d/4jkl.../view?usp=sharing", 
                    # ... 18 links mais (total 20)
                ],
                "welcome_message": "Bem-vindo ao meu conteúdo básico amor! 😘 Aqui estão suas 20 fotos + 20 vídeos exclusivos:",
                "access_duration": 365  # dias de acesso
            },
            29.90: {
                "name": "Pacote Intermediário", 
                "photos": [
                    # 40 links de fotos
                ],
                "videos": [
                    # 40 links de vídeos
                ],
                "welcome_message": "Parabéns pela escolha inteligente! 🔥 Aqui está seu pacote com 40 fotos + 40 vídeos:",
                "access_duration": 365,
                "bonus": "https://t.me/+LinkDoGrupoPrivado"  # Grupo Telegram premium
            },
            39.90: {
                "name": "Pacote Premium",
                "photos": [
                    # 80 links de fotos  
                ],
                "videos": [
                    # 80 links de vídeos
                ],
                "welcome_message": "Welcome to premium! 👑 Seu acesso completo com 80 fotos + 80 vídeos + chat exclusivo:",
                "chat_access": "https://wa.me/5542999999999?text=SouClientePremium",
                "video_call_booking": "https://calendly.com/ana-videocalls",
                "access_duration": 365
            },
            59.90: {
                "name": "Pacote VIP",
                "photos": "https://drive.google.com/drive/folders/PASTA_COMPLETA",
                "videos": "https://drive.google.com/drive/folders/PASTA_VIDEOS_VIP", 
                "welcome_message": "🚀 CLIENTE VIP ATIVADO! Acesso ILIMITADO a todo meu conteúdo:",
                "vip_telegram": "https://t.me/+GrupoVIPExclusivo",
                "priority_whatsapp": "https://wa.me/5542999999999?text=ClienteVIP",
                "discount_code": "VIP20OFF",  # 20% desconto em encontros
                "access_duration": -1  # Acesso vitalício
            }
        }
        
        # MENSAGENS DE ENTREGA AUTOMÁTICA
        self.delivery_messages = {
            "payment_confirmed": [
                "🎉 PAGAMENTO CONFIRMADO! Obrigada pela confiança amor!",
                "✅ Pagamento processado com sucesso! Preparando seu acesso...",
                "💕 Confirmado! Agora és oficialmente meu cliente querido!"
            ],
            "content_delivery": [
                "📱 Enviando seu conteúdo agora...",
                "🔥 Preparei tudo especialmente para ti!",
                "💫 Aqui está o que estavas esperando:"
            ],
            "access_instructions": [
                "📋 IMPORTANTE: Salva todos os links em local seguro!",
                "⚠️ Links são pessoais e intransferíveis",
                "💬 Qualquer problema, me chama no privado!"
            ]
        }
        
        logger.info("✅ Sistema de entrega automática inicializado")
    
    def verify_stripe_signature(self, payload, signature):
        """Verifica se webhook é realmente do Stripe"""
        try:
            expected_signature = hmac.new(
                self.stripe_webhook_secret.encode('utf-8'),
                payload,
                hashlib.sha256
            ).hexdigest()
            
            return hmac.compare_digest(f"sha256={expected_signature}", signature)
        except Exception as e:
            logger.error(f"❌ Erro verificação Stripe: {e}")
            return False
    
    def detect_payment_amount(self, stripe_data):
        """Extrai valor do pagamento do webhook Stripe"""
        try:
            # Stripe envia valor em centavos
            amount_cents = stripe_data.get('data', {}).get('object', {}).get('amount', 0)
            amount_euros = amount_cents / 100
            
            # Mapeia para nossos pacotes
            package_mapping = {
                1990: 19.90,  # €19,90 = 1990 centavos
                2990: 29.90,  # €29,90 = 2990 centavos
                3990: 39.90,  # €39,90 = 3990 centavos
                5990: 59.90   # €59,90 = 5990 centavos
            }
            
            return package_mapping.get(amount_cents, None)
        except Exception as e:
            logger.error(f"❌ Erro extraindo valor: {e}")
            return None
    
    def get_customer_phone(self, stripe_data):
        """Extrai telefone do cliente do webhook"""
        try:
            # Stripe pode ter o telefone em metadata ou customer
            customer_data = stripe_data.get('data', {}).get('object', {})
            
            # Procura em vários locais possíveis
            phone = (
                customer_data.get('metadata', {}).get('phone') or
                customer_data.get('customer_details', {}).get('phone') or
                customer_data.get('billing_details', {}).get('phone')
            )
            
            if phone:
                # Limpa e formata telefone
                clean_phone = re.sub(r'[^\d+]', '', phone)
                return clean_phone
            
            return None
        except Exception as e:
            logger.error(f"❌ Erro extraindo telefone: {e}")
            return None
    
    async def deliver_content_package(self, phone, package_price):
        """Entrega conteúdo automaticamente após confirmação"""
        try:
            package = self.content_packages.get(package_price)
            if not package:
                logger.error(f"❌ Pacote não encontrado: €{package_price}")
                return False
            
            logger.info(f"🚀 Iniciando entrega automática: €{package_price} para {phone[-8:]}")
            
            # 1. CONFIRMA PAGAMENTO
            confirmation_msg = random.choice(self.delivery_messages["payment_confirmed"])
            await send_telegram_message(1076029751, confirmation_msg)
            await asyncio.sleep(3)
            
            # 2. MENSAGEM DE PREPARAÇÃO
            preparation_msg = random.choice(self.delivery_messages["content_delivery"])
            await send_telegram_message(1076029751, preparation_msg)
            await asyncio.sleep(5)
            
            # 3. MENSAGEM DE BOAS-VINDAS
            welcome_msg = package["welcome_message"]
            await send_telegram_message(1076029751, welcome_msg)
            await asyncio.sleep(3)
            
            # 4. ENTREGA DO CONTEÚDO (baseado no pacote)
            if package_price == 59.90:
                # VIP: Pasta completa + acessos especiais
                await self.deliver_vip_content(phone, package)
            else:
                # Outros: Links individuais em lotes
                await self.deliver_standard_content(phone, package)
            
            # 5. INSTRUÇÕES FINAIS
            instructions = random.choice(self.delivery_messages["access_instructions"])
            await send_telegram_message(1076029751, instructions)
            
            # 6. ATUALIZA STATUS DO CLIENTE

            
            logger.info(f"✅ Conteúdo entregue com sucesso para {phone[-8:]}")
            return True
            
        except Exception as e:
            logger.error(f"💥 Erro na entrega: {e}")
            return False
    
    async def deliver_standard_content(self, phone, package):
        """Entrega conteúdo padrão (fotos + vídeos em lotes)"""
        try:
            # FOTOS (envia em lotes de 5)
            if 'photos' in package and isinstance(package['photos'], list):
                await send_telegram_message(1076029751, "📸 SUAS FOTOS EXCLUSIVAS:")
                await asyncio.sleep(2)
                
                photos = package['photos']
                for i in range(0, len(photos), 5):  # Lotes de 5
                    batch = photos[i:i+5]
                    batch_text = f"Fotos {i+1}-{i+len(batch)}:\n" + "\n".join(batch)
                    await send_telegram_message(1076029751, batch_text)
                    await asyncio.sleep(8)  # 8 segundos entre lotes
            
            # VÍDEOS (envia em lotes de 3)
            if 'videos' in package and isinstance(package['videos'], list):
                await send_telegram_message(1076029751, "🎥 SEUS VÍDEOS QUENTES:")
                await asyncio.sleep(2)
                
                videos = package['videos']
                for i in range(0, len(videos), 3):  # Lotes de 3
                    batch = videos[i:i+3]
                    batch_text = f"Vídeos {i+1}-{i+len(batch)}:\n" + "\n".join(batch)
                    await send_telegram_message(1076029751, batch_text)
                    await asyncio.sleep(10)  # 10 segundos entre lotes
            
            # BÔNUS (se houver)
            if 'bonus' in package:
                await asyncio.sleep(5)
                await send_telegram_message(1076029751, "🎁 BÔNUS ESPECIAL:")
                await send_telegram_message(1076029751, package['bonus'])
            
        except Exception as e:
            logger.error(f"❌ Erro entrega padrão: {e}")
    
    async def deliver_vip_content(self, phone, package):
        """Entrega conteúdo VIP (acesso completo + privilégios)"""
        try:
            # ACESSO COMPLETO ÀS PASTAS
            await send_telegram_message(1076029751, "📂 ACESSO COMPLETO ÀS MINHAS PASTAS:")
            await asyncio.sleep(2)
            
            await send_telegram_message(1076029751, f"📸 Todas as fotos: {package['photos']}")
            await asyncio.sleep(3)
            
            await send_telegram_message(1076029751, f"🎥 Todos os vídeos: {package['videos']}")
            await asyncio.sleep(3)
            
            # ACESSOS VIP
            await send_telegram_message(1076029751, "👑 PRIVILÉGIOS VIP ATIVADOS:")
            await asyncio.sleep(2)
            
            await send_telegram_message(1076029751, f"💬 Grupo VIP: {package['vip_telegram']}")
            await asyncio.sleep(3)
            
            await send_telegram_message(1076029751, f"📞 WhatsApp Priority: {package['priority_whatsapp']}")
            await asyncio.sleep(3)
            
            # CÓDIGO DE DESCONTO
            await send_telegram_message(1076029751, f"🎫 Seu código de desconto: {package['discount_code']}")
            await send_telegram_message(1076029751, "20% OFF em todos os encontros presenciais! 🔥")
            
        except Exception as e:
            logger.error(f"❌ Erro entrega VIP: {e}")
    
    async def schedule_followup(self, phone, package_price):
        """Agenda follow-up automático pós-entrega"""
        try:
            # Follow-up após 24h
            followup_messages = [
                "Oi amor! Conseguiste aceder a todo o conteúdo? Alguma dúvida? 😘",
                "Hey querido! Como está a curtir o material? Tudo funcionando bem? 💕",
                "Olá! Só para saber se está tudo ok com teu acesso! Beijos! 😉"
            ]
            
            # Implementar sistema de agendamento (pode usar APScheduler ou similar)
            # Por agora, apenas loga a intenção
            logger.info(f"📅 Follow-up agendado para {phone[-8:]} em 24h")
            
        except Exception as e:
            logger.error(f"❌ Erro agendando follow-up: {e}")

# INSTÂNCIA GLOBAL
delivery_system = AutoDeliverySystem()

# WEBHOOK STRIPE PARA CONFIRMAÇÃO DE PAGAMENTO
@app.post("/stripe-webhook")
async def stripe_webhook(request: Request):
    """Webhook do Stripe para confirmação automática de pagamento"""
    try:
        # Recebe payload do Stripe
        payload = await request.body()
        signature = request.headers.get("stripe-signature")
        
        if not signature:
            logger.error("❌ Webhook sem assinatura")
            return {"error": "No signature"}
        
        # Verifica se é realmente do Stripe
        if not delivery_system.verify_stripe_signature(payload, signature):
            logger.error("❌ Assinatura Stripe inválida")
            return {"error": "Invalid signature"}
        
        # Parse do JSON
        event_data = json.loads(payload)
        event_type = event_data.get("type")
        
        logger.info(f"🔔 Webhook Stripe recebido: {event_type}")
        
        # Processa apenas pagamentos confirmados
        if event_type in ["payment_intent.succeeded", "checkout.session.completed"]:
            
            # Extrai informações do pagamento
            package_price = delivery_system.detect_payment_amount(event_data)
            customer_phone = delivery_system.get_customer_phone(event_data)
            
            if package_price and customer_phone:
                logger.info(f"💰 PAGAMENTO CONFIRMADO: €{package_price} de {customer_phone[-8:]}")
                
                # ENTREGA AUTOMÁTICA IMEDIATA
                asyncio.create_task(
                    delivery_system.deliver_content_package(customer_phone, package_price)
                )
                
                # Agenda follow-up
                asyncio.create_task(
                    delivery_system.schedule_followup(customer_phone, package_price)
                )
                
                return {"status": "success", "delivered": True}
            else:
                logger.error(f"❌ Dados incompletos: preço={package_price}, telefone={customer_phone}")
                return {"status": "error", "message": "Incomplete data"}
        
        return {"status": "ignored"}
        
    except Exception as e:
        logger.error(f"💥 Erro webhook Stripe: {e}")
        return {"status": "error"}

# COMANDO MANUAL PARA TESTAR ENTREGA
@app.post("/test-delivery/{phone}/{package}")
async def test_delivery(phone: str, package: float):
    """Endpoint para testar entrega manual (APENAS PARA TESTES)"""
    try:
        logger.info(f"🧪 TESTE: Entrega manual €{package} para {phone}")
        
        success = await delivery_system.deliver_content_package(phone, package)
        
        return {
            "status": "test_completed",
            "delivered": success,
            "package": f"€{package}",
            "phone": phone[-8:]
        }
        
    except Exception as e:
        logger.error(f"❌ Erro teste entrega: {e}")
        return {"status": "error", "error": str(e)}

# DASHBOARD COM INFO DE ENTREGAS
@app.get("/deliveries")
async def delivery_dashboard():
    """Dashboard das entregas realizadas"""
    

from telegram_client import send_telegram_message, start_telegram_client, stop_telegram_client
import asyncio




async def telegram_message_handler(message):
    # Aqui você pode adicionar a lógica para processar as mensagens recebidas
    print(f"Mensagem recebida de {message.sender_id}: {message.text}")
    if message.text:
        # Exemplo de resposta: ecoar a mensagem
        await send_telegram_message(message.chat_id, f"Você disse: {message.text}")





@app.on_event("startup")
async def startup_event():
    await start_telegram_client()
    asyncio.create_task(listen_for_messages(telegram_message_handler))

@app.on_event("shutdown")
async def shutdown_event():
    await stop_telegram_client()


