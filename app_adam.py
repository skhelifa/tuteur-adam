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
Enseigne en FRANÇAIS par défaut. Utilise une approche socratique : pose une seule question gérable à la fois, donne des indices avant les solutions complètes, et corrige les idées fausses avec bienveillance.
IMPORTANT POUR LES LIENS : À la fin de ta réponse, tu dois TOUJOURS proposer de vrais liens cliquables Markdown vers YouTube sous ce format exact :
[🎥 Rechercher sur YouTube](https://www.youtube.com/results?search_query=QUERY_EN_URL)
Remplace QUERY_EN_URL par des mots-clés pertinents (en séparant les mots par des '+').
Lorsque des extraits de documents de cours sont fournis, priorise-les et cite le nom du fichier source.
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
Tu es le tuteur d'Adam pour le cours d'anglais Comprehensive Focus 40S au Manitoba. Bien que le cours soit en anglais, explique les stratégies et réponds principalement en français pour aider Adam à progresser, puis donne des exemples en anglais.
Fournis de vrais liens Markdown cliquables lorsque tu suggères des recherches, formatés ainsi : [🎥 Rechercher sur YouTube](https://www.youtube.com/results?search_query=...).
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
Enseigne en FRANÇAIS. Aide-le à analyser le cinéma comme art et artefact historique (contexte, point de vue, techniques).
Fournis de vrais liens Markdown cliquables pour les recherches vidéo, formatés ainsi : [🎥 Rechercher sur YouTube](https://www.youtube.com/results?search_query=...).
""",
    },
}

st.set_page_config(
    page_title="Adam's Study Tutor", page_icon="🎓", layout="centered"
)
st.title("🎓 Adam's Study Tutor")
st.caption("Collège Louis-Riel · Grade 12 · 40S (DSFM)")
st.info(
    "Utilise ce tuteur pour comprendre tes cours, t'entraîner avec des quiz et"
    " préparer tes examens."
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


# Fonction pour la synthèse vocale du navigateur (Option 2)
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


# Fonction pour couper la parole immédiatement
def stop_speech():
    js_code = """
    <script>
        window.speechSynthesis.cancel();
    </script>
    """
    components.html(js_code, height=0)


# Gestion des états du Quiz et des prompts
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


def generate_qcm(course_title, system_prompt, chunks_text, number_questions=10):
    prompt = f"""Crée un examen d'entraînement d'exactement {number_questions} questions à choix multiples (QCM) pour un élève de 12e année basé sur les standards de la DSFM et du Manitoba pour le cours : {course_title}.
Format de l'examen :
- Exactement {number_questions} questions.
- Quatre options par question, étiquetées A, B, C, D.
- Une seule bonne réponse par question.
- Rédige toutes les questions, options, indices et explications en français.
- Inclus une courte explication et un indice utile pour chaque question.

Utilise ces extraits de cours / anciens examens si pertinent :
{chunks_text}

Renvoie UNIQUEMENT un tableau JSON valide dans cette structure exacte :
{{
  "questions": [
    {{
      "question": "Texte de la question",
      "options": {{
        "A": "Première option",
        "B": "Deuxième option",
        "C": "Troisième option",
        "D": "Quatrième option"
      }},
      "correct": "A",
      "hint": "Un indice utile",
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
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
        return json.loads(content.strip())
    except Exception:
        return None


# --- BARRE LATÉRALE MODERNE ET ÉPURÉE ---
with st.sidebar:
    st.markdown("### 📚 Matière active")
    course_name = st.radio(
        "Choisir une matière",
        list(COURSES.keys()),
        label_visibility="collapsed"
    )
    st.divider()

    st.markdown("### 🎯 Mode Examen (10 Q)")
    st.caption("Test blanc basé sur les programmes du Manitoba.")
    if st.button("🎲 Générer le quiz", use_container_width=True):
        st.session_state.show_hint = False
        st.session_state.quiz_submitted = False
        folder_path = DOCS_DIR / COURSES[course_name]["folder"]
        all_chunks_temp = []
        if folder_path.exists():
            for pdf_path in sorted(folder_path.glob("*.pdf")):
                try:
                    reader = PdfReader(str(pdf_path))
                    full_text = "\n".join(
                        (page.extract_text() or "") for page in reader.pages
                    )
                    if full_text.strip():
                        all_chunks_temp.append(f"\n{full_text[:6000]}")
                except Exception:
                    continue
        chunks_text = "\n\n".join(all_chunks_temp[:3])
        with st.spinner("Préparation de l'examen d'entraînement d'Adam..."):
            quiz = generate_qcm(
                course_name,
                COURSES[course_name]["system"],
                chunks_text,
                number_questions=10,
            )
        if quiz:
            st.session_state.quiz_data = quiz
            st.session_state.quiz_submitted = False
        else:
            st.error("Impossible de générer le quiz. Réessaie !")

    st.divider()
    st.markdown("### 🔊 Audio")
    enable_voice_output = st.checkbox("Lecture vocale automatique", value=True)
    if st.button("🛑 Arrêter la parole", use_container_width=True):
        stop_speech()
        st.success("Voix arrêtée.")
    st.divider()

    st.markdown("### 🎤 Vocal")
    audio_value = st.audio_input("Enregistrer")

course = COURSES[course_name]
folder = DOCS_DIR / course["folder"]


@st.cache_data(show_spinner=False)
def load_pdf_chunks(folder_string: str):
    folder_path = Path(folder_string)
    chunks = []
    if not folder_path.exists():
        return chunks
    for pdf_path in sorted(folder_path.glob("*.pdf")):
        try:
            reader = PdfReader(str(pdf_path))
            full_text = "\n".join((page.extract_text() or "") for page in reader.pages)
            full_text = re.sub(r"[ \t]+", " ", full_text)
            full_text = re.sub(r"\n{3,}", "\n\n", full_text).strip()
            if not full_text:
                continue
            paragraphs = [p.strip() for p in re.split(r"\n\s*\n", full_text) if p.strip()]
            current = ""
            for para in paragraphs:
                if len(current) + len(para) > 1400 and current:
                    chunks.append({"source": pdf_path.name, "text": current})
                    current = ""
                if len(para) > 1800:
                    for start in range(0, len(para), 1400):
                        piece = para[start : start + 1400]
                        if piece.strip():
                            chunks.append({"source": pdf_path.name, "text": piece})
                else:
                    current = (current + "\n\n" + para).strip()
            if current:
                chunks.append({"source": pdf_path.name, "text": current})
        except Exception:
            continue
    return chunks


def retrieve_chunks(question: str, chunks: list, limit: int = 4):
    if not chunks or not question.strip():
        return []
    stop_words = {
        "the", "and", "for", "with", "that
