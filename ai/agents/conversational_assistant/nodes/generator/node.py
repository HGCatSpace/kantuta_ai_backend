from langchain_core.messages import HumanMessage, SystemMessage
from ai.agents.conversational_assistant.llms import get_chat_model
from ai.agents.conversational_assistant.states import RetrievalState

# --- 1. DEFINICIÓN DE TEMPLATES (Aquí mismo para evitar errores) ---

SYSTEM_TEMPLATE = """Eres **Kantuta AI**, un asistente legal experto en la legislación de Bolivia.

TU OBJETIVO:
Responder a la pregunta del usuario basándote **ÚNICA Y EXCLUSIVAMENTE** en el CONTEXTO LEGAL proporcionado.

REGLAS:
1.  **Cita las fuentes:** Si usas información del contexto, menciona el documento (ej: "Según el Artículo 45... [libro: nombre_del_libreo, pag: pagina]").
3.  **Tono:** Formal, jurídico y preciso.
4.  **Formato:** Usa listas (bullets) si hay múltiples puntos.
TAREA FINAL **Pega exactamente el los datos que tuviste de entrada**
"""

HUMAN_MSG_TEMPLATE = """CONTEXTO LEGAL RECUPERADO:
{context_text}

---
PREGUNTA DEL USUARIO:
{mensaje}
"""

# --- 2. LÓGICA DEL NODO ---

async def generate_node(state: RetrievalState):
    print("🤖 [GENERATOR] Iniciando generación...")

    messages = state.get("messages")
    raw_context = state.get("context", [])
    
    # Configuración dinámica
    threshold = state.get("score_threshold", 0.65) # Distancia máxima
    temp = state.get("temperature", 0.0)
    top_p = state.get("top_p", 0.9)
    top_k = state.get("top_k", 40)

    # A. PROCESAMIENTO Y FILTRADO DEL CONTEXTO
    valid_docs = []
    for item in raw_context:
        if isinstance(item, tuple):
            doc, score = item # Score es Distancia (0 es idéntico)
            
            # Filtro: Solo pasa si la distancia es MENOR al umbral
            #if score <= threshold:
            source = doc.metadata.get("source_filename", "Fuente Desconocida")
            valid_docs.append(f"--- FUENTE: {source} ---PAGINA: {doc.metadata.get("page_label")}\n{doc.page_content}")
            #else:
                # Debug opcional para ver qué se descarta
                # print(f"   🗑️ Descartado (Dist: {score:.4f} > {threshold})")
            #    pass
        else:
            # Si llega sin score (fallback), lo aceptamos
            valid_docs.append(item.page_content)
    
    # Construir el bloque de texto
    if valid_docs:
        context_text = "\n\n".join(valid_docs)
        print(f"   ✅ Contexto válido: {len(valid_docs)} fragmentos.")
    else:
        context_text = "No se encontraron documentos relevantes en la base de datos para esta consulta."
        print("   ⚠️ Contexto vacío tras el filtrado.")

    # B. SANITIZACIÓN DEL MENSAJE DE USUARIO (Fix para LangSmith/Multimodal)
    last_user_msg = messages[-1]
    raw_content = last_user_msg.content
    
    query_text = ""
    if isinstance(raw_content, str):
        query_text = raw_content
    elif isinstance(raw_content, list):
        # Si LangSmith manda una lista [{'type':'text', 'text':'hola'}]
        parts = [block.get("text", "") for block in raw_content if block.get("type") == "text"]
        query_text = " ".join(parts)
    else:
        query_text = str(raw_content)

    # C. INYECCIÓN EN EL TEMPLATE
    # Aquí combinamos el texto limpio del usuario con el contexto
    augmented_content = HUMAN_MSG_TEMPLATE.format(
        context_text=context_text, 
        mensaje=query_text
    )
    
    augmented_message = HumanMessage(content=augmented_content)

    # D. ENSAMBLE DEL HISTORIAL
    # System + Historial Previo + Nuevo Mensaje Aumentado
    history = messages[:-1] 
    
    prompt_messages = [
        SystemMessage(content=SYSTEM_TEMPLATE), 
        augmented_message                        
    ]

    for msg in prompt_messages:
        msg.pretty_print()
    # E. INVOCACIÓN
    llm = get_chat_model(
        temperature=temp, 
        top_p=top_p, 
        top_k=top_k
    )    
    
    print("🚀 [GENERATOR] Invocando LLM...")
    try:
        response = await llm.ainvoke(prompt_messages)
        print("✅ [GENERATOR] Respuesta generada.")
        return {"messages": [response]}
        
    except Exception as e:
        print(f"❌ Error generando respuesta: {e}")
        return {"messages": [HumanMessage(content="Lo siento, ocurrió un error interno al generar la respuesta.")]}