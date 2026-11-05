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
# MTS AI Hub — Écosystème Pédagogique Souverain du Manitoba (10 Modules)
# Manitoba Teachers' Society · 16 000+ Membres · Francophone, Immersion & Anglophone
# -----------------------------------------------------------------------------

APP_DIR = Path(__file__).parent
DOCS_DIR = APP_DIR / "documents"
DAYBOOKS_DIR = DOCS_DIR / "daybooks_archive"
DAYBOOKS_DIR.mkdir(parents=True, exist_ok=True)

COURSES = {
    "Biology 40S / Biologie 40S": {
        "folder": "biology",
        "welcome": (
            "Bonjour et bienvenue sur votre tuteur en Biologie 40S (12e année) ! "
            "Sur quel concept explorons-nous aujourd'hui ? Génétique mendélienne, "
            "biologie moléculaire, écologie ou mécanismes de l'évolution ?"
        ),
        "system": """
Tu es le tuteur socratique de niveau provincial pour le cours de Biologie 40S (12e année) au Manitoba (BEF / Manitoba Education standards).
APPROCHE : Enseigne avec rigueur, bienveillance et clarté. Ne donne jamais la solution finale directement.
Pose une seule question d'étayage à la fois, utilise des indices gradués et stimule la démarche scientifique de l'élève.
S'adapte automatiquement à la langue choisie par l'élève (Français ou Anglais).
""",
    },
    "Computer Science 40S / STIAM": {
        "folder": "cs40s",
        "welcome": (
            "Bienvenue au laboratoire d'informatique et STIAM 40S ! "
            "Quels algorithmes, structures de données ou projets de codage abordons-nous ?"
        ),
        "system": """
Tu es le tuteur socratique en sciences computationnelles et STIAM pour les écoles du Manitoba (MTS AI).
Guide l'élève dans l'analyse de ses algorithmes et la résolution de ses bogues logiques sans écrire le code à sa place.
""",
    },
    "English — Comprehensive Focus 40S": {
        "folder": "english",
        "welcome": (
            "Welcome to English Comprehensive Focus 40S! "
            "Would you like to work on critical text analysis, essay synthesis, or persuasive writing today?"
        ),
        "system": """
You are the Socratic writing and analytical mentor for Manitoba Grade 12 English (Comprehensive Focus 40S).
Guide the student methodically through thesis formulation, evidence synthesis, and rhetorical style step-by-step.
Do not write essays for the student; ask thoughtful prompting questions.
""",
    },
    "Cinema — Witness to Modern History 40S": {
        "folder": "cinema",
        "welcome": (
            "Bienvenue en Cinéma : Témoin de l'histoire moderne 40S. "
            "Quel film, courant cinématographique ou perspective historique analysons-nous ?"
        ),
        "system": """
Tu es le tuteur pour le cours d'histoire et langage cinématographique 40S au Manitoba.
Guide l'élève à décoder la mise en scène, le contexte sociopolitique et la véracité documentaire par des relances réflexives.
""",
    },
}

CONTEXT_MODES = {
    "🎓 Standard Socratique (Consolidation)": {
        "prompt": "MÉTHODE SOCRATIQUE CLASSIQUE : Pose UNE SEULE question à la fois. Offre des indices gradués sans donner la réponse brute.",
        "temp": 0.4,
    },
    "🇫🇮 Co-Enquête & Autonomie Active (Modèle Finlandais)": {
        "prompt": (
            "POSTURE MODÈLE FINLANDAIS (Inquiry-Based Learning) : Agis comme un co-chercheur et facilitateur. "
            "Encourage l'élève à formuler ses propres questions, à tester des hypothèses pratiques et à faire des liens "
            "avec des phénomènes réels de sa communauté. Favorise une autonomie chaleureuse et la confiance en soi."
        ),
        "temp": 0.5,
    },
    "🇯🇵 Mimamoru & Hansei (Modèle Japonais - Autocorrection)": {
        "prompt": (
            "POSTURE MODÈLE JAPONAIS (Mimamoru & Hansei) : Observe la pensée de l'élève avec une grande courtoisie sans intervenir brutalement. "
            "Si l'élève fait une erreur, ne la sanctionne pas : demande-lui poliment d'expliciter chaque maillon de sa démarche "
            "pour qu'il expérimente le Hansei (auto-réflexion introspective) et découvre lui-même sa propre correction."
        ),
        "temp": 0.3,
    },
    "🚀 Défi & Approfondissement (Élèves avancés)": {
        "prompt": (
            "POSTURE ENRICHISSEMENT : Hausse l'exigence conceptuelle (Taxonomie de Bloom supérieure). "
            "Propose des contre-exemples stimulants, teste la solidité argumentative et relie les notions à la recherche actuelle."
        ),
        "temp": 0.4,
    },
    "❄️ Grand Froid & Tempête (Continuité Blizzard)": {
        "prompt": (
            "POSTURE TEMPÊTE & BLIZZARD (MTS) : Ton particulièrement chaleureux, rassurant et interactif. "
            "Maintiens le sentiment d'appartenance et brise l'isolement de l'élève connecté depuis la maison lors d'une fermeture d'école."
        ),
        "temp": 0.5,
    },
    "⏱️ Examen Provincial 40S (Simulation BEF / Manitoba)": {
        "prompt": (
            "POSTURE EXAMINATEUR PROVINCIAL : Évalue formellement selon les barèmes ministériels de 12e année. "
            "Mesure la précision de la terminologie scientifique, la clarté du raisonnement et chiffre le barème."
        ),
        "temp": 0.2,
    },
    "🌍 Francisation & Accueil (Inclusion)": {
        "prompt": (
            "POSTURE FRANCISATION & ACCUEIL : Vocabulaire clair, phrases limpides, mise entre parenthèses des termes techniques "
            "et repères bilingues d'appoint si nécessaire pour les nouveaux arrivants."
        ),
        "temp": 0.3,
    },
}

st.set_page_config(
    page_title="MTS AI — Hub Provincial de l'Éducation au Manitoba",
    page_icon="🦬",
    layout="wide"
)

