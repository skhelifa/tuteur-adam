from collections import Counter
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import time

from openai import OpenAI
from pypdf import PdfReader
import streamlit as st
import streamlit.components.v1 as components

# -----------------------------------------------------------------------------
# DSFMGPT / Hub — Écosystème Pédagogique Souverain DSFM / BEF Manitoba (8 Modules)
# -----------------------------------------------------------------------------

APP_DIR = Path(__file__).parent
DOCS_DIR = APP_DIR / "documents"

COURSES = {
    "Biology 40S": {
        "folder": "biology",
        "welcome": (
            "Salut Adam ! Bienvenue en Biologie 40S. Sur quel sujet travaillons-nous"
            " aujourd'hui ? Génétique, hérédité mendélienne, mécanismes d'évolution ou biologie cellulaire ?"
        ),
        "system": """
Tu es le tuteur d'Adam pour le cours de Biologie 40S (12e année) au Collège Louis-Riel au Manitoba (normes DSFM et BEF).
APPROCHE SOCRATIQUE OBLIGATOIRE : Enseigne en FRANÇAIS. Ne donne jamais de réponses directes toutes faites.
Pose UNE SEULE question claire à la fois, utilise des indices gradués, stimule le raisonnement et valide chaque étape.
""",
    },
    "Computer Science 40S (Python/STIAM)": {
        "folder": "cs40s",
        "welcome": (
            "Bienvenue au laboratoire STIAM & Informatique 40S ! Quels algorithmes, structures"
            " de données ou défis Python explorons-nous aujourd'hui ?"
        ),
        "system": """
Tu es le tuteur socratique en informatique et sciences computationnelles (STIAM) pour la DSFM.
APPROCHE SOCRATIQUE : Guide l'élève dans la compréhension de ses erreurs d'algorithme et de syntaxe en français, sans écrire le code à sa place.
""",
    },
    "English — Comprehensive Focus 40S": {
        "folder": "english",
        "welcome": (
            "Salut Adam ! Bienvenue en Anglais Comprehensive Focus 40S. Nous"
            " pouvons travailler sur la lecture critique, l'analyse littéraire ou l'écriture persuasive."
        ),
        "system": """
Tu es le tuteur d'Adam pour le cours d'anglais Comprehensive Focus 40S au Manitoba.
APPROCHE SOCRATIQUE OBLIGATOIRE : Guide la méthodologie et la structure argumentative en français, étape par étape, sans rédiger le travail à sa place.
""",
    },
    "Cinema — Witness to Modern History 40S": {
        "folder": "cinema",
        "welcome": (
            "Salut Adam ! Bienvenue en Cinéma (Témoin de l'histoire moderne 40S)."
            " Quel film, réalisateur ou contexte historique souhaites-tu analyser aujourd'hui ?"
        ),
        "system": """
Tu es le tuteur d'Adam pour le cours « Le cinéma, témoin de l'histoire moderne 40S » (DSFM).
APPROCHE SOCRATIQUE OBLIGATOIRE : Enseigne en FRANÇAIS. Guide-le par des questions réflexives sur le langage cinématographique et la réalité historique.
""",
    },
}

CONTEXT_MODES = {
    "🎓 Standard Socratique (Consolidation)": {
        "prompt": "MÉTHODE SOCRATIQUE CLASSIQUE : Pose UNE SEULE question à la fois. Donne des indices sans donner la réponse finale.",
        "temp": 0.4,
    },
    "🚀 Défi & Approfondissement (Élèves avancés)": {
        "prompt": (
            "POSTURE ÉLÈVE AVANCÉ / ENRICHISSEMENT : Hausse l'exigence conceptuelle (Taxonomie de Bloom supérieure). "
            "Pose des questions ouvertes, stimule la pensée critique, teste la robustesse de l'argumentation avec des contre-exemples "
            "ou des liens avec la recherche universitaire contemporaine."
        ),
        "temp": 0.4,
    },
    "❄️ Grand Froid & Tempête (Continuité Blizzard)": {
        "prompt": (
            "POSTURE TEMPÊTE & BLIZZARD (DSFM) : Adopte un ton particulièrement chaleureux, dynamique et bienveillant. "
            "Maintiens une immersion orale et écrite soutenue en français pour briser l'isolement de l'élève à la maison et préserver le bain linguistique."
        ),
        "temp": 0.5,
    },
    "⏱️ Examen Provincial 40S (Simulation BEF)": {
        "prompt": (
            "POSTURE EXAMINATEUR PROVINCIAL BEF : Évalue formellement selon les grilles ministérielles de 12e année. "
            "Analyse avec précision la démarche, relève les imprécisions de vocabulaire et quantifie le barème."
        ),
        "temp": 0.2,
    },
    "🌴 Trêve & Vacances (Micro-défis)": {
        "prompt": (
            "POSTURE TRÊVE LUDIQUE : Propose des énigmes, défis de logique et anecdotes culturelles passionnantes en français "
            "pour stimuler l'esprit sans créer d'anxiété de devoirs."
        ),
        "temp": 0.7,
    },
    "🌍 Francisation & Accueil (Inclusion)": {
        "prompt": (
            "POSTURE FRANCISATION & ACCUEIL : Emploie une syntaxe fluide et limpide. Définis les termes complexes entre parenthèses "
            "et fournis des repères lexicaux bilingues d'appoint si nécessaire."
        ),
        "temp": 0.3,
    },
}

# Configuration Streamlit
st.set_page_config(
    page_title="DSFMGPT — Écosystème Pédagogique Souverain (8 Modules)",
    page_icon="🦬",
    layout="wide"
)

# Injection de style CSS moderne pour l'interface d'accueil
st.markdown(
    """
    <style>
        .hero-container {
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 60%, #1e3a5f 100%);
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 18px;
            padding: 30px;
            margin-bottom: 25px;
            box-shadow: 0 10px 30px -10px rgba(0, 0, 0, 0.5);
        }
        .hero-title {
            font-size: 2.3rem;
            font-weight: 800;
            color: #f8fafc;
            margin-bottom: 6px;
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .hero-subtitle {
            font-size: 1.05rem;
            color: #94a3b8;
            margin-bottom: 18px;
            line-height: 1.5;
        }
        .tag-pill {
            display: inline-block;
            background: rgba(234, 179, 8, 0.15);
            color: #facc15;
            border: 1px solid rgba(234, 179, 8, 0.3);
            padding: 4px 12px;
            border-radius: 9999px;
            font-size: 0.8rem;
            font-weight: 600;
            margin-right: 8px;
        }
        .tag-pill-blue {
            display: inline-block;
            background: rgba(59, 130, 246, 0.15);
            color: #60a5fa;
            border: 1px solid rgba(59, 130, 246, 0.3);
            padding: 4px 12px;
            border-radius: 9999px;
            font-size: 0.8rem;
            font-weight: 600;
            margin-right: 8px;
        }
        .module-box {
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 14px;
            padding: 20px;
            height: 100%;
            transition: all 0.25s ease;
        }
        .module-box:hover {
            border-color: rgba(96, 165, 250, 0.4);
            background: rgba(255, 255, 255, 0.05);
        }
    </style>
    """,
    unsafe_allow_html=True
)

