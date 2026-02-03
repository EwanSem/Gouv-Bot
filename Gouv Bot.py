import streamlit as st
import requests
import json
import base64
import re
from datetime import datetime, date

# Configuration de l'API
API_RAG_URL = "https://chat-services.sandbox.gouv.tg/rag-chat"

st.set_page_config(page_title="Gouv Bot", layout="wide")
st.title("Gouv Bot")

# --- Styles CSS personnalisés ---
st.markdown("""
<style>
    .stForm {
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 20px;
    }
    .stChatMessage {
        border-radius: 15px;
    }
</style>
""", unsafe_allow_html=True)

# --- Initialisation de l'état ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "conversation_state" not in st.session_state:
    st.session_state.conversation_state = {}

# --- Barre Latérale : Sélection de la Plateforme ---
with st.sidebar:
    st.image("https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcR6A6R4O6C-W9Wn6-7W8V6-6_7Z-_U-W-V-Vw&s", width=100)
    st.title("Paramètres")
    
    # Choix de la plateforme
    platform_choice = st.selectbox(
        "Plateforme active :",
        ["Service Public", "Voyage"],
        index=1 if st.session_state.get("platform") == "Voyage" else 0
    )
    
    # Réinitialisation si changement
    if "platform" not in st.session_state or st.session_state.platform != platform_choice:
        st.session_state.platform = platform_choice
        st.session_state.messages = []
        st.session_state.conversation_state = {"platform": platform_choice}
        st.rerun()

    st.markdown("---")
    st.caption("Gouv Bot v3.5.0 - Assistant IA")

def encode_images(image_files):
    encoded_images = []
    if image_files:
        for img_file in image_files:
            img_file.seek(0)
            encoded_images.append(base64.b64encode(img_file.read()).decode("utf-8"))
    return encoded_images if encoded_images else None

def get_rag_response(question: str, history: list, state: dict, images_base64: list = None) -> dict:
    # On s'assure que la plateforme est bien injectée dans l'état et le payload
    platform = st.session_state.get("platform", "Service Public")
    state["platform"] = platform
    
    payload = {
        "question": question,
        "history": history,
        "platform": platform,
        "stream": False,
        "state": state,
        "images_base64": images_base64
    }
    try:
        response = requests.post(API_RAG_URL, json=payload)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"answer": f"Erreur: {str(e)}", "sources": [], "state": state}

# --- Layout Principal ---
# On affiche les messages dans le flux principal
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- Affichage du Formulaire de Réclamation (après les messages) ---
state = st.session_state.conversation_state
if state.get("show_ui_form"):
    form_config = state.get("form_schema", {})
    problem_type = state.get("current_pipeline")
    
    # On crée une bulle "assistant" pour contenir le formulaire
    with st.chat_message("assistant"):
        st.markdown(f"### 📝 {form_config.get('title', 'Formulaire')}")
        st.info("Veuillez renseigner les champs ci-dessous pour finaliser votre demande.")
        
        # Style uniforme : pas de bordures lourdes, fond transparent
        with st.form("dynamic_claim_form", border=False):
            form_data = {}
            
            # On affiche les champs
            for field_id, field_info in form_config.get("fields", {}).items():
                if field_id == "captures_preuves":
                    continue
                
                label = f"**{field_info.get('label', field_id)}**"
                hint = field_info.get("hint", "")
                default_val = state.get("form_data", {}).get(field_id, "")

                if "date" in field_id.lower():
                    # Gestion spéciale pour les dates
                    try:
                        if default_val and isinstance(default_val, str) and "-" in default_val:
                            d_val = datetime.strptime(default_val, "%Y-%m-%d").date()
                        else:
                            d_val = date.today()
                    except Exception:
                        d_val = date.today()
                    
                    selected_date = st.date_input(label, value=d_val, help=hint)
                    form_data[field_id] = selected_date.strftime("%Y-%m-%d")
                else:
                    # Saisie texte classique
                    if default_val is None: default_val = ""
                    form_data[field_id] = st.text_input(label, value=str(default_val), help=hint, placeholder=hint)
            
            # Section Upload
            st.markdown("---")
            uploaded_files = None
            if "captures_preuves" in form_config.get("required_fields", []):
                uploaded_files = st.file_uploader("**📸 Preuve(s) de paiement (Capture d'écran, SMS Mobile Money)**", 
                                               type=["jpg", "jpeg", "png"], 
                                               accept_multiple_files=True,
                                               help="Sélectionnez un ou plusieurs fichiers")

            # Bouton d'envoi
            submitted = st.form_submit_button("VALIDER MA RÉCLAMATION", use_container_width=True, type="primary")
            
            if submitted:
                # Validation Métier (Frontend)
                errors = []
                for req in form_config.get("required_fields", []):
                    if req == "captures_preuves":
                        if not uploaded_files:
                            errors.append("Une preuve de paiement est obligatoire.")
                    elif not form_data.get(req):
                        errors.append(f"Le champ '{form_config['fields'][req]['label']}' est requis.")
                
                if form_data.get("email_demandeur") and not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", form_data["email_demandeur"]):
                    errors.append("L'adresse email saisie est incorrecte.")
                
                if form_data.get("telephone"):
                    clean_phone = form_data["telephone"].replace(" ", "").replace("-", "")
                    if not re.match(r"^(?:\+228|00228|228)?([79]\d{7})$", clean_phone):
                        errors.append("Le numéro de téléphone doit comporter 8 chiffres (format Togo).")

                if errors:
                    for err in errors:
                        st.error(err)
                else:
                    with st.spinner("Analyse et transmission..."):
                        imgs_b64 = encode_images(uploaded_files)
                        updated_state = state.copy()
                        updated_state["form_data"] = form_data
                        updated_state["show_ui_form"] = False
                        
                        response_data = get_rag_response(
                            "LOGIQUE_FORMULAIRE_UI", 
                            st.session_state.messages, 
                            updated_state,
                            images_base64=imgs_b64
                        )
                        
                        st.session_state.conversation_state = response_data.get("state", {})
                        st.session_state.messages.append({"role": "assistant", "content": response_data.get("answer")})
                        st.rerun()

# Zone de saisie du chat (toujours en bas)
if prompt := st.chat_input("Votre message (ou 'annuler')..."):
    # Si un formulaire est ouvert, on peut quand même envoyer un message (ex: pour annuler ou poser une question)
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Réflexion..."):
            response_data = get_rag_response(
                prompt, 
                st.session_state.messages[:-1], 
                st.session_state.conversation_state
            )
            
            answer = response_data.get("answer")
            st.session_state.conversation_state = response_data.get("state", {})
            st.markdown(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})
    st.rerun()

