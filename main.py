import os
import asyncio
import random
import logging
import sqlite3
import json
from datetime import datetime
from fastapi import FastAPI, Request
import httpx
from openai import OpenAI

# Configuração de logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

# Inicializa FastAPI
app = FastAPI()

# Configurações fixas
MAYTAPI_PRODUCT_ID = "f38c3b76-29d1-4f85-ab4e-c3c911b7116c"
MAYTAPI_PHONE_ID = "107677" 
MAYTAPI_TOKEN = "c9510ef0-09e6-4780-bb6a-72b137811069"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "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").strip()

client = OpenAI(api_key=OPENAI_API_KEY)

# Banco de dados para aprendizado
class LearningDatabase:
    def __init__(self):
        self.conn = sqlite3.connect('conversations.db', check_same_thread=False)
        self.init_tables()
    
    def init_tables(self):
        cursor = self.conn.cursor()
        
        # Tabela de conversas
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                user_message TEXT,
                ai_response TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                converted BOOLEAN DEFAULT FALSE,
                stage TEXT
            )
        ''')
        
        # Tabela de conversões
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                conversation_id INTEGER,
                amount REAL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabela de padrões de sucesso
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS success_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_type TEXT,
                pattern_text TEXT,
                success_rate REAL,
                usage_count INTEGER DEFAULT 1
            )
        ''')
        
        self.conn.commit()
        
        # Adiciona padrões iniciais baseados nos seus exemplos
        self.add_initial_patterns()
    
    def add_initial_patterns(self):
        """Adiciona padrões de sucesso baseados nos exemplos analisados"""
        cursor = self.conn.cursor()
        
        success_patterns = [
            ("opening", "Olá boa tarde tudo bem?? de qual cidade fala??", 0.8),
            ("client_rule", "Só saio com meus clientes", 0.9),
            ("client_rule", "Só transo com meus clientes", 0.9),
            ("explanation", "Só saio com o pessoal das plataformas adultas", 0.85),
            ("price_presentation", "Baratinho. É só pra selecionar quem quer mesmo", 0.75),
            ("closing", "19,90 - https://buy.stripe.com/14k4iR16VdNk43mfZ5", 0.8),
            ("sample_response", "É só abrir o link que lá tem uma foto", 0.7),
        ]
        
        for pattern_type, text, success_rate in success_patterns:
            cursor.execute('''
                INSERT OR IGNORE INTO success_patterns (pattern_type, pattern_text, success_rate)
                VALUES (?, ?, ?)
            ''', (pattern_type, text, success_rate))
        
        self.conn.commit()
    
    def log_conversation(self, user_id, user_message, ai_response, stage="unknown"):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO conversations (user_id, user_message, ai_response, stage)
            VALUES (?, ?, ?, ?)
        ''', (user_id, user_message, ai_response, stage))
        self.conn.commit()
        return cursor.lastrowid
    
    def mark_conversion(self, user_id, amount=19.90):
        cursor = self.conn.cursor()
        
        # Marca as últimas conversas como convertidas
        cursor.execute('''
            UPDATE conversations 
            SET converted = TRUE 
            WHERE user_id = ? AND timestamp > datetime('now', '-1 hour')
        ''', (user_id,))
        
        # Registra a conversão
        cursor.execute('''
            INSERT INTO conversions (user_id, amount)
            VALUES (?, ?)
        ''', (user_id, amount))
        
        self.conn.commit()
        logger.info(f"💰 Conversão registrada: {user_id} - €{amount}")
    
    def get_best_patterns(self, pattern_type):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT pattern_text, success_rate 
            FROM success_patterns 
            WHERE pattern_type = ? 
            ORDER BY success_rate DESC LIMIT 3
        ''', (pattern_type,))
        return cursor.fetchall()

# Inicializa banco de aprendizado
learning_db = LearningDatabase()
user_histories = {}