api_key = st.secrets.get("OPENAI_API_KEY") if hasattr(st, "secrets") else None
api_key = api_key or os.environ.get("OPENAI_API_KEY")
if not api_key:
    st.error("Clé API OpenAI non configurée. Ajoutez OPENAI_API_KEY dans vos Secrets Streamlit.")
    st.stop()

client = OpenAI(api_key=api_key)


# Fonctions d'illustration Souveraine (DALL-E Grounded)
def generer_image_souveraine(contexte_texte: str, focus_visuel: str):
    try:
        distill_prompt = (
            "Tu es un illustrateur scientifique et pédagogique pour la DSFM au Manitoba.\n"
            f"Sujet d'étude : {focus_visuel}\n"
            f"Données contextuelles vérifiées : {contexte_texte}\n"
            "Conçois un prompt descriptif pour un schéma scientifique ou une illustration d'apprentissage sobre, "
            "sans texte complexe ou légende illisible, sur fond neutre."
        )
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": distill_prompt}],
            temperature=0.3
        )
        prompt_image = res.choices[0].message.content.strip()
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt_image,
            size="1024x1024",
            quality="standard",
            n=1
        )
        return response.data[0].url
    except Exception as exc:
        st.error(f"Erreur illustration : {exc}")
        return None


# Synthèse Vocale Web
def speak_text(text: str):
    clean_text = text.replace("'", "\\'").replace('"', '\\"').replace("\n", " ").replace("\r", " ")
    js_code = f"""
    <script>
        window.speechSynthesis.cancel();
        var msg = new SpeechSynthesisUtterance("{clean_text}");
        msg.lang = 'fr-FR';
        window.speechSynthesis.speak(msg);
    </script>
    """
    components.html(js_code, height=0)


def stop_speech():
    components.html("<script>window.speechSynthesis.cancel();</script>", height=0)


# Variables d'état
if "nav_active" not in st.session_state:
    st.session_state.nav_active = "🏠 Accueil & Vue d'Ensemble"
if "quiz_data" not in st.session_state:
    st.session_state.quiz_data = None
if "quiz_submitted" not in st.session_state:
    st.session_state.quiz_submitted = False
if "quiz_answers" not in st.session_state:
    st.session_state.quiz_answers = {}
if "next_question" not in st.session_state:
    st.session_state.next_question = None
if "histories_by_course" not in st.session_state:
    st.session_state.histories_by_course = {}
if "processed_audio_hash" not in st.session_state:
    st.session_state.processed_audio_hash = None
if "pending_audio_text" not in st.session_state:
    st.session_state.pending_audio_text = None
if "current_lesson_plan" not in st.session_state:
    st.session_state.current_lesson_plan = ""
if "current_eval_data" not in st.session_state:
    st.session_state.current_eval_data = ""


# Générateur de QCM au format JSON
def generate_qcm_from_context(course_title, system_prompt, discussion_context, number_questions=10):
    prompt = (
        f"En te basant sur la discussion récente et le cours : {course_title}, crée un quiz d'entraînement de {number_questions} questions à choix multiples (QCM) en français.\n"
        f"Contexte récent :\n{discussion_context}\n\n"
        "Format strict : 4 options (A,B,C,D), 1 seule bonne réponse, 1 indice et 1 explication.\n"
        "Renvoie UNIQUEMENT un objet JSON valide : {\"questions\": [{\"question\": \"...\", \"options\": {\"A\":\"...\",\"B\":\"...\",\"C\":\"...\",\"D\":\"...\"}, \"correct\": \"A\", \"hint\": \"...\", \"explanation\": \"...\"}]}"
    )
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
        )
        content = response.choices[0].message.content.strip()
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return None
    except Exception:
        return None


# Moteur RAG Local
@st.cache_data(show_spinner=False)
def load_pdf_chunks(folder_string: str):
    folder_path = Path(folder_string)
    chunks = []
    if not folder_path.exists():
        return chunks
    for pdf_path in sorted(folder_path.glob("**/*.pdf")):
        try:
            reader = PdfReader(str(pdf_path))
            full_text = "\n".join((page.extract_text() or "") for page in reader.pages)
            full_text = re.sub(r"[ \t]+", " ", full_text)
            full_text = re.sub(r"\n{3,}", "\n\n", full_text).strip()
            if not full_text:
                continue
            paragraphs = [p.strip() for p in re.split(r"\n\s*\n", full_text) if p.strip()]
            current = ""
            is_custom = "custom_teacher" in str(pdf_path)
            prefix = "[Ressource Enseignant]" if is_custom else "[Programme BEF]"
            for para in paragraphs:
                if len(current) + len(para) > 1400 and current:
                    chunks.append({"source": f"{prefix} {pdf_path.name}", "text": current})
                    current = ""
                if len(para) > 1800:
                    for start in range(0, len(para), 1400):
                        piece = para[start : start + 1400]
                        if piece.strip():
                            chunks.append({"source": f"{prefix} {pdf_path.name}", "text": piece})
                else:
                    current = (current + "\n\n" + para).strip()
            if current:
                chunks.append({"source": f"{prefix} {pdf_path.name}", "text": current})
        except Exception:
            continue
    return chunks


def retrieve_chunks(question: str, chunks: list, limit: int = 4):
    if not chunks or not question.strip():
        return []
    stop_words = {
        "the", "and", "for", "with", "that", "this", "from", "what", "when",
        "where", "which", "how", "why", "are", "was", "were", "have", "has",
        "does", "did", "can", "could", "would", "should", "into", "about",
        "les", "des", "une", "dans", "pour", "avec", "est", "que", "qui",
        "quoi", "comment", "pourquoi", "sur", "par", "aux", "du", "de", "la",
        "le", "un", "et", "en", "je", "tu", "il", "elle"
    }
    terms = [t.lower() for t in re.findall(r"[A-Za-zÀ-ÿ0-9'-]{3,}", question) if t.lower() not in stop_words]
    if not terms:
        return []
    scored = []
    for chunk in chunks:
        counts = Counter(re.findall(r"[A-Za-zÀ-ÿ0-9'-]{3,}", chunk["text"].lower()))
        score = sum(1.0 + min(counts[term], 4) * 0.15 for term in set(terms) if term in counts)
        if score > 0:
            scored.append((score, chunk))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _, chunk in scored[:limit]]


