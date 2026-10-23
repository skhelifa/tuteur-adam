from collections import Counter
import hashlib
import io
import json
import os
from pathlib import Path
import re

from openai import OpenAI
from pypdf import PdfReader
import streamlit as st
import streamlit.components.v1 as components

# ------------------------------------------------------------
# Adam's tutor — separate application. Does not modify Toutou.
# ------------------------------------------------------------

APP_DIR = Path(__file__).parent
DOCS_DIR = APP_DIR / "documents"

COURSES = {
    "Biology 40S": {
        "folder": "biology",
        "welcome": (
            "Salut Adam ! Bienvenue en Biologie 40S. Sur quel sujet travailles-tu"
            " aujourd'hui ? Nous pouvons revoir la génétique, l'hérédité, l'évolution,"
            " la biodiversité ou une question de ton cours."
        ),
        "system": """
Tu es le tuteur patient et rigoureux d'Adam pour le cours de Biologie 40S (12e année) au Collège Louis-Riel au Manitoba (normes DSFM).
APPROCHE SOCRATIQUE OBLIGATOIRE : Enseigne en FRANÇAIS. Ne donne jamais de réponses directes et massives. Pose UNE seule question claire et gérable à la fois, guide Adam par des indices, vérifie sa compréhension et corrige les idées fausses avec bienveillance.
À la fin de ta réponse, propose toujours des pistes de réflexion ou de discussion.
""",
    },
    "English — Comprehensive Focus 40S": {
        "folder": "english",
        "welcome": (
            "Salut Adam ! Bienvenue en Anglais Comprehensive Focus 40S. Nous"
            " pouvons travailler sur la lecture, l'analyse littéraire, l'écriture"
            " persuasive ou la grammaire."
        ),
        "system": """
Tu es le tuteur d'Adam pour le cours d'anglais Comprehensive Focus 40S au Manitoba. 
APPROCHE SOCRATIQUE OBLIGATOIRE : Explique les stratégies en français, pose des questions étape par étape, aide Adam à structurer sa pensée sans rédiger son travail à sa place.
""",
    },
    "Cinema — Witness to Modern History 40S": {
        "folder": "cinema",
        "welcome": (
            "Salut Adam ! Bienvenue en Cinéma (Témoin de l'histoire moderne 40S)."
            " Dis-moi quel film, période historique ou travail tu étudies."
        ),
        "system": """
Tu es le tuteur d'Adam pour le cours manitobain « Le cinéma, témoin de l'histoire moderne 40S ».
APPROCHE SOCRATIQUE OBLIGATOIRE : Enseigne en FRANÇAIS. Guide-le par des questions socratiques sur le contexte historique, les choix de réalisation et l'esprit critique, une question à la fois.
""",
    },
}

st.set_page_config(
    page_title="Adam's Study Tutor", page_icon="🎓", layout="centered"
)
st.title("🎓 Adam's Study Tutor")
st.caption("Collège Louis-Riel · Grade 12 · 40S (DSFM)")
st.info(
    "Utilise ce tuteur pour comprendre tes cours, t'entraîner et progresser pas à pas."
)

api_key = st.secrets.get("OPENAI_API_KEY") if hasattr(st, "secrets") else None
api_key = api_key or os.environ.get("OPENAI_API_KEY")
if not api_key:
    st.error(
        "The OpenAI API key is not configured. The app administrator must add"
        " OPENAI_API_KEY in Streamlit app Secrets."
    )
    st.stop()

client = OpenAI(api_key=api_key)


def speak_text(text: str):
    clean_text = (
        text.replace("'", "\\'")
        .replace('"', '\\"')
        .replace("\n", " ")
        .replace("\r", " ")
    )
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
    js_code = """
    <script>
        window.speechSynthesis.cancel();
    </script>
    """
    components.html(js_code, height=0)


if "quiz_data" not in st.session_state:
    st.session_state.quiz_data = None
if "show_hint" not in st.session_state:
    st.session_state.show_hint = False
if "quiz_submitted" not in st.session_state:
    st.session_state.quiz_submitted = False
if "quiz_answers" not in st.session_state:
    st.session_state.quiz_answers = {}
if "next_question" not in st.session_state:
    st.session_state.next_question = None


def generate_qcm_from_context(course_title, system_prompt, discussion_context, number_questions=10):
    prompt = f"""En te basant sur la discussion récente et le cours : {course_title}, crée un quiz d'entraînement de {number_questions} questions à choix multiples (QCM) en français.
Contexte de la discussion récente :
{discussion_context}

Format de l'examen :
- Exactement {number_questions} questions.
- Quatre options par question (A, B, C, D).
- Une seule bonne réponse par question.
- Rédige tout en français avec une explication et un indice (hint) pour chaque question.

Renvoie UNIQUEMENT un objet JSON valide dans cette structure exacte :
{{
  "questions": [
    {{
      "question": "Texte de la question",
      "options": {{
        "A": "Option A",
        "B": "Option B",
        "C": "Option C",
        "D": "Option D"
      }},
      "correct": "A",
      "hint": "Indice utile",
      "explanation": "Explication détaillée"
    }}
  ]
}}"""
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
            json_str = match.group(0)
            return json.loads(json_str)
        return None
    except Exception as e:
        print(f"Erreur de génération JSON : {e}")
        return None


# --- BARRE LATÉRALE COMPACTE ET ÉPURÉE ---
with st.sidebar:
    st.markdown("### 📚 Matière")
    course_name = st.radio(
        "Matière active",
        list(COURSES.keys()),
        label_
