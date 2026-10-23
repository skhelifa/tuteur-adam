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
# Adam's tutor — Application d'étude Socratique DSFM
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


# Initialisation des variables d'état (Session State)
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


# --- BARRE LATÉRALE ---
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


# Initialisation de l'historique
if "histories_by_course" not in st.session_state:
    st.session_state.histories_by_course = {}
if course_name not in st.session_state.histories_by_course:
    st.session_state.histories_by_course[course_name] = [{
        "role": "assistant",
        "content": course["welcome"],
    }]

history = st.session_state.histories_by_course[course_name]

# Traitement de l'audio
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
            except Exception as exc:
                st.error(f"Erreur transcription : {exc}")
                st.session_state.processed_audio_hash = audio_hash


# =====================================================================
# 1. AFFICHAGE DE LA DISCUSSION ET DES SUGGESTIONS
# =====================================================================
for idx, msg in enumerate(history):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        
        if msg["role"] == "assistant" and idx == len(history) - 1 and enable_voice_output:
            speak_text(msg["content"])
    
    if msg["role"] == "assistant" and idx == len(history) - 1:
        st.markdown("💡 **Suggestions rapides :**")
        col1, col2, col3, col4 = st.columns(4)
        btn_query = None
        with col1:
            if st.button("📖 Expliquer simplement", key=f"s1_{idx}", use_container_width=True):
                btn_query = "Peux-tu m'expliquer cela plus simplement en français avec une analogie claire ?"
        with col2:
            if st.button("📝 Donner un exemple", key=f"s2_{idx}", use_container_width=True):
                btn_query = "Peux-tu me donner un exemple concret issu du cours en français ?"
        with col3:
            if st.button("🎥 Vidéo YouTube", key=f"s3_{idx}", use_container_width=True):
                btn_query = "Peux-tu me donner des liens de recherche YouTube cliquables pour illustrer ce concept ?"
        with col4:
            if st.button("🖼️ Schéma visuel", key=f"s4_{idx}", use_container_width=True):
                btn_query = "Peux-tu me décrire un schéma visuel étape par étape en français ?"

        if btn_query:
            st.session_state.next_question = btn_query
            st.rerun()

        st.markdown("")
        if st.button("🎯 🎲 Générer un quiz de 10 questions sur cette discussion", key=f"quiz_btn_{idx}", use_container_width=True):
            with st.spinner("Génération du quiz personnalisé..."):
                recent_discussion = "\n".join([f"{m['role']}: {m['content']}" for m in history[-6:]])
                quiz = generate_qcm_from_context(
                    course_name,
                    COURSES[course_name]["system"],
                    recent_discussion,
                    number_questions=10,
                )
            if quiz and "questions" in quiz:
                st.session_state.quiz_data = quiz
                st.session_state.quiz_submitted = False
                st.rerun()
            else:
                st.error("Impossible de générer le quiz. Réessaie !")


# =====================================================================
# 2. AFFICHAGE DU QUIZ (DIRECTEMENT APRÈS LA DISCUSSION)
# =====================================================================
if st.session_state.quiz_data:
    questions = st.session_state.quiz_data.get("questions", [])
    total = len(questions)
    st.divider()
    st.subheader(f"🎯 Quiz d'entraînement — {course_name}")
    st.write(f"**{total} questions** · Basé sur vos échanges récents")

    if not st.session_state.quiz_submitted:
        with st.form("qcm_exam_form"):
            user_answers = {}
            for i, item in enumerate(questions):
                st.markdown(f"### Question {i + 1} sur {total}")
                st.write(item["question"])
                option_labels = [
                    f"{letter}. {item['options'][letter]}"
                    for letter in ("A", "B", "C", "D")
                ]
                choice = st.radio(
                    "Choisis une réponse :",
                    option_labels,
                    index=None,
                    key=f"quiz_answer_{i}",
                )
                user_answers[i] = choice
                with st.expander("💡 Besoin d'un indice ?"):
                    st.write(item.get("hint", "Aucun indice disponible."))
                st.divider()

            submitted = st.form_submit_button(
                "✅ Soumettre l'examen et voir mon score",
                type="primary",
            )

        if submitted:
            st.session_state.quiz_answers = user_answers
            st.session_state.quiz_submitted = True
            st.rerun()

    else:
        score = 0
        user_answers = st.session_state.quiz_answers
        st.markdown("### 📊 Résultats détaillés de ton examen :")
        for i, item in enumerate(questions):
            ans = user_answers.get(i)
            correct_letter = item["correct"].upper()
            st.markdown(f"**Question {i + 1} : {item['question']}**")

            if ans:
                selected_letter = ans[0].upper()
                if selected_letter == correct_letter:
                    score += 1
                    st.success(
                        f"✅ Correct ! Ta réponse : {ans}\n\n*{item['explanation']}*"
                    )
                else:
                    st.error(
                        f"❌ Incorrect. Ta réponse : {ans} | Bonne réponse : **{correct_letter}. {item['options'].get(correct_letter, '')}**\n\n*{item['explanation']}*"
                    )
            else:
                st.warning(
                    f"⚠️ Sans réponse. La bonne réponse était **{correct_letter}. {item['options'].get(correct_letter, '')}**\n\n*{item['explanation']}*"
                )
            st.markdown("---")

        percentage = (score / total) * 100 if total > 0 else 0
        st.markdown(f"## 🏆 Ton Score Final : {score} / {total} ({percentage:.0f}%)")

        if score >= 8:
            st.balloons()
            st.success("🎉 Excellent travail ! Tu maîtrises parfaitement ton sujet.")
        elif score >= 5:
            st.info("👍 Bon effort ! Encore quelques révisions et ce sera parfait.")
        else:
            st.warning("💡 Prends le temps de revoir les notions avec le tuteur socratique pour progresser !")

        if st.button("🔄 Fermer ce quiz et continuer la discussion"):
            st.session_state.quiz_data = None
            st.session_state.quiz_submitted = False
            st.session_state.quiz_answers = {}
            st.rerun()

    st.divider()