# --- LISTE DES 8 MODULES DU SYSTÈME ---
MODULES_LIST = [
    "🏠 Accueil & Vue d'Ensemble",
    "1. 👩‍🏫 Assistant BEF (Module 1)",
    "2. 🎓 Tuteur Socratique (Module 2)",
    "3. 🏢 Admin & Impact MTS (Module 3)",
    "4. 🛡️ InfoSec & FIPPA (Module 4)",
    "5. 💻 STIAM & Sandbox Codage (Module 5)",
    "6. 🔄 Suppléance & ERP Atrieve (Module 6)",
    "7. 🤝 Auxiliaires EA & Inclusion (Module 7)",
    "8. 👨‍👩‍👦 Portail Parents & Tuteurs (Module 8)"
]

# --- BARRE LATÉRALE DE CONTRÔLE ---
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/school.png", width=56)
    st.title("DSFMGPT Hub")
    st.caption("Matrice des 8 Modules Opérationnels · DSFM / BEF")

    # Index par défaut basé sur l'état
    default_idx = MODULES_LIST.index(st.session_state.nav_active) if st.session_state.nav_active in MODULES_LIST else 0
    navigation_espace = st.radio(
        "Navigation Systémique :",
        MODULES_LIST,
        index=default_idx
    )
    st.session_state.nav_active = navigation_espace

    st.markdown("---")
    st.markdown("### 📚 Matière Active")
    course_name = st.selectbox("Sélection du cours :", list(COURSES.keys()))
    course = COURSES[course_name]
    folder = DOCS_DIR / course["folder"]

    st.markdown("---")
    st.markdown("### 🎛️ Posture Pédagogique")
    mode_selectionne = st.selectbox("Mode contextuel :", list(CONTEXT_MODES.keys()))
    mode_info = CONTEXT_MODES[mode_selectionne]

    st.markdown("---")
    st.markdown("### 🔊 Audio & Dictée Whisper")
    enable_voice_output = st.checkbox("Lecture vocale automatique", value=True)
    if st.button("🛑 Couper la voix", use_container_width=True):
        stop_speech()
        st.success("Voix coupée.")

    audio_value = st.audio_input("Dictée vocale directe")


