# -*- coding: utf-8 -*-
import os
import json
import time 
import re 
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from google import genai
from google.genai import types
from google.genai.errors import APIError 



try:
    from firebase_admin import initialize_app, firestore, credentials
    HAS_FIREBASE = True
except ImportError:
    HAS_FIREBASE = False
    print("AVISO: A biblioteca 'firebase-admin' não está instalada. O histórico de pedidos será desativado.")


# --- CONFIGURAÇÕES DE AMBIENTE E API ---


GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
if not GEMINI_API_KEY:
    try:
        with open('gemini_api_key.txt', 'r') as f:
            GEMINI_API_KEY = f.read().strip()
    except FileNotFoundError:
        print("ERRO: A variável de ambiente 'GEMINI_API_KEY' não foi definida. Crie o arquivo 'gemini_api_key.txt' ou defina a variável.")
        pass

# Inicialização do Firebase/Firestore
db = None
if HAS_FIREBASE:
    try:
             
        FIREBASE_CRED_PATH = "saluzfoodbot-firebase-adminsdk-fbsvc-7c34cc73ca.json"
        
        if os.path.exists(FIREBASE_CRED_PATH):
            cred = credentials.Certificate(FIREBASE_CRED_PATH) 
            initialize_app(cred) 
            db = firestore.client()
        else:
            print(f"AVISO: Arquivo de credenciais do Firebase não encontrado: {FIREBASE_CRED_PATH}")
            # Tenta inicializar sem credenciais, se estiver no ambiente do Firebase
            try:
                initialize_app()
                db = firestore.client()
            except Exception as init_err:
                print(f"ERRO ao inicializar Firebase sem credenciais: {init_err}")
                db = None


    except Exception as e:
        print(f"AVISO: Não foi possível inicializar o Firebase. O banco de dados não funcionará. Erro: {e}")
        db = None

# Cliente Gemini
client = None
if GEMINI_API_KEY:
    try:
        # Tenta inicializar o cliente usando a chave encontrada
        client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        print(f"ERRO ao inicializar o cliente Gemini: {e}")
        client = None 
else:
    print("ERRO: Cliente Gemini não inicializado devido à falta da chave de API.")

# ---------------------------------------------------------------------------
# >> LINK DO CARDÁPIO EM PDF
# ---------------------------------------------------------------------------
PDF_CARDAPIO_LINK = "https://abre.ai/n7ty"

# >> ENDEREÇO DO RESTAURANTE (V14.0)
RESTAURANT_ADDRESS = "Av. Assis Brasil 516, Porto Alegre, Rio Grande do Sul 91030-280"

GEMINI_TIMEOUT_SECONDS = 240 