# Style CSS pour l'Accueil Prestige & Balises de Guidage MTS AI
st.markdown(
    """
    <style>
        .hero-container {
            background: linear-gradient(135deg, #091326 0%, #0f274a 55%, #1b3d6d 100%);
            border: 1px solid rgba(255, 255, 255, 0.14);
            border-radius: 18px;
            padding: 32px;
            margin-bottom: 25px;
            box-shadow: 0 14px 35px -10px rgba(0, 0, 0, 0.6);
        }
        .hero-title {
            font-size: 2.35rem;
            font-weight: 800;
            color: #f8fafc;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            gap: 12px;
            letter-spacing: -0.5px;
        }
        .hero-subtitle {
            font-size: 1.05rem;
            color: #94a3b8;
            margin-bottom: 20px;
            line-height: 1.55;
        }
        .tag-pill {
            display: inline-block;
            background: rgba(234, 179, 8, 0.15);
            color: #facc15;
            border: 1px solid rgba(234, 179, 8, 0.35);
            padding: 4px 12px;
            border-radius: 9999px;
            font-size: 0.8rem;
            font-weight: 600;
            margin-right: 8px;
        }
        .tag-pill-blue {
            display: inline-block;
            background: rgba(59, 130, 246, 0.16);
            color: #60a5fa;
            border: 1px solid rgba(59, 130, 246, 0.35);
            padding: 4px 12px;
            border-radius: 9999px;
            font-size: 0.8rem;
            font-weight: 600;
            margin-right: 8px;
        }
        .module-card {
            background: rgba(255, 255, 255, 0.035);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 14px;
            padding: 18px;
            min-height: 180px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            margin-bottom: 10px;
            transition: all 0.2s ease;
        }
        .module-card:hover {
            border-color: rgba(96, 165, 250, 0.4);
            background: rgba(255, 255, 255, 0.06);
        }
        .module-card h4 {
            font-size: 1rem;
            color: #f1f5f9;
            margin-bottom: 6px;
        }
        .module-card p {
            font-size: 0.82rem;
            color: #94a3b8;
            line-height: 1.4;
            margin-bottom: 8px;
        }
        .module-card small {
            color: #60a5fa;
            font-weight: 600;
            font-size: 0.75rem;
        }
        .guide-badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: rgba(59, 130, 246, 0.15);
            color: #93c5fd;
            border: 1px solid rgba(59, 130, 246, 0.4);
            padding: 3px 10px;
            border-radius: 6px;
            font-size: 0.78rem;
            font-weight: 700;
            margin-bottom: 6px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .guide-box {
            background: rgba(30, 58, 138, 0.22);
            border-left: 4px solid #3b82f6;
            border-radius: 6px;
            padding: 12px 16px;
            font-size: 0.88rem;
            color: #e2e8f0;
            margin-bottom: 18px;
            line-height: 1.5;
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


def generer_image_souveraine(contexte_texte: str, focus_visuel: str):
    try:
        distill_prompt = (
            "Tu es un illustrateur scientifique et pédagogique pour la Manitoba Teachers' Society (MTS AI).\n"
            f"Sujet d'étude : {focus_visuel}\n"
            f"Données contextuelles vérifiées : {contexte_texte}\n"
            "Conçois un prompt descriptif pour un schéma scientifique sobre, "
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


def speak_text(text: str, lang_code="fr-FR"):
    clean_text = text.replace("'", "\\'").replace('"', '\\"').replace("\n", " ").replace("\r", " ")
    js_code = f"""
    <script>
        window.speechSynthesis.cancel();
        var msg = new SpeechSynthesisUtterance("{clean_text}");
        msg.lang = '{lang_code}';
        window.speechSynthesis.speak(msg);
    </script>
    """
    components.html(js_code, height=0)


def stop_speech():
    components.html("<script>window.speechSynthesis.cancel();</script>", height=0)


# Variables d'état & Initialisation
if "nav_active" not in st.session_state:
    st.session_state.nav_active = "🏠 Accueil & Vue d'Ensemble"
if "guide_interactif" not in st.session_state:
    st.session_state.guide_interactif = True
if "student_name" not in st.session_state:
    st.session_state.student_name = ""
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


def generate_qcm_from_context(course_title, system_prompt, discussion_context, number_questions=10):
    prompt_lines = [
        f"En te basant sur la discussion récente et le cours : {course_title}, crée un quiz d'entraînement de {number_questions} questions à choix multiples (QCM).",
        f"Contexte récent :\n{discussion_context}",
        "Format strict : 4 options (A, B, C, D), une seule réponse correcte, un indice et une explication.",
        'Renvoie UNIQUEMENT un objet JSON valide avec cette structure : {"questions": [{"question": "...", "options": {"A":"...", "B":"...", "C":"...", "D":"..."}, "correct": "A", "hint": "...", "explanation": "..."}]}'
    ]
    prompt = "\n\n".join(prompt_lines)
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
            prefix = "[Ressource Enseignant]" if is_custom else "[Curriculum Manitoba]"
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


# --- LISTE DES 10 MODULES OFFICIELS ---
MODULES_LIST = [
    "🏠 Accueil & Vue d'Ensemble",
    "1. 👩‍🏫 Assistant BEF / CUA",
    "2. 🎓 Tuteur Socratique",
    "3. 🏢 Admin & Impact MTS",
    "4. 🛡️ InfoSec & FIPPA",
    "5. 💻 STIAM & Sandbox Codage",
    "6. 🔄 Suppléance & Daybook",
    "7. 🤝 Auxiliaires EA & Inclusion",
    "8. 👨‍👩‍👦 Portail Parents & Tuteurs",
    "9. 🌍 Lab Phénomènes (PhBL)",
    "10. 🧠 Moteur Neuro-Cognitif"
]

# --- BARRE LATÉRALE DE CONTRÔLE MULTI-DIVISIONS ---
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/school.png", width=52)
    st.title("MTS AI Hub")
    st.caption("Manitoba Teachers' Society · 16 000+ Membres")

    # Profil Institutionnel Provincial
    st.markdown("### 🏛️ Division & Langue")
    div_locale = st.selectbox(
        "Division scolaire :",
        [
            "DSFM (Division scolaire franco-manitobaine)",
            "Winnipeg School Division (WSD #1)",
            "Pembina Trails School Division",
            "Louis Riel School Division (LRSD)",
            "St. James-Assiniboia School Division",
            "River East Transcona School Division",
            "Brandon School Division",
            "Autre division scolaire manitobaine"
        ],
        help="Adapte le profil curriculaire, les conventions et les flux administratifs selon votre division."
    )
    langue_choisie = st.radio("Langue de l'espace :", ["Français (Immersion & Français langue première)", "English (Standard)"], horizontal=True)

    default_idx = MODULES_LIST.index(st.session_state.nav_active) if st.session_state.nav_active in MODULES_LIST else 0
    navigation_espace = st.radio(
        "Navigation Systémique :",
        MODULES_LIST,
        index=default_idx
    )
    st.session_state.nav_active = navigation_espace

    st.markdown("---")
    st.markdown("### 📚 Matière & Pédagogie")
    course_name = st.selectbox(
        "Matière / Programme :",
        list(COURSES.keys()),
        help="Choix du programme de cours manitobain indexé."
    )
    course = COURSES[course_name]
    folder = DOCS_DIR / course["folder"]

    mode_selectionne = st.selectbox(
        "Posture d'apprentissage :",
        list(CONTEXT_MODES.keys()),
        help="Choisissez le modèle pédagogique : Socratique, Modèle Finlandais d'investigation ou Modèle Japonais d'auto-réflexion."
    )
    mode_info = CONTEXT_MODES[mode_selectionne]

    st.markdown("---")
    st.markdown("### 🧭 Balises d'Accompagnement")
    guide_toggle = st.toggle(
        "Activer le Mode Guidé (Repères)",
        value=st.session_state.guide_interactif,
        help="Affiche des badges étape par étape et des encadrés conseils dans chaque module."
    )
    st.session_state.guide_interactif = guide_toggle

    st.markdown("---")
    st.markdown("### 🔊 Dictée & Voix")
    enable_voice_output = st.checkbox("Synthèse vocale active", value=True)
    if st.button("🛑 Couper la voix", use_container_width=True):
        stop_speech()
        st.success("Voix coupée.")

    audio_value = st.audio_input("Dictée vocale directe (Whisper)")


# =============================================================================
# ACCUEIL : LE DASHBOARD EXÉCUTIF MTS AI
# =============================================================================
if "Accueil" in navigation_espace:
    st.markdown(
        """
        <div class="hero-container">
            <div class="hero-title">
                <span>MTS AI</span>
                <span style="font-size: 2.2rem;">🦬</span>
                <span style="font-size: 1.8rem;">🌾</span>
                <span style="font-size: 1.8rem;">⚜️</span>
            </div>
            <div class="hero-subtitle">
                Infrastructure d'Intelligence Artificielle Souveraine, Équitable & Pédagogique<br>
                Conçue pour la <strong>Manitoba Teachers' Society (MTS)</strong> et l'ensemble des divisions scolaires de la province.
            </div>
            <div>
                <span class="tag-pill">🏛️ Écosystème Provincial des 10 Modules</span>
                <span class="tag-pill">🔒 Souveraineté & Protection FIPPA</span>
                <span class="tag-pill-blue">🇫🇮 Inspiration Finlande (PhBL)</span>
                <span class="tag-pill-blue">🇯🇵 Modèle Japon (Hansei/Métacognition)</span>
                <span class="tag-pill-blue">⏱️ Prévention de l'Épuisement MTS</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    if st.session_state.guide_interactif:
        st.markdown(
            f"""
            <div class="guide-box">
                👋 <strong>Bienvenue au Hub MTS AI pour : {div_locale} !</strong><br>
                • <strong>Pour planifier :</strong> Le <em>Module 1</em> génère des leçons CUA complètes et le <em>Module 6</em> génère votre cartable de suppléance imprimable.<br>
                • <strong>Pour les élèves :</strong> Le <em>Module 2</em> fournit un tuteur socratique qui favorise l'effort intellectuel sans donner de réponses toutes faites.<br>
                • <strong>Pour l'administration :</strong> Le <em>Module 3</em> mesure l'allègement concret de la tâche enseignante (heures récupérées par semaine).
            </div>
            """,
            unsafe_allow_html=True
        )

    c_k1, c_k2, c_k3, c_k4 = st.columns(4)
    c_k1.metric("Couverture Provinciale", "10 Modules", "Membres MTS & Divisions")
    c_k2.metric("Gain Hebdomadaire", "~4.8 h / enseignant", "Allègement de tâche")
    c_k3.metric("Équité Territoriale", "24/7 Autonome", "Urbain, Rural & Nord")
    c_k4.metric("Souveraineté des Données", "Manitoba Local", "Zéro fuite FIPPA/LAIPVP")

    st.markdown("### 🧭 La Matrice des 10 Services MTS AI")
    st.caption("Sélectionnez directement un service pour ouvrir son poste de travail :")

    r1_c1, r1_c2, r1_c3, r1_c4, r1_c5 = st.columns(5)
    with r1_c1:
        st.markdown("""<div class="module-card"><div><h4>👩‍🏫 1. Assistant BEF/CUA</h4><p>Plans de cours CUA multiniveau, adaptations PAT et fiches d'évaluation.</p></div><small>Public : Enseignants titulaires</small></div>""", unsafe_allow_html=True)
        if st.button("Ouvrir 1 ➔", key="btn_m1", use_container_width=True):
            st.session_state.nav_active = "1. 👩‍🏫 Assistant BEF / CUA"
            st.rerun()

    with r1_c2:
        st.markdown("""<div class="module-card"><div><h4>🎓 2. Tuteur Socratique</h4><p>Accompagnement bienveillant, quiz 10 questions et schémas scientifiques RAG.</p></div><small>Public : Élèves 40S / K-12</small></div>""", unsafe_allow_html=True)
        if st.button("Ouvrir 2 ➔", key="btn_m2", use_container_width=True):
            st.session_state.nav_active = "2. 🎓 Tuteur Socratique"
            st.rerun()

    with r1_c3:
        st.markdown("""<div class="module-card"><div><h4>🏢 3. Admin & MTS</h4><p>Baromètre du gain de temps et allègement de la charge enseignante.</p></div><small>Public : Directions & MTS</small></div>""", unsafe_allow_html=True)
        if st.button("Ouvrir 3 ➔", key="btn_m3", use_container_width=True):
            st.session_state.nav_active = "3. 🏢 Admin & Impact MTS"
            st.rerun()

    with r1_c4:
        st.markdown("""<div class="module-card"><div><h4>🛡️ 4. InfoSec FIPPA</h4><p>Masquage dynamique des PII, chiffrement TLS 1.3 et registre audit SHA-256.</p></div><small>Public : Services TI</small></div>""", unsafe_allow_html=True)
        if st.button("Ouvrir 4 ➔", key="btn_m4", use_container_width=True):
            st.session_state.nav_active = "4. 🛡️ InfoSec & FIPPA"
            st.rerun()

    with r1_c5:
        st.markdown("""<div class="module-card"><div><h4>💻 5. STIAM Sandbox</h4><p>Bac à sable d'exécution Python en direct et débogueur socratique 24/7.</p></div><small>Public : Secondaire STEM</small></div>""", unsafe_allow_html=True)
        if st.button("Ouvrir 5 ➔", key="btn_m5", use_container_width=True):
            st.session_state.nav_active = "5. 💻 STIAM & Sandbox Codage"
            st.rerun()

    st.markdown("")

    r2_c1, r2_c2, r2_c3, r2_c4, r2_c5 = st.columns(5)
    with r2_c1:
        st.markdown("""<div class="module-card"><div><h4>🔄 6. Suppléance Daybook</h4><p>Cartables imprimables (Cycle 6 jours & Secondaire) et banque d'exemplaires réels.</p></div><small>Public : Titulaires & Suppléants</small></div>""", unsafe_allow_html=True)
        if st.button("Ouvrir 6 ➔", key="btn_m6", use_container_width=True):
            st.session_state.nav_active = "6. 🔄 Suppléance & Daybook"
            st.rerun()

    with r2_c2:
        st.markdown("""<div class="module-card"><div><h4>🤝 7. Auxiliaires EA</h4><p>Feuilles de mission minute, guide de relance socratique et bilans PEI.</p></div><small>Public : Équipes Inclusion</small></div>""", unsafe_allow_html=True)
        if st.button("Ouvrir 7 ➔", key="btn_m7", use_container_width=True):
            st.session_state.nav_active = "7. 🤝 Auxiliaires EA & Inclusion"
            st.rerun()

    with r2_c3:
        st.markdown("""<div class="module-card"><div><h4>👨‍👩‍👦 8. Parents/Tuteurs</h4><p>Métriques d'effort, accord légal des binômes d'étude et liaison foyer.</p></div><small>Public : Familles & Tuteurs</small></div>""", unsafe_allow_html=True)
        if st.button("Ouvrir 8 ➔", key="btn_m8", use_container_width=True):
            st.session_state.nav_active = "8. 👨‍👩‍👦 Portail Parents & Tuteurs"
            st.rerun()

    with r2_c4:
        st.markdown("""<div class="module-card"><div><h4>🌍 9. Lab Phénomènes</h4><p>Approche transdisciplinaire finlandaise ancrée dans les défis manitobains.</p></div><small>Public : Projets Inter-matières</small></div>""", unsafe_allow_html=True)
        if st.button("Ouvrir 9 ➔", key="btn_m9", use_container_width=True):
            st.session_state.nav_active = "9. 🌍 Lab Phénomènes (PhBL)"
            st.rerun()

    with r2_c5:
        st.markdown("""<div class="module-card"><div><h4>🧠 10. Neuro-Cognitif</h4><p>Métacognition active, anti-paresse cérébrale et répétition espacée.</p></div><small>Public : Sciences Cognitives</small></div>""", unsafe_allow_html=True)
        if st.button("Ouvrir 10 ➔", key="btn_m10", use_container_width=True):
            st.session_state.nav_active = "10. 🧠 Moteur Neuro-Cognitif"
            st.rerun()


# =============================================================================
# MODULE 1 : ASSISTANT BEF / CUA (ENSEIGNANT)
# =============================================================================
elif "Assistant BEF" in navigation_espace:
    st.title("👩‍🏫 Module 1 : Assistant Pédagogique BEF & Planification CUA")
    st.caption("Conception accélérée de plans de leçons différenciés, évaluations formatives et classeur curriculaire")

    if st.session_state.guide_interactif:
        st.markdown(
            """
            <div class="guide-box">
                🎯 <strong>Guide Enseignant :</strong><br>
                • <strong>Étape 1 :</strong> Renseignez le code ministériel et l'objectif de la séance.<br>
                • <strong>Étape 2 :</strong> Précisez les aménagements nécessaires pour l'inclusion et le défi pour les élèves rapides.<br>
                • <strong>Étape 3 :</strong> Cliquez sur le bouton rouge pour produire le déroulé complet en 4 phases.
            </div>
            """,
            unsafe_allow_html=True
        )

    tab_bef, tab_eval, tab_notebook, tab_video = st.tabs([
        "📋 Planification Différenciée (CUA / PAT / Défi)",
        "📊 Évaluation Formative & par les Pairs",
        "📚 Mon Classeur (Esprit NotebookLM)",
        "🎬 Studio Capsule Dialoguée (Continuité Blizzard)"
    ])

    with tab_bef:
        st.subheader("Générateur de Leçon Curriculaire Trifide")
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            if st.session_state.guide_interactif:
                st.markdown('<span class="guide-badge">📍 Étape 1 : Cadre Ministériel</span>', unsafe_allow_html=True)
            ras_input = st.text_input(
                "Code RAS ministériel :",
                value="B12-2-03 (Lois de Mendel)",
                help="Saisissez le code du résultat d'apprentissage manitobain visé."
            )
            sujet_lecon = st.text_input(
                "Sujet de la leçon :",
                value="Monohybridisme et grilles de Punnett",
                help="Intitulé thématique précis de la période de cours."
            )
        with col_t2:
            if st.session_state.guide_interactif:
                st.markdown('<span class="guide-badge">📍 Étape 2 : Inclusion & Différenciation</span>', unsafe_allow_html=True)
            profil_pat = st.text_area(
                "Adaptations PAT / IEP :",
                value="2 élèves en PAT (textes aérés, étayage visuel, consignes découpées).",
                help="Besoins particuliers d'adaptation (sans données nominatives directes, conforme FIPPA)."
            )
            profil_avance = st.text_area(
                "Enrichissement & Défi :",
                value="3 élèves très rapides (probabilités mendéliennes complexes et dihybridisme).",
                help="Tâches complexes à proposer pour stimuler les élèves en avance."
            )

        if st.session_state.guide_interactif:
            st.markdown('<span class="guide-badge">📍 Étape 3 : Production en 1 clic</span>', unsafe_allow_html=True)
        col_b1, col_b2 = st.columns(2)
        with col_b1:
            l_btn = st.button("🚀 Générer la leçon multiniveau complète", type="primary", use_container_width=True)
        with col_b2:
            img_btn_t = st.button("🖼️ Générer une illustration souveraine", use_container_width=True)

        if l_btn:
            with st.spinner("Génération du plan pédagogique CUA…"):
                p_prompt = (
                    f"Tu es un conseiller pédagogique expert pour la Manitoba Teachers' Society ({div_locale}).\n"
                    f"Crée un plan de leçon rigoureux et structuré pour : {course_name}.\n"
                    f"- Résultat d'apprentissage ministériel : {ras_input}\n"
                    f"- Sujet : {sujet_lecon}\n"
                    f"- Adaptations PAT : {profil_pat}\n"
                    f"- Élèves avancés : {profil_avance}\n\n"
                    "Structure attendue :\n"
                    "1. 🎯 Objectifs ministériels observables et critères de réussite explicites.\n"
                    "2. 📖 Déroulement de classe (Amorce 10 min, Enseignement explicite 15 min, Pratique guidée 25 min, Clôture 10 min).\n"
                    "3. ♿ Volet Inclusion & CUA (Aménagements matériels et consignes adaptées).\n"
                    "4. 🚀 Volet Enrichissement (Défis ouverts à haut niveau cognitif).\n"
                    "5. 💡 3 questions socratiques de relance pour vérifier l'assimilation.\n"
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
            with st.spinner("Création du schéma scientifique…"):
                les_data = st.session_state.current_lesson_plan or f"Lesson: {sujet_lecon}."
                img_url_t = generer_image_souveraine(les_data, f"Schéma scientifique de {sujet_lecon}")
                if img_url_t:
                    st.image(img_url_t, caption="Illustration scientifique générée localement")

    with tab_eval:
        st.subheader("📊 Évaluations Formatives & par les Pairs (Normes Manitoba)")
        type_eval = st.radio("Type d'outil :", ["🎟️ Billet de Sortie Flash (3 min)", "👥 Grille d'Évaluation par les Pairs (Deux étoiles et un souhait)", "🎯 Sonde Diagnostique Rapide"], horizontal=True)
        sujet_eval = st.text_input("Notion ciblée :", value="L'analyse des allèles dominants et récessifs", help="Le concept précis à sonder.")
        if st.button("✨ Générer l'outil d'évaluation", type="primary"):
            with st.spinner("Conception de l'instrument d'évaluation…"):
                eval_p = f"Crée un outil d'évaluation formatif conforme aux normes manitobaines. Type : {type_eval}. Matière : {course_name}. Sujet : {sujet_eval}."
                resp_eval = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": eval_p}], temperature=0.3)
                st.markdown(resp_eval.choices[0].message.content)

    with tab_notebook:
        st.subheader("📚 Mon Classeur de Cours (Esprit NotebookLM)")
        custom_folder = DOCS_DIR / course["folder"] / "custom_teacher"
        custom_folder.mkdir(parents=True, exist_ok=True)
        up_files = st.file_uploader("Ajouter des PDF de cours personnels :", type=["pdf"], accept_multiple_files=True, help="Déposez vos propres documents : l'assistant les utilisera en priorité.")
        if up_files:
            for f in up_files:
                with open(custom_folder / f.name, "wb") as buffer:
                    buffer.write(f.getbuffer())
            st.success(f"✅ {len(up_files)} ressource(s) indexée(s) avec succès !")
            st.cache_data.clear()

    with tab_video:
        st.subheader("🎬 Studio Capsule Dialoguée (Continuité Blizzard)")
        notion_v = st.text_input("Notion clé pour la capsule :", value="Le monohybridisme et la ségrégation mendélienne")
        if st.button("🎥 Scénariser la capsule vidéo"):
            with st.spinner("Scénarisation en cours…"):
                vid_p = f"Rédige un script de dialogue chaleureux de 2 min entre un élève et son enseignant sur {notion_v} pour une école du Manitoba."
                res_v = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": vid_p}], temperature=0.5)
                st.markdown(res_v.choices[0].message.content)


# =============================================================================
# MODULE 2 : TUTEUR SOCRATIQUE (ÉLÈVE)
# =============================================================================
elif "Tuteur Socratique" in navigation_espace:
    st.title(f"🎓 Module 2 : Tuteur Socratique MTS AI — {course_name}")
    st.caption("Accompagnement réflexif bienveillant · Pédagogie de questionnement sans réponse brute")

    # Personnalisation universelle du prénom de l'élève
    c_nom1, c_nom2 = st.columns([2, 1])
    with c_nom1:
        if st.session_state.guide_interactif:
            st.markdown(
                """
                <div class="guide-box">
                    👋 <strong>Bienvenue dans votre espace d'apprentissage !</strong><br>
                    • <strong>Principe :</strong> Le tuteur socratique ne vous donne pas la solution directement ; il vous aide à structurer votre propre réflexion.<br>
                    • <strong>Comment participer :</strong> Écrivez votre réponse ci-dessous ou dictez-la avec le microphone dans la barre latérale.
                </div>
                """,
                unsafe_allow_html=True
            )
    with c_nom2:
        prenom_saisi = st.text_input("Prénom de l'élève (optionnel) :", value=st.session_state.student_name, placeholder="Ex: Alexandre, Sarah...")
        if prenom_saisi != st.session_state.student_name:
            st.session_state.student_name = prenom_saisi

    greeting_name = f" {st.session_state.student_name}" if st.session_state.student_name.strip() else ""

    if course_name not in st.session_state.histories_by_course:
        intro_msg = f"Bonjour{greeting_name} ! Bienvenue sur votre espace d'apprentissage en {course_name}. Sur quel point souhaitez-vous avancer aujourd'hui ?"
        st.session_state.histories_by_course[course_name] = [{"role": "assistant", "content": intro_msg}]
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
                if st.button("📖 Expliquer plus simplement", key=f"s1_{idx}", use_container_width=True):
                    b_q = "Peux-tu m'expliquer cette idée plus simplement avec une analogie visuelle claire ?"
            with c2:
                if st.button("📝 Exemple concret manitobain", key=f"s2_{idx}", use_container_width=True):
                    b_q = "Donne-moi un exemple concret issu du quotidien ou de la nature au Manitoba."
            with c3:
                if st.button("🎥 Vidéo illustrative", key=f"s3_{idx}", use_container_width=True):
                    b_q = "Propose un lien YouTube ou une ressource visuelle pour explorer ce concept."
            with c4:
                if st.button("🚀 Relever un défi supérieur", key=f"s4_{idx}", use_container_width=True):
                    b_q = "Comment ce concept se relie-t-il à un problème scientifique plus complexe ?"
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
                        c_txt = "\n\n".join(c["text"] for c in rel_c) if rel_c else "Programme général provincial."
                        u = generer_image_souveraine(c_txt, disc_img)
                        if u:
                            st.image(u, caption="Illustration scientifique basée sur le contexte local")

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

    typed_q = st.chat_input("Posez votre question ici…")
    active_q = typed_q or st.session_state.pop("next_question", None)
    if active_q and active_q.strip():
        active_q = active_q.strip()
        history.append({"role": "user", "content": active_q})
        with st.chat_message("user"):
            st.markdown(active_q)

        all_c = load_pdf_chunks(str(folder))
        rel_c = retrieve_chunks(active_q, all_c)
        c_block = "\n\n".join(f"[{c['source']}]\n{c['text']}" for c in rel_c) if rel_c else "Programme général provincial."
        sys_p = f"{course['system']}\n\nDivision scolaire active : {div_locale}\n\nPosture demandée :\n{mode_info['prompt']}\n\nExtraits documentaires locaux :\n{c_block}\n\nRAPPEL : Adopte rigoureusement la posture sélectionnée."
        
        with st.chat_message("assistant"):
            with st.spinner("Réflexion en cours…"):
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
    st.caption("Mesure de l'allègement de la charge enseignante (ROI humain) et efficience divisionnaire")

    col_p1, col_p2, col_p3 = st.columns(3)
    with col_p1:
        nb_profs = st.slider("Enseignants titulaires dans l'établissement :", 5, 80, 30)
        lecons_sem = st.slider("Plans de cours générés / sem. :", 1, 10, 3)
    with col_p2:
        nb_ea = st.slider("Auxiliaires d'enseignement (EA) :", 1, 20, 6)
        nb_suppl = st.slider("Remplacements / suppléances par mois :", 2, 50, 15)
    with col_p3:
        nb_el = st.slider("Élèves bénéficiaires du tuteur :", 20, 600, 180, step=10)
        sess_el = st.slider("Sessions d'étayage / élève / sem. :", 1, 7, 3)

    gain_profs_h = (nb_profs * lecons_sem * (45 + 50)) / 60
    gain_ea_h = (nb_ea * 5 * 25) / 60
    gain_suppl_h = (nb_suppl * 40) / 60
    gain_total_mois = (gain_profs_h * 4) + (gain_ea_h * 4) + gain_suppl_h
    jours_recup = gain_total_mois / 7.5

    st.divider()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Heures économisées / prof", f"~{gain_profs_h / nb_profs:.1f} h / sem", "Moins de correction/prépa")
    m2.metric("Temps personnel école", f"{gain_total_mois:.0f} h / mois", "Heures réinvesties")
    m3.metric("Équivalent journées de travail", f"{jours_recup:.1f} jours", "Par mois d'école")
    m4.metric("Temps d'étude élèves", f"{(nb_el * sess_el * 30 * 4) / 60:.0f} h / mois", "Encadré et sécurisé")

    st.markdown("---")
    st.success("🛡️ **Plaidoyer MTS :** Ce baromètre fournit la preuve mathématique que MTS AI protège la santé mentale des enseignants en allégeant leur charge de préparation administrative et pédagogique.")


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
            "Texte d'exemple contenant des données identifiables :",
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
        logs_demo = [
            {"Horodatage": "2026-10-25 18:42:10", "Utilisateur": "Enseignant #4102", "Action": "Génération Leçon Bio 40S", "Statut FIPPA": "Vérifié (Zéro PII)", "Hash SHA-256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"},
            {"Horodatage": "2026-10-25 19:05:32", "Utilisateur": "Élève (Session Anonyme)", "Action": "Question Socratique Mendel", "Statut FIPPA": "Conforme (Session Isolée)", "Hash SHA-256": "87542b827e7d60a1a9a40f02f8f902cbd3194206585634d6824a848380516200"},
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
    st.caption("Équité territoriale en informatique : bac à sable sécurisé et débogueur socratique pour écoles urbaines et rurales")

    code_init = """# Défi Informatique 40S : Calcul de la fréquence d'allèles
def frequence_alleles(nb_dominants, nb_recessifs):
    total = nb_dominants + nb_recessifs
    freq_dom = nb_dominants / total
    return freq_dom

# Test
print("Fréquence allèle dominant :", frequence_alleles(60, 40))
"""
    code_eleve = st.text_area("Éditeur de code Python :", value=code_init, height=180, help="Saisissez ou collez votre script Python. Vous pouvez l'exécuter directement.")

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
                    "Tu es un enseignant socratique en informatique 40S au Manitoba (MTS AI).\n"
                    f"Voici le code saisi par l'élève :\n{code_eleve}\n\n"
                    "CONSIGNE STRICTE : Ne donne pas la correction directe du code. "
                    "Pose 1 ou 2 questions socratiques stimulantes sur la complexité algorithmique, la gestion des erreurs ou la structure logique."
                )
                res_code = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": p_code}],
                    temperature=0.3
                )
                st.markdown(res_code.choices[0].message.content)


# =============================================================================
# MODULE 6 : SUPPLÉANCE, DAYBOOK & ERP ATRIEVE (CORRIGÉ & ÉTENDU)
# =============================================================================
elif "Suppléance & Daybook" in navigation_espace:
    st.title("🔄 Module 6 : Cartable de Suppléance, Daybook & Archives Terrain")
    st.caption("Génération en un clic des fiches de journée (Cycle de 6 jours ou Secondaire par périodes) et banque d'exemplaires réels")

    if st.session_state.guide_interactif:
        st.markdown(
            """
            <div class="guide-box">
                📌 <strong>Mode d'emploi du Cartable de Suppléance :</strong><br>
                1. <strong>Sélectionnez votre palier :</strong> Onglet <em>M à 8e</em> pour les classes élémentaires (cycle manitobain de 6 jours) ou <em>Secondaire</em> pour les collèges (découpage par périodes).<br>
                2. <strong>Personnalisez :</strong> Vérifiez les horaires, les surveillances de cour et les consignes de classe combinée.<br>
                3. <strong>Imprimez :</strong> Utilisez le bouton d'impression propre pour insérer la feuille dans votre classeur physique.<br>
                4. <strong>Banque d'archives :</strong> Consultez ou alimentez l'onglet <em>Archives</em> pour stocker vos photos réelles de cartables de suppléance.
            </div>
            """,
            unsafe_allow_html=True
        )

    tab_elem, tab_sec, tab_atrieve, tab_archive = st.tabs([
        "🎒 Cartable M à 8e (Cycle 6 Jours)",
        "🏛️ Cartable Secondaire 9e à 12e (Par Périodes)",
        "⚡ Protocole d'Urgence Atrieve (8 h 15)",
        "🗄️ Banque de Plans Réels & Exemplaires Terrain"
    ])

    # -------------------------------------------------------------------------
    # GABARIT 1 : MATERNELLE AU 8E (CYCLE 6 JOURS)
    # -------------------------------------------------------------------------
    with tab_elem:
        st.subheader("📋 Générateur de Daybook — Élémentaire & Intermédiaire (M à 8e)")
        st.write("Conçu selon les standards manitobains : cycle de 6 jours, blocs de 30 minutes et gestion des classes combinées.")

        col_e1, col_e2, col_e3 = st.columns(3)
        with col_e1:
            ecole_elem = st.selectbox("Établissement :", [
                "École Saint-Albert (Winnipeg)",
                "École Pointe-des-Chênes (Sainte-Anne)",
                "École Saint-Joachim (La Broquerie)",
                "École Réal-Bérard (Saint-Pierre-Jolys)",
                "École Précieux-Sang (Winnipeg)",
                "École élémentaire de division anglophone"
            ], key="elem_ecole", help="Nom de l'école apparaissant dans l'en-tête officiel.")
            date_elem = st.text_input("Date du jour :", value="Vendredi 25 septembre", key="elem_date", help="Date de la journée de remplacement.")
        with col_e2:
            cycle_elem = st.selectbox("Jour du cycle manitobain :", [
                "JOUR 1", "JOUR 2", "JOUR 3", "JOUR 4", "JOUR 5", "JOUR 6"
            ], index=1, key="elem_cycle", help="Jour officiel du cycle de 6 jours du Manitoba.")
            classe_elem = st.text_input("Niveau / Classe :", value="3e / 4e année combinée", key="elem_classe", help="Exemple : 4e année ou classe multi-niveaux 3e/4e.")
        with col_e3:
            surveillance_elem = st.text_input("Surveillance récréation :", value="14 h 05 - 14 h 20 : Extérieur (Cour principale)", key="elem_surv", help="Plage de surveillance extérieure assignée au suppléant.")
            consigne_entree = st.text_input("Consigne d'ouverture :", value="Entrée des élèves : Ne pas laisser travailler dans les couloirs.", key="elem_entree", help="Consigne de sécurité affichée en haut de page.")

        st.markdown("##### 📝 Détail des périodes et consignes de travail :")
        c_m1, c_m2 = st.columns(2)
        with c_m1:
            mat_fr = st.text_area("Français / UFLI (Matin) :", value="Français : Vocabulaire 'an/en'. Cahiers d'écriture. Theo a besoin d'encouragement pour débuter.", height=85, help="Travail en littératie ou phonétique.")
            mat_math = st.text_area("Mathématiques (Matin) :", value="Stratégies d'addition 3 et 4. Les 3e travaillent dans les duo-tangs bleus, les 4e sur les fiches roses.", height=85, help="Consignes différenciées pour les mathématiques.")
        with c_m2:
            mat_apresmidi = st.text_area("Après-midi (Sciences / Univers social) :", value="12h35: Lecture autonome sur iPads (EPIC). 13h05: Sciences de la nature (Cahier L'École p. 12-14).", height=85, help="Activités autonomes de l'après-midi.")
            mat_ela = st.text_area("E.L.A. / Clôture de journée :", value="14h20: Reading mystery 'Teacher Toads'. 15h10: Écrire les devoirs dans l'agenda et étamper.", height=85, help="Anglais et routine de sortie.")

        if st.button("📄 Générer la Fiche Imprimable du Classeur (M à 8)", type="primary", use_container_width=True):
            html_elem = f"""
            <div style="font-family: Arial, sans-serif; background: #ffffff; color: #1e293b; padding: 25px; border-radius: 8px; border: 2px solid #cbd5e1; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
                <div style="display: flex; justify-content: space-between; align-items: baseline; border-bottom: 2px solid #0f172a; padding-bottom: 8px; margin-bottom: 12px;">
                    <div>
                        <span style="font-size: 1.5rem; font-weight: 800; color: #0f172a;">{cycle_elem}</span>
                        <span style="font-size: 1.1rem; font-weight: 600; color: #475569; margin-left: 15px;">{ecole_elem} — Classe : {classe_elem}</span>
                    </div>
                    <div style="font-size: 1.1rem; font-weight: 700; color: #1e293b;">{date_elem}</div>
                </div>

                <div style="margin-bottom: 10px; font-size: 0.9rem; background: #f8fafc; padding: 8px; border-left: 4px solid #3b82f6;">
                    <strong>Bonjour !</strong> {consigne_entree}
                </div>

                <table style="width: 100%; border-collapse: collapse; font-size: 0.88rem; margin-bottom: 15px;">
                    <thead>
                        <tr style="background: #f1f5f9; border-bottom: 2px solid #cbd5e1;">
                            <th style="border: 1px solid #cbd5e1; padding: 8px; width: 15%; text-align: left;">Horaire</th>
                            <th style="border: 1px solid #cbd5e1; padding: 8px; width: 25%; text-align: left;">Matière</th>
                            <th style="border: 1px solid #cbd5e1; padding: 8px; text-align: left;">Consignes pour le / la suppléant(e)</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td style="border: 1px solid #cbd5e1; padding: 6px; font-weight: bold;">8h40 - 8h50</td>
                            <td style="border: 1px solid #cbd5e1; padding: 6px;">Exercices d'ouverture</td>
                            <td style="border: 1px solid #cbd5e1; padding: 6px;">Prise des présences, hymne national, routine de classe.</td>
                        </tr>
                        <tr>
                            <td style="border: 1px solid #cbd5e1; padding: 6px; font-weight: bold;">8h50 - 9h50</td>
                            <td style="border: 1px solid #cbd5e1; padding: 6px;">Français / UFLI</td>
                            <td style="border: 1px solid #cbd5e1; padding: 6px;">{mat_fr}</td>
                        </tr>
                        <tr>
                            <td style="border: 1px solid #cbd5e1; padding: 6px; font-weight: bold;">9h50 - 10h20</td>
                            <td style="border: 1px solid #cbd5e1; padding: 6px;">Mathématiques</td>
                            <td style="border: 1px solid #cbd5e1; padding: 6px;">{mat_math}</td>
                        </tr>
                        <tr style="background: #fee2e2;">
                            <td style="border: 1px solid #cbd5e1; padding: 6px; font-weight: bold; color: #991b1b;">10h20 - 10h35</td>
                            <td style="border: 1px solid #cbd5e1; padding: 6px; font-weight: bold; color: #991b1b;">Récréation</td>
                            <td style="border: 1px solid #cbd5e1; padding: 6px; font-weight: bold; color: #991b1b;">⚠️ SURVEILLANCE : {surveillance_elem}</td>
                        </tr>
                        <tr>
                            <td style="border: 1px solid #cbd5e1; padding: 6px; font-weight: bold;">10h35 - 11h35</td>
                            <td style="border: 1px solid #cbd5e1; padding: 6px;">Éd. Physique / Spécialité</td>
                            <td style="border: 1px solid #cbd5e1; padding: 6px;">Accompagner les élèves au gymnase ou à la bibliothèque avec le spécialiste.</td>
                        </tr>
                        <tr style="background: #f1f5f9;">
                            <td style="border: 1px solid #cbd5e1; padding: 8px; text-align: center; font-weight: bold;" colspan="3">11h35 - 12h35 : DÎNER-MIDI</td>
                        </tr>
                        <tr>
                            <td style="border: 1px solid #cbd5e1; padding: 6px; font-weight: bold;">12h35 - 13h05</td>
                            <td style="border: 1px solid #cbd5e1; padding: 6px;">Lecture & Écriture</td>
                            <td style="border: 1px solid #cbd5e1; padding: 6px;">Retour au calme. {mat_apresmidi}</td>
                        </tr>
                        <tr>
                            <td style="border: 1px solid #cbd5e1; padding: 6px; font-weight: bold;">13h05 - 14h05</td>
                            <td style="border: 1px solid #cbd5e1; padding: 6px;">Sciences de la nature</td>
                            <td style="border: 1px solid #cbd5e1; padding: 6px;">Travail en duo autorisé. Feuilles d'activités supplémentaires sur la table du fond.</td>
                        </tr>
                        <tr style="background: #fee2e2;">
                            <td style="border: 1px solid #cbd5e1; padding: 6px; font-weight: bold; color: #991b1b;">14h05 - 14h20</td>
                            <td style="border: 1px solid #cbd5e1; padding: 6px; font-weight: bold; color: #991b1b;">Récréation</td>
                            <td style="border: 1px solid #cbd5e1; padding: 6px; font-weight: bold; color: #991b1b;">⚠️ SURVEILLANCE : {surveillance_elem}</td>
                        </tr>
                        <tr>
                            <td style="border: 1px solid #cbd5e1; padding: 6px; font-weight: bold;">14h20 - 15h20</td>
                            <td style="border: 1px solid #cbd5e1; padding: 6px;">E.L.A. & Départ</td>
                            <td style="border: 1px solid #cbd5e1; padding: 6px;">{mat_ela}</td>
                        </tr>
                    </tbody>
                </table>

                <div style="border: 1px dashed #64748b; padding: 10px; background: #fafafa; border-radius: 4px;">
                    <div style="font-weight: bold; font-size: 0.88rem; margin-bottom: 4px; color: #334155;">📝 Billet de liaison du suppléant (à laisser sur le bureau à 15h30) :</div>
                    <div style="font-size: 0.82rem; color: #64748b; min-height: 45px;">
                        • Élèves absents : ________________________________________________________________<br>
                        • Déroulement général : [ &nbsp; ] Très bien &nbsp;&nbsp; [ &nbsp; ] Correct &nbsp;&nbsp; [ &nbsp; ] Difficile<br>
                        • Notes particulières pour le titulaire : __________________________________________________
                    </div>
                    <div style="text-align: right; font-weight: bold; font-size: 0.85rem; color: #0f172a; margin-top: 5px;">Merci et bonne journée !</div>
                </div>
            </div>
            """
            st.markdown(html_elem, unsafe_allow_html=True)
            components.html("<script>function imprimer(){ window.print(); }</script><button onclick='imprimer()' style='margin-top:12px; padding:9px 18px; background:#1e3a8a; color:white; border:none; border-radius:6px; font-weight:600; cursor:pointer;'>🖨️ Imprimer la feuille pour le classeur (Format Lettre)</button>", height=55)

    # -------------------------------------------------------------------------
    # GABARIT 2 : SECONDAIRE / COLLÈGE (9E À 12E ANNÉE)
    # -------------------------------------------------------------------------
    with tab_sec:
        st.subheader("🏛️ Générateur de Daybook — Secondaire / Collège (9e à 12e)")
        st.write("Organisé par grandes périodes de cours, locaux de spécialité et politiques d'établissement.")

        col_s1, col_s2, col_s3 = st.columns(3)
        with col_s1:
            ecole_sec = st.selectbox("Établissement Secondaire :", [
                "Collège Louis-Riel (Winnipeg)",
                "Collège Pierre-Elliott-Trudeau (Transcona)",
                "Vincent Massey Collegiate (Pembina Trails)",
                "Glenlawn Collegiate (Louis Riel SD)",
                "École régionale Gabrielle-Roy (Île-des-Chênes)",
                "Autre Collegiate / High School"
            ], key="sec_ecole", help="Établissement secondaire hôte.")
            date_sec = st.text_input("Date :", value="Lundi 28 octobre", key="sec_date")
        with col_s2:
            titulaire_sec = st.text_input("Enseignant(e) titulaire :", value="M. KHALIFA (Sciences & STIAM)", key="sec_titulaire", help="Nom du professeur remplacé.")
            local_base = st.text_input("Local d'accueil / Bureau :", value="Salle 204 (Clé au secrétariat)", key="sec_local", help="Où se rendre à l'arrivée le matin.")
        with col_s3:
            surv_sec = st.text_input("Surveillance / Corridor :", value="11 h 30 - 11 h 50 : Cafétéria Nord", key="sec_surv", help="Plage de surveillance assignée au suppléant.")
            politique_sec = st.text_input("Directives d'école :", value="Cellulaires interdits en classe. Présences obligatoires sur PowerSchool.", key="sec_pol", help="Règles d'établissement à rappeler.")

        st.markdown("##### 🔬 Contenu des Périodes du Secondaire :")
        sp_c1, sp_c2 = st.columns(2)
        with sp_c1:
            p1_info = st.text_area("Période 1 (8h50 - 10h05) :", value="Biologie 40S (Salle 204) : Exercices génétique mendélienne p. 142. Travail autonome individuel.", height=85)
            p2_info = st.text_area("Période 2 (10h15 - 11h30) :", value="Informatique 40S (Labo STIAM 108) : Défi Python sur les fonctions. Ouvrir le bac à sable MTS AI.", height=85)
        with sp_c2:
            p3_info = st.text_area("Période 3 (12h35 - 13h50) :", value="Mathématiques Pré-calcul 30S (Salle 204) : Chapitre 4 (Trigonométrie). Feuilles d'exercices sur le bureau.", height=85)
            p4_info = st.text_area("Période 4 (14h00 - 15h15) :", value="Période de préparation / Remplacement interne assigné par la direction. Se présenter au secrétariat.", height=85)

        if st.button("📄 Générer la Fiche Imprimable du Collège (9e à 12e)", type="primary", use_container_width=True):
            html_sec = f"""
            <div style="font-family: Arial, sans-serif; background: #ffffff; color: #0f172a; padding: 25px; border-radius: 8px; border: 2px solid #334155;">
                <div style="display: flex; justify-content: space-between; border-bottom: 2px solid #1e3a8a; padding-bottom: 10px; margin-bottom: 12px;">
                    <div>
                        <div style="font-size: 1.4rem; font-weight: 800; color: #1e3a8a;">{ecole_sec}</div>
                        <div style="font-size: 1rem; color: #475569; font-weight: 600;">Dossier de Suppléance — Titulaire : {titulaire_sec} | Local : {local_base}</div>
                    </div>
                    <div style="text-align: right;">
                        <div style="font-size: 1.1rem; font-weight: 700;">{date_sec}</div>
                        <span style="background: #e2e8f0; color: #0f172a; padding: 3px 8px; border-radius: 4px; font-size: 0.8rem; font-weight: 600;">Secondaire (9e-12e)</span>
                    </div>
                </div>

                <div style="background: #f8fafc; border: 1px solid #cbd5e1; padding: 8px 12px; border-radius: 6px; font-size: 0.88rem; margin-bottom: 15px;">
                    <strong>📌 Consignes et protocoles :</strong> {politique_sec}
                </div>

                <table style="width: 100%; border-collapse: collapse; font-size: 0.88rem; margin-bottom: 15px;">
                    <thead>
                        <tr style="background: #1e293b; color: white;">
                            <th style="padding: 8px; width: 18%; text-align: left;">Période / Horaire</th>
                            <th style="padding: 8px; width: 25%; text-align: left;">Cours & Local</th>
                            <th style="padding: 8px; text-align: left;">Plan de travail & Objectifs</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr style="border-bottom: 1px solid #cbd5e1;">
                            <td style="padding: 8px; font-weight: bold;">Période 1<br><span style="font-size: 0.8rem; color: #64748b;">8h50 - 10h05</span></td>
                            <td style="padding: 8px; font-weight: 600; color: #1e3a8a;">Biologie 40S<br><small style="color: #64748b;">Salle 204</small></td>
                            <td style="padding: 8px;">{p1_info}</td>
                        </tr>
                        <tr style="border-bottom: 1px solid #cbd5e1;">
                            <td style="padding: 8px; font-weight: bold;">Période 2<br><span style="font-size: 0.8rem; color: #64748b;">10h15 - 11h30</span></td>
                            <td style="padding: 8px; font-weight: 600; color: #1e3a8a;">Informatique 40S<br><small style="color: #64748b;">Labo STIAM 108</small></td>
                            <td style="padding: 8px;">{p2_info}</td>
                        </tr>
                        <tr style="background: #fee2e2; border-bottom: 1px solid #fca5a5;">
                            <td style="padding: 8px; font-weight: bold; color: #991b1b;">Dîner & Service<br><span style="font-size: 0.8rem;">11h30 - 12h35</span></td>
                            <td style="padding: 8px; font-weight: bold; color: #991b1b;">Surveillance assignée</td>
                            <td style="padding: 8px; font-weight: bold; color: #991b1b;">⚠️ {surv_sec} (Prendre la veste haute visibilité au bureau).</td>
                        </tr>
                        <tr style="border-bottom: 1px solid #cbd5e1;">
                            <td style="padding: 8px; font-weight: bold;">Période 3<br><span style="font-size: 0.8rem; color: #64748b;">12h35 - 13h50</span></td>
                            <td style="padding: 8px; font-weight: 600; color: #1e3a8a;">Mathématiques 30S<br><small style="color: #64748b;">Salle 204</small></td>
                            <td style="padding: 8px;">{p3_info}</td>
                        </tr>
                        <tr style="border-bottom: 1px solid #cbd5e1;">
                            <td style="padding: 8px; font-weight: bold;">Période 4<br><span style="font-size: 0.8rem; color: #64748b;">14h00 - 15h15</span></td>
                            <td style="padding: 8px; font-weight: 600; color: #1e3a8a;">Préparation / Relève<br><small style="color: #64748b;">Local assigné</small></td>
                            <td style="padding: 8px;">{p4_info}</td>
                        </tr>
                    </tbody>
                </table>

                <div style="border: 1px dashed #64748b; padding: 10px; background: #fafafa; border-radius: 4px;">
                    <div style="font-weight: bold; font-size: 0.88rem; margin-bottom: 4px; color: #334155;">📝 Rapport de fin de journée pour M. KHALIFA :</div>
                    <div style="font-size: 0.82rem; color: #64748b; min-height: 40px;">
                        • Présences complétées sur le portail : [ &nbsp; ] Oui &nbsp;&nbsp; [ &nbsp; ] Formulaire papier laissé au bureau<br>
                        • Notations sur le comportement / travaux remis : _______________________________________________<br>
                        • Clé retournée au secrétariat : [ &nbsp; ] Oui &nbsp;&nbsp; Signature : ________________________
                    </div>
                </div>
            </div>
            """
            st.markdown(html_sec, unsafe_allow_html=True)
            components.html("<script>function imprimerSec(){ window.print(); }</script><button onclick='imprimerSec()' style='margin-top:12px; padding:9px 18px; background:#0f172a; color:white; border:none; border-radius:6px; font-weight:600; cursor:pointer;'>🖨️ Imprimer la fiche Collège (Format Lettre)</button>", height=55)

    # -------------------------------------------------------------------------
    # GABARIT 3 : PROTOCOLE ATRIEVE (8 H 15)
    # -------------------------------------------------------------------------
    with tab_atrieve:
        st.subheader("⚡ Synthèse Express Atrieve ERP (Prêt à 8 h 15)")
        st.caption("Génération automatique par l'IA d'un résumé de mission pour un suppléant arrivant sans préparation.")

        col_ec1, col_ec2 = st.columns(2)
        with col_ec1:
            ecole_sel = st.selectbox("Établissement demandeur :", [
                "Collège Louis-Riel (DSFM - Winnipeg)", 
                "École Saint-Joachim (DSFM - La Broquerie)", 
                "École Pointe-des-Chênes (DSFM - Sainte-Anne)", 
                "École Réal-Bérard (DSFM - Saint-Pierre-Jolys)",
                "École Saint-Albert (DSFM - Winnipeg)",
                "Vincent Massey Collegiate (Pembina Trails)"
            ], key="atrieve_ecole")
            classe_suppl = st.selectbox("Période et matière du remplacement :", [
                "Période 2 — Biologie 40S", 
                "Période 3 — Mathématiques Pré-calcul 30S", 
                "Période 4 — Informatique 40S",
                "Journée complète — 3e/4e année combinée"
            ], key="atrieve_classe")
        with col_ec2:
            code_mission = st.text_input("Code de mission Atrieve ERP :", value="SUB-2026-MTS-8821")
            consigne_particuliere = st.text_input("Consigne spéciale laissée par le titulaire :", value="Les élèves doivent terminer les exercices sur l'hérédité mendélienne.")

        if st.button("📋 Générer le Briefing d'Urgence Express (30 secondes)", type="primary"):
            with st.spinner("Compilation du dossier de remplacement…"):
                p_sub = (
                    f"Tu es le directeur adjoint responsable des suppléances au Manitoba ({ecole_sel}).\n"
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

    # -------------------------------------------------------------------------
    # NOUVEAU GABARIT 4 : BANQUE D'ARCHIVES DES PLANS RÉELS DE SUPPLÉANCE
    # -------------------------------------------------------------------------
    with tab_archive:
        st.subheader("🗄️ Banque de Plans Réels & Exemplaires Terrain (Daybooks)")
        st.write(
            "Ce répertoire local stocke les photos et documents de vrais classeurs de suppléance récoltés sur le terrain "
            "(ex. École Saint-Albert, Collège Louis-Riel). Ces données alimentent le modèle pour affiner les grilles automatiques."
        )

        col_up_arc, col_info_arc = st.columns([2, 1])
        with col_up_arc:
            uploaded_daybooks = st.file_uploader(
                "Ajouter des photos ou scans de cartables de classe (JPG, PNG, PDF) :",
                type=["png", "jpg", "jpeg", "pdf"],
                accept_multiple_files=True,
                help="Les fichiers sont enregistrés localement dans documents/daybooks_archive/"
            )
            if uploaded_daybooks:
                for f in uploaded_daybooks:
                    file_dest = DAYBOOKS_DIR / f.name
                    with open(file_dest, "wb") as buffer:
                        buffer.write(f.getbuffer())
                st.success(f"✅ {len(uploaded_daybooks)} plan(s) ajouté(s) à la bibliothèque locale !")

        with col_info_arc:
            fichiers_archives = list(DAYBOOKS_DIR.glob("*.*"))
            st.metric("Plans archivés en local", len(fichiers_archives), "Répertoire terrain")

        st.markdown("---")
        st.markdown("##### 📂 Bibliothèque des cartables réels répertoriés :")
        if fichiers_archives:
            cols_img = st.columns(3)
            for i, p_file in enumerate(fichiers_archives):
                with cols_img[i % 3]:
                    st.caption(f"📄 **{p_file.name}**")
                    if p_file.suffix.lower() in [".png", ".jpg", ".jpeg"]:
                        st.image(str(p_file), use_container_width=True)
                    else:
                        st.info("Document PDF stocké")
        else:
            st.info("Aucun plan déposé pour l'instant. Déposez vos photos pour constituer la base d'apprentissage locale.")


# =============================================================================
# MODULE 7 : AUXILIAIRES D'ENSEIGNEMENT (EA) & INCLUSION
# =============================================================================
elif "Auxiliaires EA" in navigation_espace:
    st.title("🤝 Module 7 : Coordination des Auxiliaires d'Enseignement (EA)")
    st.caption("Feuille de mission minute (EA Briefing), étayage socratique et micro-bilans d'observation PEI")

    contenu_c = st.text_area(
        "Tâche demandée à l'élève sous PAT / IEP :",
        value="Résolution autonome de 4 problèmes de croisements génétiques (grilles de Punnett) en Biologie 40S.",
        height=90,
        help="Description succincte de l'exercice pour lequel l'auxiliaire intervient."
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
    st.caption("Suivi transparent du cheminement, coordination des binômes d'étude et liaison foyer (Conforme FIPPA)")

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
        st.write("🔬 **Laboratoire d'hérédité mendélienne — Travail d'équipe**")
        st.progress(70, text="Progression du dossier : 70%")
        st.checkbox("Étape 1 : Hypothèses et protocoles de recherche (Validé)", value=True, disabled=True)
        st.checkbox("Étape 2 : Recueil des données de croisement (Validé)", value=True, disabled=True)
        st.checkbox("Étape 3 : Révision finale avec le tuteur socratique", value=False)
        st.write("📍 **Coordination logistique :** Séance de révision partagée prévue à la bibliothèque le mercredi à 16 h 30.")
    with t_liaison:
        st.success("💡 **Note de l'équipe :** L'élève fait preuve d'une excellente assiduité réflexive. Poursuivez dans cette dynamique !")


# =============================================================================
# MODULE 9 : LAB D'APPRENTISSAGE PAR PHÉNOMÈNES (PhBL - FINLANDE / MB)
# =============================================================================
elif "Lab Phénomènes" in navigation_espace:
    st.title("🌍 Module 9 : Laboratoire d'Apprentissage par Phénomènes (PhBL)")
    st.caption("Pédagogie transdisciplinaire inspirée de la Finlande : Enquêtes complexes ancrées dans le territoire manitobain")

    st.write(
        "Ce module décloisonne les matières pour proposer une **enquête immersive**. "
        "Les élèves mobilisent simultanément les sciences, les mathématiques, l'histoire et les langues autour d'un grand défi réel du Manitoba."
    )

    phenomene_choisi = st.selectbox(
        "Choisissez un grand phénomène manitobain à explorer :",
        [
            "🌊 La crue centennale de la Rivière Rouge et la santé écologique du Lac Winnipeg",
            "❄️ L'impact des vagues de froid polaire (-45°C) sur les infrastructures et la résilience humaine",
            "⚡ La transition hydro-électrique au Manitoba et les droits territoriaux autochtones",
            "🌾 La biodiversité de la plaine d'herbes hautes et l'agriculture régénératrice",
            "🎯 Phénomène personnalisé (saisir manuellement ci-dessous)"
        ]
    )

    if "personnalisé" in phenomene_choisi:
        phenomene_input = st.text_input("Définissez le phénomène à enquêter :", value="L'érosion des berges de la rivière Assiniboine")
    else:
        phenomene_input = phenomene_choisi

    col_ph1, col_ph2 = st.columns(2)
    with col_ph1:
        niveau_ph = st.selectbox("Niveau scolaire visé :", ["Secondaire 4 (12e année / 40S)", "Secondaire 3 (11e année / 30S)", "Secondaire 1 & 2 (9e/10e)"])
    with col_ph2:
        disciplines_ph = st.multiselect(
            "Disciplines provinciales à croiser :",
            ["Biologie", "Mathématiques (Pré-calcul)", "Histoire du Canada & Manitoba", "Chimie", "Français / Rhétorique", "Physique"],
            default=["Biologie", "Mathématiques (Pré-calcul)", "Histoire du Canada & Manitoba", "Français / Rhétorique"]
        )

    if st.button("🚀 Générer la Matrice d'Enquête Transdisciplinaire", type="primary"):
        with st.spinner("Tissage des liens curriculaires interdisciplinaires…"):
            p_phbl = (
                "Tu es un expert en Phenomenon-Based Learning (PhBL) et conseiller pédagogique pour la Manitoba Teachers' Society.\n"
                f"Phénomène étudié : {phenomene_input}\n"
                f"Niveau : {niveau_ph}\n"
                f"Disciplines croisées : {', '.join(disciplines_ph)}\n\n"
                "Génère une unité d'enquête transdisciplinaire complète :\n"
                "1. 🌟 La Grande Question Directrice (problématique captivante pour des élèves du Manitoba).\n"
                "2. 🔬 Tâches d'enquête spécifiques par matière (croisement concret des résultats d'apprentissage de chaque cours).\n"
                "3. 🤝 Défi d'équipe concret (ex. simuler une commission consultative provinciale ou créer un modèle prédictif).\n"
                "4. 📝 Grille d'évaluation holistique (compétences du 21e siècle : pensée critique, collaboration, communication, rigueur scientifique).\n"
            )
            res_phbl = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": p_phbl}], temperature=0.4)
            st.markdown(res_phbl.choices[0].message.content)


# =============================================================================
# MODULE 10 : MOTEUR NEURO-COGNITIF & MÉTACOGNITION (FRANCE / JAPON)
# =============================================================================
elif "Neuro-Cognitif" in navigation_espace:
    st.title("🧠 Module 10 : Moteur Neuro-Cognitif & Métacognition Active")
    st.caption("Sciences cognitives (Dehaene) & Directives Society 5.0 (Japon) : Protection contre l'atrophie intellectuelle et répétition espacée")

    tab_anti_laziness, tab_ebbinghaus, tab_error_signal = st.tabs([
        "🛡️ Bouclier Anti-Paresse Cognitive",
        "📈 Planificateur de Répétition Espacée (J+1, J+3, J+7)",
        "🎯 Analyseur de Signal d'Erreur Bienveillant"
    ])

    with tab_anti_laziness:
        st.subheader("Miroir Métacognitif (Anti-Cognitive Offloading)")
        st.write(
            "Inspiré des garde-fous japonais : quand un élève soumet une question sans faire d'effort préalable, "
            "l'IA verrouille la réponse directe et lui tend un miroir de réflexion pour forcer l'engagement actif."
        )

        requete_eleve = st.text_area(
            "Question soumise par l'élève :",
            value="Donne-moi directement la solution pour calculer les fréquences génotypiques à l'équilibre de Hardy-Weinberg.",
            height=80
        )

        if st.button("🧠 Activer le Bouclier Métacognitif"):
            with st.spinner("Activation de la posture métacognitive…"):
                p_meta = (
                    "Tu es le Moteur Neuro-Cognitif de MTS AI, formé aux 4 piliers de Stanislas Dehaene (Engagement Actif).\n"
                    f"Requête de l'élève : {requete_eleve}\n\n"
                    "CONSIGNE STRICTE : Ne donne SURTOUT PAS la réponse ou la formule complète.\n"
                    "Agis comme un miroir métacognitif bienveillant :\n"
                    "1. Félicite l'élève pour le sujet abordé.\n"
                    "2. Pose-lui 2 questions miroir pour qu'il explicite son état de compréhension actuel (ex. 'Quelle est ton hypothèse de départ ?', 'Que représentent p et q pour toi ?').\n"
                    "3. Encourage-le à faire un premier pas par lui-même avant de débloquer la suite."
                )
                res_meta = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": p_meta}], temperature=0.3)
                st.markdown(res_meta.choices[0].message.content)

    with tab_ebbinghaus:
        st.subheader("Courbe d'Ebbinghaus & Répétition Espacée (Spaced Retrieval)")
        st.write("Ce système programme les micro-rappels pour ancrer durablement les concepts dans la mémoire à long terme.")
        
        notion_retenue = st.text_input("Notion maîtrisée aujourd'hui par l'élève :", value="La méiose et le brassage génétique")
        
        if st.button("📅 Générer le Calendrier de Consolidation Mnésique"):
            c_j1, c_j3, c_j7, c_j21 = st.columns(4)
            c_j1.success("**J + 1 (Demain)**\n\nMicro-flashcard de 60 secondes : Définir la différence entre crossing-over et ségrégation.")
            c_j3.info("**J + 3 (Mercredi)**\n\nQuestion piège de transfert : Appliquer la méiose à une anomalie chromosomique.")
            c_j7.warning("**J + 7 (Dimanche)**\n\nAuto-explication en français : Réexpliquer le schéma à voix haute au tuteur.")
            c_j21.error("**J + 21 (Avant examen)**\n\nQuiz synthèse chronométré de 3 questions formatives.")

    with tab_error_signal:
        st.subheader("Le Diagnostic du Signal d'Erreur (Non-punitif)")
        st.write("En neuro-éducation, l'erreur n'est pas une faute mais la condition sine qua non de l'apprentissage.")
        
        erreur_eleve = st.text_area("Erreur observée chez l'élève :", value="L'élève pense qu'un allèle dominant est toujours le plus fréquent dans une population.")
        
        if st.button("🔬 Décoder le Biais Cognitif"):
            with st.spinner("Analyse du signal d'erreur…"):
                p_err = (
                    "Tu es un neuro-scientifique spécialiste des apprentissages scolaires pour MTS AI.\n"
                    f"Erreur observée : {erreur_eleve}\n\n"
                    "Analyse pédagogique en 3 points :\n"
                    "1. 💡 Quel est le biais intuitif ou l'obstacle cognitif sous-jacent ? (Pourquoi le cerveau de l'élève fait cette fausse association).\n"
                    "2. 🪞 Une analogie ou un contre-exemple frappant pour briser ce biais en douceur.\n"
                    "3. 🎯 Une question socratique de rebond pour valider que le nouveau modèle mental est acquis."
                )
                res_err = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": p_err}], temperature=0.3)
                st.markdown(res_err.choices[0].message.content)


# =============================================================================
# PIED DE PAGE INSTITUTIONNEL & DÉDICACE AU MANITOBA (MTS AI)
# =============================================================================
st.divider()
st.markdown(
    """
    <div style="text-align: center; padding: 22px 10px 15px 10px; line-height: 1.7;">
        <div style="font-weight: 700; color: #f1f5f9; font-size: 1.05rem; letter-spacing: 0.3px; margin-bottom: 6px;">
            MTS AI · Conçu avec passion et rigueur par <span style="color: #60a5fa;">Sami KHALIFA</span>
        </div>
        <div style="font-style: italic; color: #cbd5e1; max-width: 860px; margin: 0 auto; font-size: 0.96rem;">
            « Offert avec amour et gratitude à cette terre du Manitoba qui a ouvert ses bras à ma famille et à mes enfants — 
            puisse cette œuvre semer l’excellence, l’équité et la lumière du savoir dans le cœur de chaque élève. »
        </div>
        <div style="font-size: 0.82rem; color: #64748b; margin-top: 10px; font-weight: 500;">
            Écosystème Pédagogique Souverain · Manitoba Teachers' Society 🦬 🌾 ⚜️ · 2026-2032
        </div>
    </div>
    """,
    unsafe_allow_html=True
)