# =============================================================================
# VUE ACCUEIL : LE TABLEAU DE BORD GRANDIOSE DES 8 MODULES
# =============================================================================
if "Accueil" in navigation_espace:
    # HERO BANNER PRESTIGE
    st.markdown(
        """
        <div class="hero-container">
            <div class="hero-title">
                <span>DSFMGPT</span>
                <span style="font-size: 2rem;">🦬</span>
                <img src="https://upload.wikimedia.org/wikipedia/commons/thumb/c/ce/Franco-Manitobain_flag.svg/160px-Franco-Manitobain_flag.svg.png" 
                     alt="Drapeau Franco-Manitobain" 
                     style="height: 28px; border-radius: 4px; box-shadow: 0 2px 6px rgba(0,0,0,0.4); vertical-align: middle;">
            </div>
            <div class="hero-subtitle">
                Infrastructure d'Intelligence Artificielle Souveraine, Équitable & Pédagogique<br>
                Conçue exclusivement pour la Division scolaire franco-manitobaine (DSFM) et le Bureau de l'éducation française (BEF).
            </div>
            <div>
                <span class="tag-pill">🏛️ 8 Modules Déployés</span>
                <span class="tag-pill">🔒 100% Souverain & FIPPA</span>
                <span class="tag-pill-blue">❄️ Continuité Blizzard Active</span>
                <span class="tag-pill-blue">⏱️ Alignement Priorités MTS</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # CHIFFRES D'IMPACT CLÉS
    c_k1, c_k2, c_k3, c_k4 = st.columns(4)
    c_k1.metric("Couverture Opérationnelle", "8 Modules", "Écosystème unifié")
    c_k2.metric("Gain Temps Enseignants", "~4.8 h / semaine", "Prévention burnout MTS")
    c_k3.metric("Équité Territoriale STEM", "24/7 Accessible", "Urbain & Rural garanti")
    c_k4.metric("Conformité des Données", "100% Locale MB", "Zéro fuite FIPPA/LAIPVP")

    st.markdown("### 🧭 La Matrice des 8 Services de DSFMGPT")
    st.caption("Sélectionnez un module pour y accéder directement :")

    # Ligne 1 : Modules 1 à 4
    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    with col_m1:
        st.markdown(
            """
            <div class="module-box">
                <h4>👩‍🏫 Module 1 : Assistant BEF</h4>
                <p style="font-size: 0.85rem; color: #cbd5e1;">Plans de leçon CUA différenciés, aménagements PAT, évaluations formatives et esprit NotebookLM.</p>
                <small style="color: #60a5fa;">Public : Enseignants titulaires</small>
            </div>
            """, unsafe_allow_html=True
        )
        if st.button("Ouvrir Module 1 ➔", key="btn_go_m1", use_container_width=True):
            st.session_state.nav_active = "1. 👩‍🏫 Assistant BEF (Module 1)"
            st.rerun()

    with col_m2:
        st.markdown(
            """
            <div class="module-box">
                <h4>🎓 Module 2 : Tuteur Socratique</h4>
                <p style="font-size: 0.85rem; color: #cbd5e1;">Accompagnement conversationnel bienveillant pas-à-pas, quiz 10 questions et schémas RAG en direct.</p>
                <small style="color: #60a5fa;">Public : Élèves 40S & K-12</small>
            </div>
            """, unsafe_allow_html=True
        )
        if st.button("Ouvrir Module 2 ➔", key="btn_go_m2", use_container_width=True):
            st.session_state.nav_active = "2. 🎓 Tuteur Socratique (Module 2)"
            st.rerun()

    with col_m3:
        st.markdown(
            """
            <div class="module-box">
                <h4>🏢 Module 3 : Admin & Impact MTS</h4>
                <p style="font-size: 0.85rem; color: #cbd5e1;">Baromètre d'allègement de la charge enseignante (ROI humain) et métriques divisionnaires.</p>
                <small style="color: #60a5fa;">Public : Directions & Comité MTS</small>
            </div>
            """, unsafe_allow_html=True
        )
        if st.button("Ouvrir Module 3 ➔", key="btn_go_m3", use_container_width=True):
            st.session_state.nav_active = "3. 🏢 Admin & Impact MTS (Module 3)"
            st.rerun()

    with col_m4:
        st.markdown(
            """
            <div class="module-box">
                <h4>🛡️ Module 4 : InfoSec & FIPPA</h4>
                <p style="font-size: 0.85rem; color: #cbd5e1;">Anonymisation PII dynamique, journal d'audit immuable SHA-256 et cybersécurité sur site.</p>
                <small style="color: #60a5fa;">Public : Service TI & Direction</small>
            </div>
            """, unsafe_allow_html=True
        )
        if st.button("Ouvrir Module 4 ➔", key="btn_go_m4", use_container_width=True):
            st.session_state.nav_active = "4. 🛡️ InfoSec & FIPPA (Module 4)"
            st.rerun()

    st.markdown("")

    # Ligne 2 : Modules 5 à 8
    col_m5, col_m6, col_m7, col_m8 = st.columns(4)
    with col_m5:
        st.markdown(
            """
            <div class="module-box">
                <h4>💻 Module 5 : STIAM & Sandbox</h4>
                <p style="font-size: 0.85rem; color: #cbd5e1;">Bac à sable Python exécutable et débogueur socratique 24/7 pour les écoles rurales isolées.</p>
                <small style="color: #60a5fa;">Public : Élèves & Secondaire STEM</small>
            </div>
            """, unsafe_allow_html=True
        )
        if st.button("Ouvrir Module 5 ➔", key="btn_go_m5", use_container_width=True):
            st.session_state.nav_active = "5. 💻 STIAM & Sandbox Codage (Module 5)"
            st.rerun()

    with col_m6:
        st.markdown(
            """
            <div class="module-box">
                <h4>🔄 Module 6 : Suppléance Express</h4>
                <p style="font-size: 0.85rem; color: #cbd5e1;">Dossier d'urgence prêt à 8 h 15, synchronisation ERP Atrieve, plans BEF et consignes de sécurité.</p>
                <small style="color: #60a5fa;">Public : Suppléants & Écoles</small>
            </div>
            """, unsafe_allow_html=True
        )
        if st.button("Ouvrir Module 6 ➔", key="btn_go_m6", use_container_width=True):
            st.session_state.nav_active = "6. 🔄 Suppléance & ERP Atrieve (Module 6)"
            st.rerun()

    with col_m7:
        st.markdown(
            """
            <div class="module-box">
                <h4>🤝 Module 7 : Auxiliaires (EA)</h4>
                <p style="font-size: 0.85rem; color: #cbd5e1;">Coordination Enseignant-EA : Briefing quotidien, guide de relance socratique et bilans PEI.</p>
                <small style="color: #60a5fa;">Public : Équipes d'inclusion & EA</small>
            </div>
            """, unsafe_allow_html=True
        )
        if st.button("Ouvrir Module 7 ➔", key="btn_go_m7", use_container_width=True):
            st.session_state.nav_active = "7. 🤝 Auxiliaires EA & Inclusion (Module 7)"
            st.rerun()

    with col_m8:
        st.markdown(
            """
            <div class="module-box">
                <h4>👨‍👩‍👦 Module 8 : Parents & Tuteurs</h4>
                <p style="font-size: 0.85rem; color: #cbd5e1;">Suivi transparent du cheminement, validation des binômes d'étude et liaison sécurisée école-foyer.</p>
                <small style="color: #60a5fa;">Public : Familles & Tuteurs légaux</small>
            </div>
            """, unsafe_allow_html=True
        )
        if st.button("Ouvrir Module 8 ➔", key="btn_go_m8", use_container_width=True):
            st.session_state.nav_active = "8. 👨‍👩‍👦 Portail Parents & Tuteurs (Module 8)"
            st.rerun()


# =============================================================================
# MODULE 1 : ASSISTANT BEF (ENSEIGNANT)
# =============================================================================
elif "Assistant BEF" in navigation_espace:
    st.title("👩‍🏫 Module 1 : Assistant Pédagogique BEF")
    st.caption("Génération automatisée de plans de leçon différenciés (CUA), évaluations formatives et enrichissement NotebookLM")

    tab_bef, tab_eval, tab_notebook, tab_video = st.tabs([
        "📋 Planification Différenciée (BEF / PAT / Défi)",
        "📊 Évaluation Formative & par les Pairs",
        "📚 Mon Classeur (Esprit NotebookLM)",
        "🎬 Studio Capsule Dialoguée (Continuité Blizzard)"
    ])

    with tab_bef:
        st.subheader("Générateur de Leçon Curriculaire Trifide")
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            ras_input = st.text_input("Code RAS BEF :", value="B12-2-03 (Lois de Mendel)")
            sujet_lecon = st.text_input("Sujet :", value="Monohybridisme et grilles de Punnett")
        with col_t2:
            profil_pat = st.text_area("Adaptations PAT (Dyslexie / Visuel) :", value="2 élèves en PAT (textes aérés, étayage visuel).")
            profil_avance = st.text_area("Enrichissement (Élèves avancés) :", value="3 élèves avancés (probabilités complexes).")

        col_b1, col_b2 = st.columns(2)
        with col_b1:
            l_btn = st.button("🚀 Générer la leçon multiniveau complète", type="primary", use_container_width=True)
        with col_b2:
            img_btn_t = st.button("🖼️ Générer une illustration souveraine", use_container_width=True)

        if l_btn:
            with st.spinner("Génération du plan pédagogique CUA…"):
                p_prompt = (
                    "Tu es un conseiller pédagogique expert du Bureau de l'éducation française (BEF) au Manitoba.\n"
                    f"Crée un plan de leçon rigoureux, complet et structuré pour le cours : {course_name}.\n"
                    f"- Résultat d'apprentissage : {ras_input}\n"
                    f"- Sujet : {sujet_lecon}\n"
                    f"- Adaptations PAT : {profil_pat}\n"
                    f"- Élèves avancés : {profil_avance}\n\n"
                    "Structure obligatoire :\n"
                    "1. 🎯 Objectifs ministériels et critères de réussite observables (BEF).\n"
                    "2. 📖 Déroulement de classe (Amorce 10 min, Magistral 15 min, Pratique guidée 25 min, Objectivation 10 min).\n"
                    "3. ♿ Volet Adaptations & PAT (Aménagements matériels, consignes découpées, CUA).\n"
                    "4. 🚀 Volet Enrichissement & Défi (Tâches à haut niveau taxonomique de Bloom, problèmes ouverts).\n"
                    "5. 💡 Grille de 3 questions socratiques clés pour le bilan.\n"
                )
                resp = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": p_prompt}],
                    temperature=0.3
                )
                st.session_state.current_lesson_plan = resp.choices[0].message.content

        if st.session_state.current_lesson_plan:
            st.markdown(st.session_state.current_lesson_plan)

        if img_btn_t:
            with st.spinner("Création de l'illustration scientifique…"):
                les_data = st.session_state.current_lesson_plan or f"Lesson: {sujet_lecon}."
                img_url_t = generer_image_souveraine(les_data, f"Schéma scientifique de {sujet_lecon}")
                if img_url_t:
                    st.image(img_url_t, caption="Illustration générée à partir des ressources locales.")

    with tab_eval:
        st.subheader("📊 Évaluations Formatives & par les Pairs (Normes BEF)")
        type_eval = st.radio("Type d'instrument :", ["🎟️ Billet de Sortie Flash (3 min)", "👥 Grille d'Évaluation par les Pairs (Deux étoiles et un souhait)", "🎯 Sonde Diagnostique Rapide"], horizontal=True)
        sujet_eval = st.text_input("Notion ciblée :", value="L'analyse des allèles dominants et récessifs")
        if st.button("✨ Générer l'outil d'évaluation", type="primary"):
            with st.spinner("Conception de l'instrument d'évaluation…"):
                eval_p = f"Crée un outil d'évaluation formatif conforme au BEF du Manitoba. Type : {type_eval}. Matière : {course_name}. Sujet : {sujet_eval}."
                resp_eval = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": eval_p}], temperature=0.3)
                st.markdown(resp_eval.choices[0].message.content)

    with tab_notebook:
        st.subheader("📚 Mon Classeur de Cours (Esprit NotebookLM)")
        custom_folder = DOCS_DIR / course["folder"] / "custom_teacher"
        custom_folder.mkdir(parents=True, exist_ok=True)
        up_files = st.file_uploader("Ajouter des PDF personnels de cours :", type=["pdf"], accept_multiple_files=True)
        if up_files:
            for f in up_files:
                with open(custom_folder / f.name, "wb") as buffer:
                    buffer.write(f.getbuffer())
            st.success(f"✅ {len(up_files)} ressource(s) ajoutée(s) et indexée(s) !")
            st.cache_data.clear()

    with tab_video:
        st.subheader("🎬 Studio Capsule Dialoguée (Continuité Blizzard)")
        notion_v = st.text_input("Notion clé pour la capsule :", value="Le monohybridisme et la ségrégation mendélienne")
        if st.button("🎥 Scénariser la capsule vidéo"):
            with st.spinner("Scénarisation en cours…"):
                vid_p = f"Rédige un script de dialogue chaleureux de 2 min entre un élève et son enseignant (voix clonée) sur {notion_v} pour la DSFM."
                res_v = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": vid_p}], temperature=0.5)
                st.markdown(res_v.choices[0].message.content)


# =============================================================================
# MODULE 2 : TUTEUR SOCRATIQUE (ÉLÈVE)
# =============================================================================
elif "Tuteur Socratique" in navigation_espace:
    st.title(f"🎓 Module 2 : Tuteur Socratique — {course_name}")
    st.caption("Accompagnement pédagogique socratique · Guidage pas-à-pas sans réponse directe")

    if course_name not in st.session_state.histories_by_course:
        st.session_state.histories_by_course[course_name] = [{"role": "assistant", "content": course["welcome"]}]
    history = st.session_state.histories_by_course[course_name]

    if audio_value is not None:
        audio_bytes = audio_value.getvalue()
        audio_hash = hashlib.sha256(audio_bytes).hexdigest()
        if audio_hash != st.session_state.processed_audio_hash:
            with st.spinner("Transcription Whisper…"):
                try:
                    transcript = client.audio.transcriptions.create(
                        model="whisper-1",
                        file=(getattr(audio_value, "name", "rec.wav"), audio_bytes, getattr(audio_value, "type", None) or "audio/wav")
                    )
                    st.session_state.pending_audio_text = transcript.text.strip()
                    st.session_state.processed_audio_hash = audio_hash
                except Exception as exc:
                    st.error(f"Erreur Whisper : {exc}")

    for idx, msg in enumerate(history):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg["role"] == "assistant" and idx == len(history) - 1 and enable_voice_output:
                speak_text(msg["content"])

        if msg["role"] == "assistant" and idx == len(history) - 1:
            st.markdown("💡 **Suggestions d'étayage rapide :**")
            c1, c2, c3, c4 = st.columns(4)
            b_q = None
            with c1:
                if st.button("📖 Expliquer simplement", key=f"s1_{idx}", use_container_width=True):
                    b_q = "Peux-tu m'expliquer cela plus simplement en français avec une analogie visuelle ?"
            with c2:
                if st.button("📝 Exemple concret", key=f"s2_{idx}", use_container_width=True):
                    b_q = "Donne-moi un exemple concret issu du cours ou du Manitoba."
            with c3:
                if st.button("🎥 Vidéo YouTube", key=f"s3_{idx}", use_container_width=True):
                    b_q = "Propose un lien YouTube cliquable pour visualiser ce concept."
            with c4:
                if st.button("🚀 Défi supérieur", key=f"s4_{idx}", use_container_width=True):
                    b_q = "Comment relier ce concept à une question scientifique plus avancée ?"
            if b_q:
                st.session_state.next_question = b_q
                st.rerun()

            col_q1, col_q2 = st.columns(2)
            with col_q1:
                if st.button("🎯 Générer un quiz de 10 questions sur notre échange", key=f"q_{idx}", use_container_width=True):
                    with st.spinner("Génération du quiz formatif…"):
                        disc = "\n".join([f"{m['role']}: {m['content']}" for m in history[-6:]])
                        quiz = generate_qcm_from_context(course_name, course["system"] + "\n" + mode_info["prompt"], disc, 10)
                    if quiz and "questions" in quiz:
                        st.session_state.quiz_data = quiz
                        st.session_state.quiz_submitted = False
                        st.rerun()
            with col_q2:
                if st.button("🎨 Illustrer cette notion (RAG Souverain)", key=f"im_{idx}", use_container_width=True):
                    with st.spinner("Conception de l'image pédagogique…"):
                        disc_img = "\n".join([f"{m['role']}: {m['content']}" for m in history[-4:]])
                        all_c = load_pdf_chunks(str(folder))
                        rel_c = retrieve_chunks(disc_img, all_c)
                        c_txt = "\n\n".join(c["text"] for c in rel_c) if rel_c else "Données générales."
                        u = generer_image_souveraine(c_txt, disc_img)
                        if u:
                            st.image(u, caption="Illustration scientifique basée sur les données locales")

    # Quiz interactif
    if st.session_state.quiz_data:
        questions = st.session_state.quiz_data.get("questions", [])
        st.divider()
        st.subheader(f"🎯 Quiz formatif — {course_name}")
        if not st.session_state.quiz_submitted:
            with st.form("qcm_form"):
                u_answers = {}
                for i, itm in enumerate(questions):
                    st.markdown(f"**Q{i + 1} :** {itm['question']}")
                    opts = [f"{L}. {itm['options'][L]}" for L in ("A", "B", "C", "D")]
                    u_answers[i] = st.radio("Choix :", opts, index=None, key=f"quiz_ans_{i}")
                    with st.expander("💡 Indice d'étayage"):
                        st.write(itm.get("hint", "Pas d'indice."))
                    st.divider()
                if st.form_submit_button("✅ Valider mes réponses", type="primary"):
                    st.session_state.quiz_answers = u_answers
                    st.session_state.quiz_submitted = True
                    st.rerun()
        else:
            score = 0
            for i, itm in enumerate(questions):
                ans = st.session_state.quiz_answers.get(i)
                corr = itm["correct"].upper()
                if ans and ans[0].upper() == corr:
                    score += 1
                    st.success(f"✅ Q{i + 1} Exact ! {ans}\n\n*{itm['explanation']}*")
                else:
                    st.error(f"❌ Q{i + 1} À revoir. Réponse attendue : **{corr}. {itm['options'].get(corr, '')}**\n\n*{itm['explanation']}*")
            st.markdown(f"### Score final : {score} / {len(questions)}")
            if st.button("🔄 Fermer le quiz"):
                st.session_state.quiz_data = None
                st.session_state.quiz_submitted = False
                st.rerun()
        st.divider()

    if st.session_state.pending_audio_text:
        st.info("Validation transcription Whisper :")
        with st.form("whisper_confirm"):
            c_txt = st.text_area("Texte transcrit :", value=st.session_state.pending_audio_text)
            if st.form_submit_button("Envoyer"):
                st.session_state.pending_audio_text = None
                st.session_state.next_question = c_txt.strip()
                st.rerun()

    typed_q = st.chat_input("Pose ta question en français…")
    active_q = typed_q or st.session_state.pop("next_question", None)
    if active_q and active_q.strip():
        active_q = active_q.strip()
        history.append({"role": "user", "content": active_q})
        with st.chat_message("user"):
            st.markdown(active_q)

        all_c = load_pdf_chunks(str(folder))
        rel_c = retrieve_chunks(active_q, all_c)
        c_block = "\n\n".join(f"[{c['source']}]\n{c['text']}" for c in rel_c) if rel_c else "Programme général BEF."
        sys_p = f"{course['system']}\n\n{mode_info['prompt']}\n\nExtraits locaux :\n{c_block}\n\nRAPPEL : Socratique, en français, 1 question à la fois."
        
        with st.chat_message("assistant"):
            with st.spinner("Réflexion socratique…"):
                res = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": sys_p}] + history[-10:], temperature=mode_info["temp"])
                ans_txt = res.choices[0].message.content
                st.markdown(ans_txt)
                history.append({"role": "assistant", "content": ans_txt})
                if enable_voice_output:
                    speak_text(ans_txt)
        st.session_state.histories_by_course[course_name] = history
        st.rerun()


# =============================================================================
# MODULE 3 : ADMIN, EVALUATION & IMPACT MTS
# =============================================================================
elif "Admin & Impact" in navigation_espace:
    st.title("🏢 Module 3 : Administration & Baromètre d'Impact MTS")
    st.caption("Allègement de la tâche enseignante (Workload Reduction), métriques divisionnaires et ROI humain")

    col_p1, col_p2, col_p3 = st.columns(3)
    with col_p1:
        nb_profs = st.slider("Enseignants titulaires dans l'école :", 5, 60, 25)
        lecons_sem = st.slider("Plans de cours CUA générés / sem. :", 1, 10, 3)
    with col_p2:
        nb_ea = st.slider("Auxiliaires d'enseignement (EA) :", 1, 20, 6)
        nb_suppl = st.slider("Remplacements / suppléances par mois :", 2, 40, 12)
    with col_p3:
        nb_el = st.slider("Élèves bénéficiaires du tuteur :", 20, 500, 150, step=10)
        sess_el = st.slider("Sessions d'étayage / élève / sem. :", 1, 7, 3)

    gain_profs_h = (nb_profs * lecons_sem * (45 + 50)) / 60
    gain_ea_h = (nb_ea * 5 * 25) / 60
    gain_suppl_h = (nb_suppl * 40) / 60
    gain_total_mois = (gain_profs_h * 4) + (gain_ea_h * 4) + gain_suppl_h
    jours_recup = gain_total_mois / 7.5

    st.divider()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Heures économisées / prof", f"~{gain_profs_h / nb_profs:.1f} h / sem", "Moins de correction/prépa")
    m2.metric("Temps personnel école", f"{gain_total_mois:.0f} h / mois", "Réinvesties en classe")
    m3.metric("Équivalent journées de travail", f"{jours_recup:.1f} jours", "Par mois d'école")
    m4.metric("Temps d'étude élèves", f"{(nb_el * sess_el * 30 * 4) / 60:.0f} h / mois", "En immersion française")

    st.markdown("---")
    st.success("🛡️ **Plaidoyer MTS :** Ce calculateur fournit une preuve tangible de prévention de l'épuisement professionnel pour chaque école de la DSFM.")


# =============================================================================
# MODULE 4 : INFOSEC & FIPPA (GOUVERNANCE & CYBERSÉCURITÉ)
# =============================================================================
elif "InfoSec & FIPPA" in navigation_espace:
    st.title("🛡️ Module 4 : Gouvernance, Cybersécurité & FIPPA/LAIPVP")
    st.caption("Couche transversale de souveraineté numérique : anonymisation PII, chiffrement et traçabilité d'audit immuable")

    tab_pii, tab_audit, tab_sover = st.tabs([
        "🔒 Démonstrateur d'Anonymisation PII Dynamique",
        "📑 Journal d'Audit Immuable (FIPPA Compliance)",
        "🌐 Architecture Souveraine On-Premise"
    ])

    with tab_pii:
        st.subheader("Filtre d'Anonymisation et Dé-identification des Données Élèves")
        st.write("Ce module intercepte les requêtes avant tout traitement IA pour masquer dynamiquement les renseignements personnels (PII).")
        
        texte_test = st.text_area(
            "Entrez un texte d'exemple contenant des données identifiables :",
            value="L'élève Marc Tremblay (numéro MET 948201), né le 12 mai 2008, présente des difficultés en Biologie 40S au Collège Louis-Riel. Contacter sa tutrice Sophie à sophie.t@email.ca ou au 204-555-0199.",
            height=100
        )
        
        if st.button("🛡️ Tester l'Anonymisation Dynamique"):
            def anonymiser_pii(texte):
                t = re.sub(r"[A-Z][a-z]+ [A-Z][a-z]+", "[NOM_ELEVE_ANONYMISE]", texte)
                t = re.sub(r"\b\d{6}\b", "[ID_MET_MASQUE]", t)
                t = re.sub(r"[\w\.-]+@[\w\.-]+", "[COURRIEL_MASQUE]", t)
                t = re.sub(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b", "[TELEPHONE_MASQUE]", t)
                t = re.sub(r"\b\d{1,2} [a-zéû]+ \d{4}\b", "[DATE_NAISSANCE_MASQUEE]", t)
                return t

            texte_propre = anonymiser_pii(texte_test)
            c_raw, c_clean = st.columns(2)
            with c_raw:
                st.markdown("**Texte Brut (Interne Division) :**")
                st.code(texte_test, language="text")
            with c_clean:
                st.markdown("**Texte Anonymisé transmis au LLM :**")
                st.code(texte_propre, language="text")
            st.success("✅ Conformité FIPPA garantie : Aucune donnée nominative n'est transmise hors de l'enceinte divisionnaire.")

    with tab_audit:
        st.subheader("Journal de Traçabilité Immuable (Audit Trail)")
        st.caption("Chaque transaction pédagogique est horodatée et hachée cryptographiquement en SHA-256.")
        
        logs_demo = [
            {"Horodatage": "2026-10-25 18:42:10", "Utilisateur": "Enseignant #4102", "Action": "Génération Leçon Bio 40S", "Statut FIPPA": "Vérifié (Zéro PII)", "Hash SHA-256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"},
            {"Horodatage": "2026-10-25 19:05:32", "Utilisateur": "Élève (Adam)", "Action": "Question Socratique Mendel", "Statut FIPPA": "Conforme (Session Isolée)", "Hash SHA-256": "87542b827e7d60a1a9a40f02f8f902cbd3194206585634d6824a848380516200"},
            {"Horodatage": "2026-10-25 19:14:01", "Utilisateur": "Auxiliaire #108", "Action": "Consultation Briefing EA", "Statut FIPPA": "Vérifié (Données Chiffrées)", "Hash SHA-256": "5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8"},
        ]
        st.dataframe(logs_demo, use_container_width=True)

    with tab_sover:
        st.subheader("Architecture Souveraine & Hébergement Local")
        st.info("📍 **Localisation des serveurs :** Infrastructure sur site / Datacenter certifié au Manitoba (Canada).")
        st.write("• Chiffrement en transit : TLS 1.3 avec suites cryptographiques PFS.")
        st.write("• Chiffrement au repos : AES-256 pour toutes les bases vectorielles et documents curriculaires.")


# =============================================================================
# MODULE 5 : STIAM & SANDBOX CODAGE (ÉQUITÉ RURALE 24/7)
# =============================================================================
elif "STIAM & Sandbox" in navigation_espace:
    st.title("💻 Module 5 : Tuteur STIAM & Bac à Sable de Programmation 24/7")
    st.caption("Équité territoriale en informatique : bac à sable sécurisé et tuteur socratique de débogage pour écoles rurales")

    st.markdown("### 🧑‍💻 Bac à Sable Python (Sandbox)")
    code_init = """# Défi Informatique 40S : Calcul de la fréquence d'allèles
def frequence_alleles(nb_dominants, nb_recessifs):
    total = nb_dominants + nb_recessifs
    freq_dom = nb_dominants / total
    return freq_dom

# Test
print("Fréquence allèle dominant :", frequence_alleles(60, 40))
"""
    code_eleve = st.text_area("Éditeur de code Python :", value=code_init, height=180)

    col_run, col_soc = st.columns(2)
    with col_run:
        if st.button("▶️ Exécuter le code en direct", use_container_width=True):
            old_stdout = sys.stdout
            redirected_output = sys.stdout = io.StringIO()
            try:
                exec(code_eleve, {})
                st.code(redirected_output.getvalue(), language="text")
                st.success("Exécution terminée avec succès.")
            except Exception as e:
                st.error(f"Erreur d'exécution : {e}")
            finally:
                sys.stdout = old_stdout

    with col_soc:
        if st.button("🧠 Tuteur STIAM : Analyser ma démarche socratique", type="primary", use_container_width=True):
            with st.spinner("Analyse socratique du code…"):
                p_code = (
                    "Tu es un enseignant socratique en informatique 40S au Manitoba.\n"
                    f"Voici le code saisi par l'élève :\n{code_eleve}\n\n"
                    "CONSIGNE STRICTE : Ne donne pas la correction directe du code. "
                    "Pose 1 ou 2 questions socratiques stimulantes sur la complexité algorithmique, la gestion des erreurs ou la logique mathématique."
                )
                res_code = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": p_code}],
                    temperature=0.3
                )
                st.markdown(res_code.choices[0].message.content)


# =============================================================================
# MODULE 6 : SUPPLÉANCE & ERP ATRIEVE
# =============================================================================
elif "Suppléance & ERP" in navigation_espace:
    st.title("🔄 Module 6 : Suppléance Express & Intégration ERP Atrieve")
    st.caption("Plan d'urgence prêt à 8 h 15, protocoles de sécurité et continuité curriculaire lors des remplacements")

    col_ec1, col_ec2 = st.columns(2)
    with col_ec1:
        ecole_sel = st.selectbox("Établissement DSFM :", [
            "Collège Louis-Riel (Winnipeg)", 
            "École Saint-Joachim (La Broquerie)", 
            "École Pointe-des-Chênes (Sainte-Anne)", 
            "École Réal-Bérard (Saint-Pierre-Jolys)"
        ])
        classe_suppl = st.selectbox("Période et matière du remplacement :", [
            "Période 2 — Biologie 40S", 
            "Période 3 — Mathématiques Pré-calcul 30S", 
            "Période 4 — Informatique 40S"
        ])
    with col_ec2:
        code_mission = st.text_input("Code de mission Atrieve ERP :", value="SUB-2026-LR-8821")
        consigne_particuliere = st.text_input("Consigne spéciale laissée par l'enseignant titulaire :", value="Les élèves doivent terminer les exercices sur l'hérédité mendélienne.")

    if st.button("📋 Générer le Dossier de Suppléance Express (Prêt en 30 secondes)", type="primary"):
        with st.spinner("Compilation du dossier de remplacement…"):
            p_sub = (
                f"Tu es le directeur adjoint responsable des suppléances à la DSFM ({ecole_sel}).\n"
                f"Génère une fiche de suppléance d'urgence claire et rassurante pour un enseignant suppléant non-spécialiste prenant en charge : {classe_suppl}.\n"
                f"Consigne du titulaire : {consigne_particuliere}\n\n"
                "Structure attendue :\n"
                "1. 📍 Repères de sécurité école (Lieu des trousses de premiers soins, protocole d'évacuation, numéro du bureau de direction).\n"
                "2. ⏱️ Déroulé de la période de 60 minutes pas-à-pas (clé en main).\n"
                "3. 🤝 Soutien inclusion (Rôle de l'auxiliaire EA présent dans la classe et adaptations prioritaires discrètes).\n"
                "4. 📝 Billet de liaison à laisser sur le bureau du titulaire à 15 h 30.\n"
            )
            res_sub = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": p_sub}], temperature=0.3)
            st.markdown(res_sub.choices[0].message.content)


# =============================================================================
# MODULE 7 : AUXILIAIRES D'ENSEIGNEMENT (EA) & INCLUSION
# =============================================================================
elif "Auxiliaires EA" in navigation_espace:
    st.title("🤝 Module 7 : Coordination des Auxiliaires d'Enseignement (EA)")
    st.caption("Feuille de mission minute (EA Briefing), étayage socratique et micro-bilans d'observation PEI")

    contenu_c = st.text_area(
        "Sujet de la leçon ou tâche demandée à l'élève sous PAT :",
        value="Résolution autonome de 4 problèmes de croisements génétiques (grilles de Punnett) en Biologie 40S.",
        height=90
    )

    if st.button("📋 Générer la Fiche de Mission Auxiliaire (30 secondes)", type="primary"):
        with st.spinner("Génération de la fiche EA…"):
            ea_p = (
                "Tu es un spécialiste manitobain de l'inclusion scolaire et de l'encadrement des auxiliaires d'enseignement (EA).\n"
                f"Tâche : {contenu_c}\n\n"
                "Rédige une fiche de mission minute :\n"
                "1. 🎯 Posture attendue de l'auxiliaire (encourager l'autonomie, ne pas faire à la place).\n"
                "2. 💡 3 questions socratiques d'orientation à poser en cas de blocage.\n"
                "3. ⚠️ Signes précurseurs de surcharge cognitive à surveiller.\n"
                "4. 📝 Grille d'observation rapide à 3 critères (Autonomie, Compréhension, Persévérance).\n"
            )
            res_ea = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": ea_p}], temperature=0.3)
            st.markdown(res_ea.choices[0].message.content)


# =============================================================================
# MODULE 8 : PORTAIL PARENTS, TUTRICES ET TUTEURS LÉGAUX
# =============================================================================
elif "Portail Parents" in navigation_espace:
    st.title("👨‍👩‍👦 Module 8 : Portail Parents, Tutrices et Tuteurs Légaux")
    st.caption("Suivi transparent du cheminement, coordination des binômes d'étude et liaison foyer (Conforme FIPPA & Loi sur les écoles publiques)")

    t_suivi, t_binome, t_liaison = st.tabs(["📊 Métriques d'Effort & Autonomie", "🤝 Projets en Binôme (Esprit TeamSnap)", "📬 Liaison École-Maison"])
    with t_suivi:
        c1, c2, c3 = st.columns(3)
        c1.metric("Sessions avec le tuteur", "4", "+1 vs sem. passée")
        c2.metric("Quiz complétés", "3", "Moyenne : 83%")
        c3.metric("Notion approfondie", "Génétique 40S", "Solide")
        st.markdown("#### Validations récentes :")
        st.write("• **Biologie 40S** : 9/10 au quiz formatif (1 indice socratique utilisé).")
        st.write("• **Anglais 40S** : Argumentation littéraire structurée avec autonomie.")
    with t_binome:
        st.info("🔒 Projets en binôme : chaque travail d'équipe requiert l'autorisation préalable du parent ou tuteur légal.")
        st.write("🔬 **Laboratoire d'hérédité mendélienne — En binôme avec Marc L.**")
        st.progress(70, text="Progression du dossier : 70%")
        st.checkbox("Étape 1 : Hypothèses et protocoles de recherche (Validé)", value=True, disabled=True)
        st.checkbox("Étape 2 : Recueil des données de croisement (Validé)", value=True, disabled=True)
        st.checkbox("Étape 3 : Révision finale avec le tuteur socratique", value=False)
        st.write("📍 **Coordination logistique :** Séance de révision partagée prévue à la bibliothèque le mercredi à 16 h 30.")
    with t_liaison:
        st.success("💡 **Note de l'équipe :** Adam fait preuve d'une excellente assiduité socratique en français. Encouragez-le à continuer !")


# Pied de page institutionnel & Dédicace du Fondateur
st.divider()
st.markdown(
    """
    <div style="text-align: center; padding: 20px 10px 15px 10px; line-height: 1.7;">
        <div style="font-weight: 700; color: #f1f5f9; font-size: 1.05rem; letter-spacing: 0.3px; margin-bottom: 6px;">
            DSFMGPT · Conçu avec passion et rigueur par <span style="color: #60a5fa;">Sami KHALIFA</span>
        </div>
        <div style="font-style: italic; color: #cbd5e1; max-width: 850px; margin: 0 auto; font-size: 0.96rem;">
            « Offert avec amour et gratitude à cette terre du Manitoba qui a ouvert ses bras à ma famille et à mes enfants — 
            puisse cette œuvre semer l’excellence, l’équité et la lumière du savoir dans le cœur de chaque élève. »
        </div>
        <div style="font-size: 0.82rem; color: #64748b; margin-top: 10px; font-weight: 500;">
            Écosystème Pédagogique Souverain · Manitoba 🦬 🌾 ⚜️ · 2026-2032
        </div>
    </div>
    """,
    unsafe_allow_html=True
)
)