# ARQUIVO DE CARDÁPIO ATUALIZADO
CARDAPIO_JSON = {
    "Adicional": [
        {"nome": "Turbine seu Burguer (Adicional)", "preco": 15.00, "descricao": "Adiciona fritas e Bebida ao seu pedido."},
        {"nome": "Adicional de Acompanhamento (Elmo Salgado) - Molho de Carne", "preco": 21.99, "descricao": "Opcional para Elmo Salgado"},
        {"nome": "Adicional de Acompanhamento (Elmo Salgado) - Frango Empanado", "preco": 23.99, "descricao": "Opcional para Elmo Salgado"},
        {"nome": "Adicional de Acompanhamento (Elmo Salgado) - Escalope de Carne", "preco": 24.99, "descricao": "Opcional para Elmo Salgado"}
    ],
    "Burguer": [
        {"nome": "Trono de SaLuz", "preco": 47.00, "descricao": "Pão brioche, molho SaLuz, barbecue, molho cheddar, onion rings, geleia de bacon e um super burguer."},
        {"nome": "Fúria SaLuz", "preco": 42.00, "descricao": "Pão brioche, molho SaLuz, molho cheddar, bacon, queijo mussarela e um super burguer."},
        {"nome": "Templo dos Sabores", "preco": 44.00, "descricao": "Pão brioche, molho SaLuz, cheddar, mussarela, molho pinneaple, bacon e um super burguer."},
        {"nome": "Forja do Sabor", "preco": 36.00, "descricao": "Pão brioche, molho SaLuz, molho cheddar, bacon, alface, salada, queijo mussarela e um super burguer."},
        {"nome": "Escudo Crocante", "preco": 39.00, "descricao": "Pão brioche, molho SaLuz, molho cheddar, bacon duplo e um super burguer."},
        {"nome": "Paladino da Justiça", "preco": 31.00, "descricao": "Pão brioche, molho SaLuz, molho pinneaple e um saboroso frango empanado."},
        {"nome": "Supremo", "preco": 34.00, "descricao": "Pão brioche, molho SaLuz, cheddar, alface, tomate e um super burguer."},
        {"nome": "Plebeu", "preco": 29.00, "descricao": "Pão brioche, molho SaLuz, queijo e um super burguer."}
    ],
    "Prato Principal": [
        {"nome": "Rainha de SaLuz (M - Serve 3 Pessoas)", "preco": 54.90, "serve": "3 pessoas", "descricao": "Carne de Paleta suína ao molho Provolone e molho Cheddar, com batata rústica e arroz branco."},
        {"nome": "Rainha de SaLuz (G - Serve 5 Pessoas)", "preco": 89.90, "serve": "5 pessoas", "descricao": "Carne de Paleta suína ao molho Provolone e molho Cheddar, com batata rústica e arroz branco."},
        {"nome": "Defensor do Reino (M - Serve 3 Pessoas)", "preco": 54.90, "serve": "3 pessoas", "descricao": "Corte de Paleta suína ao molho Barbecue, acompanhada de fritas e deliciosa farofa de bacon."},
        {"nome": "Defensor do Reino (G - Serve 5 Pessoas)", "preco": 79.90, "serve": "5 pessoas", "descricao": "Corte de Paleta suína ao molho Barbecue, acompanhada de fritas e deliciosa farofa de bacon."},
        {"nome": "Armas do Reino (M - Serve 3 Pessoas)", "preco": 54.90, "serve": "3 pessoas", "descricao": "Carne de Paleta suína ao molho Barbecue."},
        {"nome": "Armas do Reino (G - Serve 5 Pessoas)", "preco": 79.90, "serve": "5 pessoas", "descricao": "Carne de Paleta suína ao molho Barbecue."},
        {"nome": "Cavaleiro Supremo (M - Serve 3 Pessoas)", "preco": 79.00, "serve": "3 pessoas", "descricao": "Carne empanada à parmegiana ao molho vermelho e molho provolone, com fritas e arroz branco."},
        {"nome": "Cavaleiro Supremo (G - Serve 5 Pessoas)", "preco": 119.00, "serve": "5 pessoas", "descricao": "Carne empanada à parmegiana ao molho vermelho e molho provolone, com fritas e arroz branco."},
        {"nome": "Cavaleiro da Luz (M - Serve 3 Pessoas)", "preco": 79.00, "serve": "3 pessoas", "descricao": "Carne empanada à parmegiana ao molho provolone, com fritas e arroz branco."},
        {"nome": "Cavaleiro da Luz (G - Serve 5 Pessoas)", "preco": 119.00, "serve": "5 pessoas", "descricao": "Carne empanada à parmegiana ao molho provolone, com fritas e arroz branco."}
    ],
    "Prato Individual": [
        {"nome": "Elmo Salgado (Mac'N'Cheese)", "preco": 24.99, "descricao": "Mac'N'Cheese. Escolha entre molho cheddar ou molho provolone."},
        {"nome": "Parmegiana Individual", "preco": 24.99, "descricao": "Carne à Parmegiana. Acompanha fritas e arroz branco. Escolha entre carne bovina ou frango."}
    ],
    "Para Compartilhar": [
        {"nome": "Fortaleza do Rei (Batata-Recheada - M)", "preco": 79.99, "serve": "2 pessoas", "descricao": "Suculentas tiras de carne, bacon, queijo mussarela, molho cheddar, cream cheese, cebola caramelizada, picles e molho SaLuz."},
        {"nome": "Fortaleza do Rei (Batata-Recheada - G)", "preco": 109.99, "serve": "3 pessoas", "descricao": "Suculentas tiras de carne, bacon, queijo mussarela, molho cheddar, cream cheese, cebola caramelizada, picles e molho SaLuz."},
        {"nome": "Divino (Tiras de Frango - Individual)", "preco": 25.00, "serve": "1 pessoa", "descricao": "Tiras de Frango empanadas. Acompanha molho SaLuz e Cheddar."}
    ],
    "Porções": [
        {"nome": "Fritas ao Provolone e Parofa de Bacon", "preco": 32.90},
        {"nome": "Queijo Coalho Empanado (10 unidades)", "preco": 35.90},
        {"nome": "Fritas McCain 300g", "preco": 19.90},
        {"nome": "Fritas McCain 500g", "preco": 24.90},
        {"nome": "Porção Extra de Arroz", "preco": 10.00},
        {"nome": "Porção Extra de Salada", "preco": 8.00}
    ],
    "Bebidas": [
        {"nome": "Água Mineral com Gás 500ml", "preco": 5.00},
        {"nome": "Água Mineral sem Gás 500ml", "preco": 5.00},
        {"nome": "H2O", "preco": 7.00},
        {"nome": "Refrigerante LATA 350ml (Coca-Cola, Guaraná, Soda, Fanta, etc.)", "preco": 7.00},
        {"nome": "Suco de Limão", "preco": 10.00},
        {"nome": "Suco de Morango", "preco": 12.00},
        {"nome": "Red Bull", "preco": 15.00}
    ],
    "Chopp e Cervejas": [
        {"nome": "Chopp Imigração 300ml", "preco": 12.00},
        {"nome": "Chopp Imigração 500ml", "preco": 16.00},
        {"nome": "Chopp Brahma 300ml", "preco": 12.00},
        {"nome": "Chopp Brahma 500ml", "preco": 16.00},
        {"nome": "Heineken long neck", "preco": 18.00},
        {"nome": "Stella long neck", "preco": 18.00},
        {"nome": "Corona long neck", "preco": 12.00},
        {"nome": "Spaten long neck", "preco": 12.00},
        {"nome": "Skol Beats", "preco": 15.00}
    ]
}