# =====================================================================
# 3. GESTION DES ENTRÉES UTILISATEUR ET REQUÊTES
# =====================================================================
if st.session_state.pending_audio_text:
    st.info("Transcription vocale — vérifie-la, puis clique sur Envoyer.")
    with st.form("voice_transcript_form", clear_on_submit=True):
        corrected_text = st.text_area(
            "Votre question transcrite",
            value=st.session_state.pending_audio_text,
            height=100,
        )
        submitted_voice = st.form_submit_button("Envoyer la question")
    if submitted_voice and corrected_text.strip():
        st.session_state.pending_audio_text = None
        st.session_state.next_question = corrected_text.strip()
        st.rerun()

typed_question = st.chat_input("Pose une question en français ou en anglais…")
question = typed_question
if not question and st.session_state.get("next_question"):
    question = st.session_state.pop("next_question")

if question and question.strip():
    question = question.strip()
    history.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    all_chunks = load_pdf_chunks(str(folder))
    relevant = retrieve_chunks(question, all_chunks)
    if relevant:
        excerpts = "\n\n".join(
            f"[Source file: {item['source']}]\n{item['text']}" for item in relevant
        )
        context_block = (
            "The following are excerpts retrieved from local course PDFs (DSFM / Manitoba curriculum). Use them"
            " when relevant, cite the source filename in your response, and say"
            " when they do not answer the question.\n\n"
            + excerpts
        )
        st.caption(
            "Références officielles utilisées : "
            + ", ".join(sorted({item["source"] for item in relevant}))
        )
    else:
        context_block = (
            "No relevant passage was retrieved from the local course PDFs for this"
            " question. Answer helpfully from general Manitoba curriculum knowledge."
        )

    api_history = [
        msg for msg in history 
        if not (msg["role"] == "assistant" and msg["content"] == course["welcome"])
    ]

    messages_for_api = [{
        "role": "system",
        "content": course["system"] + "\n\n" + context_block + "\n\n"
        "RAPPEL ABSOLU DE LA MÉTHODE SOCRATIQUE : Réponds en FRANÇAIS. Ne donne jamais de solution complète d'un seul coup. Pose UNE SEULE question socratique claire pour faire réfléchir Adam, et propose des liens cliquables YouTube si pertinent.",
    }] + api_history[-12:]

    with st.chat_message("assistant"):
        with st.spinner("Réflexion socratique…"):
            try:
                response = client.chat.completions.create(
                    model="gpt-4o-mini", messages=messages_for_api, temperature=0.4
                )
                answer = (
                    response.choices[0].message.content
                    or "Je n'ai pas pu générer de réponse. Veuillez réessayer."
                )
                st.markdown(answer)
                history.append({"role": "assistant", "content": answer})

                if enable_voice_output:
                    speak_text(answer)

            except Exception as exc:
                st.error(f"Une erreur s'est produite lors de la génération de la réponse : {exc}")

    st.session_state.histories_by_course[course_name] = history
    st.rerun()

st.divider()
st.caption(
    "Made with care by Dad ❤️ · Keep asking questions, practise, and build"
    " your own understanding."
)