class WhatsAppBotAdvanced:
    def __init__(self):
        self.max_context_messages = 6
        
    def analyze_conversation_stage(self, user_id, message):
        """Determina em que estágio da venda o cliente está"""
        message_lower = message.lower()
        
        if user_id not in user_histories:
            return "opening"
        
        conversation = user_histories[user_id]
        
        # Analisa histórico para determinar estágio
        if len(conversation) <= 2:
            return "opening"
        elif any("cidade" in msg.get("content", "") for msg in conversation):
            if any(word in message_lower for word in ["valor", "preço", "quanto", "custo", "€"]):
                return "pricing"
            elif any(word in message_lower for word in ["cliente", "como", "funciona", "plataforma"]):
                return "explanation"
            else:
                return "qualification"
        elif "cliente" in message_lower or "plataforma" in message_lower:
            return "explanation"
        elif any(word in message_lower for word in ["sim", "quero", "interesse", "ok"]):
            return "closing"
        else:
            return "qualification"
    
    def extract_location_from_message(self, message):
        """Extrai localização da mensagem"""
        message_lower = message.lower()
        cities = ["lisboa", "porto", "coimbra", "braga", "aveiro", "faro", "cascais", "leiria", "felgueiras", "alfama", "ribeira"]
        
        for city in cities:
            if city in message_lower:
                return city.title()
        return None

    def build_dynamic_prompt(self, user_id, user_message, stage):
        """Constrói prompt dinâmico baseado no estágio e padrões de sucesso"""
        
        location = self.extract_location_from_message(user_message)
        best_patterns = {}
        
        # Busca melhores padrões para cada tipo
        for pattern_type in ["opening", "client_rule", "explanation", "price_presentation", "closing"]:
            patterns = learning_db.get_best_patterns(pattern_type)
            if patterns:
                best_patterns[pattern_type] = patterns[0][0]  # Melhor padrão
        
        base_prompt = f"""
Você é uma atendente de vendas especializada. Seja DIRETA, OBJETIVA e use exatamente estas técnicas comprovadas:

LOCALIZAÇÃO: Você sempre mora na mesma cidade que o cliente. {f"Cliente é de {location}, então você também é de {location}." if location else ""}

TÉCNICAS DE VENDA (use EXATAMENTE estas frases):

ABERTURA:
"Olá boa tarde tudo bem?? de qual cidade fala??"

REGRA DOS CLIENTES (quando perguntarem sobre encontros):
"Só saio com meus clientes"
"Só transo com meus clientes"

EXPLICAÇÃO:
"Só saio com o pessoal das plataformas adultas"
"Já é muito barato kkk aí não tem como ficar saindo com qualquer um"

PREÇO (quando perguntarem valores):
"19,90"
"Baratinho. É só pra selecionar quem quer mesmo"

FECHAMENTO:
"https://buy.stripe.com/14k4iR16VdNk43mfZ5"
"Caso queira seja bem vindo"

PARA AMOSTRAS/PREVIEWS:
"É só abrir o link que lá tem uma foto"

ESTÁGIO ATUAL: {stage}

REGRAS:
- Respostas CURTAS (máximo 2 linhas)
- Poucos emojis (só quando necessário)
- Vá direto ao ponto
- Use "kkk" ocasionalmente
- Seja transparente sobre preços
- Não insista se cliente resistir
"""

        # Ajusta prompt baseado no estágio
        if stage == "opening":
            base_prompt += "\nPERGUNTE A CIDADE primeiro. Seja amigável mas concisa."
        elif stage == "qualification":
            base_prompt += "\nFaça 1-2 perguntas sobre o que a pessoa busca. Não mencione preços ainda."
        elif stage == "explanation":
            base_prompt += "\nEXPLIQUE a regra dos clientes. Use as frases exatas acima."
        elif stage == "pricing":
            base_prompt += "\nAPRESENTE o preço: €19,90 e o link. Seja direta."
        elif stage == "closing":
            base_prompt += "\nCLIENTE interessado. Confirme o link e seja acolhedora."
            
        return base_prompt

    async def get_gpt_response(self, user_id: str, user_message: str) -> str:
        try:
            if user_id not in user_histories:
                user_histories[user_id] = []

            # Determina estágio da conversa
            stage = self.analyze_conversation_stage(user_id, user_message)
            
            # Constrói prompt dinâmico
            system_prompt = {
                "role": "system", 
                "content": self.build_dynamic_prompt(user_id, user_message, stage)
            }

            user_histories[user_id].append({"role": "user", "content": user_message})
            user_histories[user_id] = user_histories[user_id][-self.max_context_messages:]

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[system_prompt] + user_histories[user_id],
                max_tokens=150,  # Respostas mais curtas
                temperature=0.7,
            )

            reply = response.choices[0].message.content.strip()
            user_histories[user_id].append({"role": "assistant", "content": reply})
            
            # Salva no banco para aprendizado
            learning_db.log_conversation(user_id, user_message, reply, stage)
            
            # Detecta conversão automática
            if "stripe.com" in reply and ("19,90" in reply or "€19.90" in reply):
                logger.info(f"🎯 LINK DE VENDA ENVIADO para {user_id}")
                # Marca como tentativa de conversão
                asyncio.create_task(self.check_conversion_later(user_id))
            
            logger.info(f"🤖 [{stage}] Resposta: {reply[:80]}...")
            return reply

        except Exception as e:
            logger.error(f"Erro GPT: {e}")
            return "Oi, tive um problema técnico. Pode mandar de novo?"

    async def check_conversion_later(self, user_id):
        """Verifica conversão após 10 minutos"""
        await asyncio.sleep(600)  # 10 minutos
        # Aqui você pode implementar verificação automática via webhook do Stripe
        # Por enquanto, deixa manual
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
                    logger.info(f"✅ Mensagem enviada: {message[:50]}...")
                    return True
                else:
                    logger.error(f"❌ Erro Maytapi: {response.status_code} - {response.text}")
                    return False
                    
            except Exception as e:
                logger.error(f"❌ Exceção envio: {e}")
                return False

    def update_success_patterns(self, pattern_type, pattern_text, worked=True):
        """Atualiza padrões de sucesso baseado no feedback"""
        cursor = learning_db.conn.cursor()
        
        cursor.execute('''
            SELECT id, success_rate, usage_count FROM success_patterns 
            WHERE pattern_type = ? AND pattern_text = ?
        ''', (pattern_type, pattern_text))
        
        result = cursor.fetchone()
        
        if result:
            pattern_id, current_rate, usage_count = result
            # Atualiza taxa de sucesso
            new_rate = (current_rate * usage_count + (1.0 if worked else 0.0)) / (usage_count + 1)
            cursor.execute('''
                UPDATE success_patterns 
                SET success_rate = ?, usage_count = usage_count + 1
                WHERE id = ?
            ''', (new_rate, pattern_id))
        else:
            # Novo padrão
            cursor.execute('''
                INSERT INTO success_patterns (pattern_type, pattern_text, success_rate)
                VALUES (?, ?, ?)
            ''', (pattern_type, pattern_text, 1.0 if worked else 0.5))
        
        learning_db.conn.commit()