app = Flask(__name__)

# --- FUNÇÕES DE LÓGICA DO CHAT E API GEMINI ---

def format_menu_for_gemini():
    """Formata o cardápio JSON em uma string SIMPLES para o prompt do Gemini."""
    menu_str = "Cardápio Saluz Food House - SOMENTE ESTES ITENS SÃO VÁLIDOS:\n"
    for categoria, itens in CARDAPIO_JSON.items():
        menu_str += f"\n--- {categoria.upper()} ---\n"
        for item in itens:
            serve = f" (Serve {item.get('serve')})" if item.get('serve') else ""
            menu_str += f"- {item['nome']}: R${item['preco']:.2f}{serve}\n"
    return menu_str

# Função auxiliar para limpar a string antes de enviar ao Twilio
def clean_and_format_message(text):
    # 1. Remove o prefixo "🤖 Saluz Bot:"
    text = re.sub(r"🤖\s*Saluz Bot:[\s\n]*", "", text, flags=re.IGNORECASE)
    # 2. Substitui múltiplas quebras de linha por duas (para espaçamento decente no WhatsApp)
    text = re.sub(r'[\n]{3,}', '\n\n', text)
    # 3. Remove quebras de linha no início e no fim
    return text.strip()


def get_gemini_response(user_message, user_history, user_doc_ref):
    """
    Chama a API Gemini para processar a mensagem do usuário com o cardápio.
    """
    if not client:
        return "❌ Desculpe, a conexão com a Gemini API falhou. Verifique sua chave de API."

    MAX_RETRIES = 4
    response_text = None
    
    # DEFINIÇÕES DE MENSAGENS FIXAS
    initial_greeting = "Olá! Eu sou o Saluz Bot, seu assistente de pedidos. Como posso te ajudar a montar seu pedido hoje? Se precisar do cardápio, me peça 'cardápio'!"
    restaurant_address = RESTAURANT_ADDRESS # Usa a constante definida
    
    # Montagem do System Prompt (Instrução da Persona e Regras)
    menu_context = format_menu_for_gemini()
    system_prompt = f"""
    [INSTRUÇÕES GERAIS]
    Você é o 'Saluz Bot', o assistente de pedidos do restaurante Saluz Food House.
    Seu objetivo é ser amigável, acolhedor e focado em ajudar o cliente a montar o pedido.
    
    REGRAS CRÍTICAS (IMPERATIVAS):
    1. **ENDEREÇO FIXO (V14.0):** O endereço do restaurante (para retirada ou informação) é: **{restaurant_address}**. Se o cliente perguntar o endereço ou localização (e a action for 'GENERAL_CHAT'), você DEVE fornecer APENAS este endereço na `summary`. NUNCA invente outros endereços.
    2. **CARDÁPIO FIXO:** Você DEVE usar **APENAS** os nomes de itens listados abaixo. **NÃO INVENTE, RESUMA OU ALTERE OS NOMES DOS PRATOS.** Se o cliente pedir algo que NÃO está na lista, você DEVE responder em 'summary' dizendo *claramente* que o item não está disponível e, em seguida, **sugerir** um item similar da lista.
    {menu_context}
    
    REGRAS DE FORMATAÇÃO:
    3. RESPOSTA ESTRUTURADA (JSON): Você DEVE responder usando o formato JSON ESPECIFICADO na schema.
    4. PEDIDOS (Action 'ORDER_PENDING'): Se o usuário estiver mencionando itens para comprar, a 'action' DEVE ser 'ORDER_PENDING'.
    5. FINALIZAÇÃO (Action 'ORDER_READY'): Se o usuário pedir para finalizar, a 'action' DEVE ser 'ORDER_READY'.
    6. CONVERSA GERAL (Action 'GENERAL_CHAT'): Se o usuário perguntar sobre horários, localização, ou *pedir o cardápio*, a 'action' DEVE ser 'GENERAL_CHAT'. Se o cliente pedir o cardápio, **você DEVE incluir este link para o cardápio em PDF: {PDF_CARDAPIO_LINK}**
    [/INSTRUÇÕES GERAIS]
    """
    
    # 1. Inicia o array de conversação
    conversation = []

    # 2. Adicionar o histórico de conversas do usuário
    if user_history.get('chat_history'):
        for msg in user_history['chat_history']:
            text_part = msg.get('text', '')
            if text_part:
                conversation.append(types.Content(role=msg['role'], parts=[types.Part(text=text_part)])) 

    # 3. Adicionar a mensagem atual do usuário com o System Prompt prefixado
    
    # Lógica de prompt para a primeira mensagem
    if not conversation:
        # O system_prompt é anexado à mensagem do usuário para contextulizar o modelo
        full_user_message = (
            f"{system_prompt}\n\n[MENSAGEM DO CLIENTE]: {user_message}\n\n"
            f"[INSTRUÇÃO ADICIONAL]: Se a mensagem do cliente for 'Oi', use a saudação inicial: '{initial_greeting}'"
        )
    else:
        full_user_message = f"{system_prompt}\n\n[MENSAGEM DO CLIENTE]: {user_message}"
       
    conversation.append(
        types.Content(
            role='user', 
            parts=[types.Part(text=full_user_message)] 
        )
    )

    
    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=conversation,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "action": types.Schema(type=types.Type.STRING, description="Ação: 'ORDER_PENDING', 'ORDER_READY', ou 'GENERAL_CHAT'."),
                            "summary": types.Schema(type=types.Type.STRING, description="Resposta principal para o usuário. Confirmação de pedido, resposta a perguntas, etc."),
                            "items": types.Schema(type=types.Type.ARRAY, description="Lista de itens do pedido atual, baseada estritamente no CARDAPIO_JSON.", 
                                items=types.Schema(type=types.Type.OBJECT, properties={"name": types.Schema(type=types.Type.STRING), "quantity": types.Schema(type=types.Type.INTEGER)})),
                            "total_price": types.Schema(type=types.Type.NUMBER, description="Preço total do pedido, calculado estritamente com base no CARDAPIO_JSON.")
                        }
                    )
                )
            )
            
            response_text = response.text.strip()
            
            break # Sucesso, saia do loop
            
        except APIError as e: 
            print(f"Tentativa {attempt + 1}/{MAX_RETRIES} falhou com erro de API: {e}")
            if attempt < MAX_RETRIES - 1:
                wait_time = 2 ** (attempt + 1)
                print(f"Aguardando {wait_time} segundos antes de tentar novamente.")
                time.sleep(wait_time)
            else:
                print("Todas as tentativas falharam. Retornando mensagem de erro final.")
                # Fallback para o caso de erro de API
                return "❌ Desculpe, o sistema de pedidos está temporariamente sobrecarregado. Por favor, tente novamente em um minuto."
        
        except Exception as e:
            print(f"Erro inesperado na chamada Gemini: {e}")
            # Fallback para o caso de erro inesperado
            return f"❌ Desculpe, ocorreu um erro inesperado ao processar seu pedido. Detalhe: {e}"


    if response_text is None:
        return "❌ Desculpe, o serviço de IA falhou após várias tentativas."
    
    # --- Lógica de processamento e persistência da resposta ---
    
    try:
        data = json.loads(response_text)
        
        # --- Lógica para o Usuário ---
        
        raw_final_message = "" # Inicializa a mensagem bruta
        
        # Intercepta APENAS 'Oi'/'Olá' no primeiro turno (sem histórico) para garantir a saudação
        is_first_turn_greeting = user_message.strip().lower() in ['oi', 'olá', 'ola'] and not user_history.get('chat_history')
        
        if data.get('action') == 'GENERAL_CHAT' and is_first_turn_greeting:
             # Se for o primeiro "Oi", usa a saudação inicial codificada
             raw_final_message = f"🤖 Saluz Bot:\n\n{initial_greeting}"
        else:
             # Caso contrário, usa a summary
             raw_final_message = f"🤖 Saluz Bot:\n\n{data.get('summary', 'Desculpe, não entendi. Pode repetir?')}\n" # Adiciona um fallback simples para a summary
        
        
        if data.get('action') == 'ORDER_PENDING' and data.get('items'):
            items_list = "\n".join([f"- {item['quantity']}x {item['name']}" for item in data['items']])
            raw_final_message += f"\nSeu pedido atual:\n{items_list}\n"
            raw_final_message += f"\nO total parcial é de R${data.get('total_price', 0.00):.2f}."
            raw_final_message += f"\n\nPosso adicionar algo mais? Se for tudo, me diga 'finalizar'."
        
        elif data.get('action') == 'ORDER_READY':
            items_list = "\n".join([f"- {item['quantity']}x {item['name']}" for item in data['items']])
            raw_final_message += f"\nSeu Pedido Final:\n{items_list}\n"
            raw_final_message += f"\n✅ O VALOR TOTAL É DE R${data.get('total_price', 0.00):.2f}."
            # Garante que a pergunta de endereço seja feita no final se a summary não a fez
            if "endereço" not in raw_final_message.lower() and "qual" not in raw_final_message.lower():
                 raw_final_message += "\n\nObrigado por pedir no Saluz Food House! Qual será o endereço de entrega?"

        
        elif data.get('action') == 'GENERAL_CHAT':
            pass
            
        # Limpa e formata a mensagem antes de retornar
        final_message = clean_and_format_message(raw_final_message)
        
        # Atualiza o histórico no Firestore (se estiver disponível)
        if db and user_doc_ref:
            
            
            new_chat_history = []
            if user_history.get('chat_history'):
                for item in user_history['chat_history']:
                    if item.get('role') in ['user', 'model']:
                        new_chat_history.append({'role': item['role'], 'text': item['text']})

            # Adiciona a mensagem do usuário (sem o system prompt)
            new_chat_history.append({'role': 'user', 'text': user_message})
            
            # Adiciona a resposta final do modelo ao histórico
            new_chat_history.append({'role': 'model', 'text': final_message})

            user_doc_ref.set({'items': data.get('items', []), 
                              'total': data.get('total_price', 0.00),
                              'chat_history': new_chat_history}, 
                              merge=True)
            
        return final_message

    except json.JSONDecodeError:
        print(f"ERRO: O modelo Gemini não retornou JSON válido. Resposta: {response_text}")
        return f"🤖 Saluz Bot: Desculpe, tive um erro ao processar sua solicitação de IA. Tente reformular a frase."
    
    except Exception as e:
        print(f"ERRO: Erro de lógica no pós-processamento: {e}")
        return f"🤖 Saluz Bot: Ops! Tive um erro de lógica interna. Por favor, tente novamente."

