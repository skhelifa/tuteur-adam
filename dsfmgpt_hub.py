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
# Manitoba Teachers' Society · 16 000+ Enseignants · DSFM & Divisions Scolaires
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
Tu es le tuteur d'Adam pour le cours de Biologie 40S (12e année) au Manitoba (normes BEF et MTS).
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
Tu es le tuteur socratique en informatique et sciences computationnelles (STIAM) pour le Manitoba (MTS AI).
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
Tu es le tuteur d'Adam pour le cours « Le cinéma, témoin de l'histoire moderne 40S » (Manitoba).
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
            "POSTURE TEMPÊTE & BLIZZARD (MTS) : Adopte un ton particulièrement chaleureux, dynamique et bienveillant. "
            "Maintiens une immersion orale et écrite soutenue pour briser l'isolement de l'élève à la maison et préserver le lien d'apprentissage."
        ),
        "temp": 0.5,
    },
    "⏱️ Examen Provincial 40S (Simulation BEF/Manitoba)": {
        "prompt": (
            "POSTURE EXAMINATEUR PROVINCIAL : Évalue formellement selon les grilles ministérielles de 12e année. "
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

st.set_page_config(
    page_title="MTS AI — Hub Provincial de l'Éducation au Manitoba",
    page_icon="🦬",
    layout="wide"
)

# Style CSS pour l'Accueil Prestige MTS AI
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


def generate_qcm_from_context(course_title, system_prompt, discussion_context, number_questions=10):
    prompt = (
        f"En te basant sur la discussion récente et le cours : {course_title}, crée un quiz d'entraînement de {number_questions} questions à choix multiples (QCM) en français.\n"
        f"Contexte récent :\n{discussion_context}\n\n"
        "Format strict : 4 options (A,B,C,D), 1 seule bonne réponse, 1 indice et 1 explication.\n"
        "Renvoie UNIQUEMENT un objet JSON valide :