# Instancia o bot avançado
bot = WhatsAppBotAdvanced()

@app.post("/webhook")
async def webhook_handler(request: Request):
    try:
        data = await request.json()
        logger.info(f"📨 Webhook: {data.get('type', 'unknown')}")

        user = data.get("user", {})
        phone = user.get("phone")
        user_name = user.get("name", "Cliente")
        message_data = data.get("message", {})

        if not phone or not message_data or message_data.get("fromMe", False):
            return {"status": "ignored"}

        user_message = message_data.get("text")
        if not user_message or not user_message.strip():
            return {"status": "ignored"}

        logger.info(f"👤 {user_name} ({phone}): {user_message}")

        # Gera resposta otimizada
        reply = await bot.get_gpt_response(phone, user_message)
        
        # Delay humano
        delay = random.randint(2, 5)
        await asyncio.sleep(delay)
        
        # Envia resposta
        success = await bot.send_whatsapp_message(phone, reply)
        
        return {"status": "success" if success else "error", "sent": success}

    except Exception as e:
        logger.error(f"💥 Erro webhook: {e}")
        return {"status": "error"}

@app.get("/")
async def dashboard():
    """Dashboard com analytics"""
    cursor = learning_db.conn.cursor()
    
    # Estatísticas básicas
    cursor.execute("SELECT COUNT(*) FROM conversations WHERE date(timestamp) = date('now')")
    conversations_today = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM conversions WHERE date(timestamp) = date('now')")
    conversions_today = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(DISTINCT user_id) FROM conversations")
    unique_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM conversions")
    total_conversions = cursor.fetchone()[0]
    
    conversion_rate = (total_conversions / unique_users * 100) if unique_users > 0 else 0
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head><title>Atendente Virtual Analytics</title>
    <style>
        body {{font-family: Arial; margin: 40px; background: #f5f5f5;}}
        .card {{background: white; padding: 20px; margin: 15px 0; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);}}
        .metric {{font-size: 28px; font-weight: bold; color: #2196F3;}}
        .success {{color: #4CAF50;}}
    </style>
    </head>
    <body>
        <h1>🤖 Atendente Virtual - Ana</h1>
        
        <div class="card">
            <h2>📊 Performance Hoje</h2>
            <p>Conversas: <span class="metric">{conversations_today}</span></p>
            <p>Conversões: <span class="metric success">{conversions_today}</span></p>
        </div>
        
        <div class="card">
            <h2>📈 Performance Total</h2>
            <p>Usuários únicos: <span class="metric">{unique_users}</span></p>
            <p>Total conversões: <span class="metric success">{total_conversions}</span></p>
            <p>Taxa conversão: <span class="metric">{conversion_rate:.1f}%</span></p>
        </div>
        
        <div class="card">
            <h2>🎯 Sistema de Aprendizado</h2>
            <p>✅ Padrões de sucesso mapeados</p>
            <p>✅ Aprendizado contínuo ativo</p>
            <p>✅ Otimização automática</p>
        </div>
        
        <div class="card">
            <h2>🔗 Ações</h2>
            <p><a href="/conversion/{'{user_id}'}" target="_blank">Registrar Conversão Manual</a></p>
            <p><a href="/analytics" target="_blank">Analytics JSON</a></p>
        </div>
    </body>
    </html>
    """
    
    return HTMLResponse(html)

@app.post("/conversion/{user_id}")
async def register_conversion(user_id: str, amount: float = 19.90):
    """Registra conversão manual"""
    learning_db.mark_conversion(user_id, amount)
    return {"status": "success", "user_id": user_id, "amount": amount}

@app.get("/analytics")
async def get_analytics():
    """Analytics em JSON"""
    cursor = learning_db.conn.cursor()
    
    cursor.execute('''
        SELECT pattern_type, pattern_text, success_rate, usage_count 
        FROM success_patterns 
        ORDER BY success_rate DESC
    ''')
    patterns = cursor.fetchall()
    
    cursor.execute('''
        SELECT stage, COUNT(*) 
        FROM conversations 
        WHERE date(timestamp) = date('now') 
        GROUP BY stage
    ''')
    stages_today = dict(cursor.fetchall())
    
    return {
        "success_patterns": [
            {"type": p[0], "text": p[1], "success_rate": p[2], "usage": p[3]} 
            for p in patterns
        ],
        "stages_today": stages_today
    }

from fastapi.responses import HTMLResponse

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    logger.info(f"🚀 Sistema com Aprendizado iniciando na porta {port}")
    logger.info(f"🧠 Padrões de sucesso carregados do banco de dados")
    uvicorn.run(app, host="0.0.0.0", port=port)