# --- ROTA WEBHOOK DO FLASK (COM LOG DE DEBUG) ---

@app.route('/whatsapp', methods=['POST'])
def whatsapp_webhook():
    """Recebe mensagens do Twilio e as processa com a Gemini API."""
    
    # 1. Extrair dados da mensagem do Twilio
    incoming_msg = request.values.get('Body', '').strip()
    sender_id = request.values.get('From', '').strip() 

    # 2. Inicializar a resposta do Twilio
    resp = MessagingResponse()
    
    print(f"Mensagem recebida de {sender_id}: {incoming_msg}")

    # 3. Lógica do Banco de Dados (Firestore) - Recuperação de Histórico
    user_history = {}
    user_doc_ref = None
    if db:
        user_doc_ref = db.collection('orders').document(sender_id)
        try:
            user_doc = user_doc_ref.get()
            if user_doc.exists:
                user_history = user_doc.to_dict()
        except Exception as e:
            print(f"Erro ao buscar histórico no Firestore: {e}")
    
    # 4. Obter resposta do Gemini
    ai_response_text = get_gemini_response(incoming_msg, user_history, user_doc_ref)
    
    # Log da Resposta gerada antes de enviar para o Twilio**
    print(f"Resposta gerada pela IA (limpa): {ai_response_text[:100]}...") # Imprime os primeiros 100 caracteres
    
    # 5. Enviar a Resposta de Volta via Twilio
    resp.message(ai_response_text)
    
    # 6. Retornar o XML de resposta para o Twilio
    twilio_xml_response = str(resp)
    
    # Log do XML final**
    print(f"XML final retornado ao Twilio: {twilio_xml_response}")
    
    return twilio_xml_response # Retorna o XML completo

@app.route('/')
def health_check():
    """Ponto de checagem simples para verificar se o servidor está ativo."""
    return "✅ O Webhook WhatsApp Saluz Bot (via Twilio) está funcionando! Acesse /whatsapp para enviar um POST do Twilio."

# --- EXECUÇÃO DO SERVIDOR ---

if __name__ == '__main__':
    print("Iniciando o Servidor Flask...")
    print("--------------------------------------------------")
    print(f"Status da Gemini API: {'Conectado' if client else 'FALHA - Chave ausente!'}")
    print(f"Status do Firestore: {'Conectado' if db else 'DESCONECTADO - O histórico de pedidos não será salvo.'}")
    print("--------------------------------------------------")
    app.run(port=5000, debug=True)