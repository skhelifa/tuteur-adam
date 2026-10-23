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
        "system": (
            "Tu es le tuteur patient et rigoureux d'Adam pour le cours de Biologie 40S (12e année) "
            "au Collège Louis-Riel au Manitoba (normes DSFM).\n"
            "APPROCHE SOCRATIQUE OBLIGATOIRE : Enseigne en FRANÇAIS. Ne donne jamais de réponses directes "
            "et massives. Pose UNE seule question claire et gérable à la fois, guide Adam par des indices, "
            "vérifie sa compréhension et corrige les idées fausses avec bienveillance.\n"
            "À la fin de ta réponse, propose toujours des pistes de réflexion ou de discussion."
        ),
    },
    "English — Comprehensive Focus 40S": {
        "folder": "english",
        "welcome": (
            "Salut Adam ! Bienvenue en Anglais Comprehensive Focus 40S. Nous"
            " pouvons travailler sur la lecture, l'analyse littéraire, l'écriture"
            " persuasive ou la grammaire."
        ),
        "system": (
            "Tu es le tuteur d'Adam pour le cours d'anglais Comprehensive Focus 40S au Manitoba.\n"
            "APPROCHE SOCRATIQUE OBLIGATOIRE : Explique les stratégies en français, pose des questions "
            "étape par étape, aide Adam à structurer sa pensée sans rédiger son travail à sa place."
        ),
    },
    "Cinema — Witness to Modern History 40S": {
        "folder": "cinema",
        "welcome": (
            "Salut Adam ! Bienvenue en Cinéma (Témoin de l'histoire moderne 40S)."
            " Dis-moi quel film, période historique ou travail tu étudies."
        ),
        "system": (
            "Tu es le tuteur d'Adam pour le cours manitobain « Le cinéma, témoin de l'histoire moderne 40S ».\n"
            "APPROCHE SOCRATIQUE OBLIGATOIRE : Enseigne en FRANÇAIS. Guide-le par des questions socratiques "
            "sur le contexte historique, les choix de réalisation et l'esprit critique, une question à la fois."
        ),
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
    prompt = (
        f"En te basant sur la discussion récente et le cours : {course_title}, "
        f"crée un quiz d'entraînement de {number_questions} questions à choix multiples (QCM) en français.\n"
        f"Contexte de la discussion récente :\n{discussion_context}\n\n"
        "Format de l'examen :\n"
        f"- Exactement {number_questions} questions.\n"
        "- Quatre options par question (A, B, C, D).\n"
        "- Une seule bonne réponse par question.\n"
        "- Rédige tout en français avec une explication et un indice (hint) pour chaque question.\n\n"
        f"Tu DOIS renvoyer un objet JSON valide contenant exactement une clé \"questions\" "
        f"qui est un tableau de {number_questions} objets avec ces clés : \"question\", "
        "\"options\" (un dictionnaire avec les clés A, B, C, D), \"correct\" (la lettre majuscule), \"hint\", \"explanation\"."
    )
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content.strip()
        return json.loads(content)
    except Exception as e:
        print(f"Erreur de génération JSON : {e}")
        return None


# --- BARRE LATÉRALE COMPACTE ET ÉPURÉE ---
with st.sidebar:
    st.markdown("### 📚 Matière")
    course_name = st.radio(
        "Matière active",
        list(COURSES.keys()),
        label_visibility="collapsed"
    )
    
    st.markdown("---")
    st.markdown("### 🔊 Audio & 🎤 Vocal")
    enable_voice_output = st.checkbox("Lecture vocale auto", value=True)
    if st.button("🛑 Arrêter la parole", use_container_width=True):
        stop_speech()
        st.success("Voix coupée.")
    
    audio_value = st.audio_input("Enregistrer votre question")

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
        "the", "and", "for", "with", "that", "this", "from", "what", "when",
        "where", "which", "how", "why", "are", "was", "were", "have", "has",
        "does", "did", "can", "could", "would", "should", "into", "about",
        "les", "des", "une", "dans", "pour", "avec", "est", "que", "qui",
        "quoi", "comment", "pourquoi", "sur", "par", "aux", "du", "de", "la",
        "le", "un", "et", "en", "je", "tu", "il", "elle"
    }
    terms = [t.lower() for t in re.findall(r"[A-Za-zÀ-ÿ0-9'-]{3,}", question)]
    terms = [t for t in terms if t not in stop_words]
    if not terms:
        return []
    scored = []
    for chunk in chunks:
        text = chunk["text"].lower()
        words = re.findall(r"[A-Za-zÀ-ÿ0-9'-]{3,}", text)
        counts = Counter(words)
        score = 0.0
        for term in set(terms):
            if term in counts:
                score += 1.0 + min(counts[term], 4) * 0.15
            else:
                if any(
                    term in word or word in term for word in counts if len(word) >= 5
                ):
                    score += 0.25
        if score > 0:
            scored.append((score, chunk))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _, chunk in scored[:limit]]


if "histories_by_course" not in st.session_state:
    st.session_state.histories_by_course = {}
if course_name not in st.session_state.histories_by_course:
    st.session_state.histories_by_course[course_name] = [{
        "role": "assistant",
        "content": course["welcome"],
    }]

history = st.session_state.histories_by_course[course_name]

if "processed_audio_hash" not in st.session_state:
    st.session_state.processed_audio_hash = None
if "pending_audio_text" not in st.session_state:
    st.session_state.pending_audio_text = None

if audio_value is not None:
    audio_bytes = audio_value.getvalue()
    audio_hash = hashlib.sha256(audio_bytes).hexdigest()
    if audio_hash != st.session_state.processed_audio_hash:
        with st.spinner("Transcription…"):
            try:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=(
                        getattr(audio_value, "name", "recording.wav"),
                        audio_bytes,
                        getattr(audio_value, "type", None) or "audio/wav",
                    ),
                )
                st.session_state.pending_audio_text = transcript.text.strip()
                st.session_state.processed_audio_hash = audio_hash
