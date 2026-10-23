from collections import Counter
import hashlib
import html
import json
import os
from pathlib import Path
import re

import streamlit as st
import streamlit.components.v1 as components
from openai import OpenAI
from pypdf import PdfReader

# ------------------------------------------------------------
# Tuteur d'Adam — application indépendante de celle de Toutou
# ------------------------------------------------------------

APP_DIR = Path(__file__).parent
DOCS_DIR = APP_DIR / "documents"

COURSES = {
    "Biology 40S": {
        "folder": "biology",
        "welcome": (
            "Salut Adam ! Bienvenue en Biologie 40S. Nous pouvons revoir la "
            "génétique, l'hérédité, l'évolution, la biodiversité ou une question "
            "de ton cours."
        ),
        "system": """
Tu es le tuteur patient et rigoureux d'Adam pour la Biologie 40S (12e année)
au Collège Louis-Riel, au Manitoba. Réponds en français, sauf si Adam demande
explicitement une réponse en anglais. Utilise une approche socratique : une
question à la fois, indices avant la solution complète, corrections bienveillantes.
Aide à comprendre la génétique, l'hérédité, l'évolution, la biodiversité et la
conservation. Ne prétends pas connaître le barème de son enseignant.
""",
    },
    "English — Comprehensive Focus 40S": {
        "folder": "english",
        "welcome": (
            "Salut Adam ! Bienvenue en Anglais Comprehensive Focus 40S. Nous "
            "pouvons travailler sur la lecture, l'analyse littéraire, l'écriture "
            "persuasive, les textes transactionnels ou la grammaire."
        ),
        "system": """
Tu es le tuteur d'Adam pour English — Comprehensive Focus 40S au Manitoba.
Explique principalement en français pour faciliter la compréhension, mais
fournis des exemples et exercices en anglais lorsque cela aide l'apprentissage.
Aide à analyser les textes, construire une thèse, choisir des preuves, réviser
la grammaire et améliorer l'écriture. Ne prétends pas connaître le barème de
son enseignant.
""",
    },
    "Cinema — Witness to Modern History 40S": {
        "folder": "cinema",
        "welcome": (
            "Salut Adam ! Bienvenue en Cinéma, témoin de l'histoire moderne 40S. "
            "Dis-moi quel film, quelle période ou quel travail tu étudies."
        ),
        "system": """
Tu es le tuteur d'Adam pour le cours « Le cinéma, témoin de l'histoire moderne
40S ». Enseigne en français. Aide-le à analyser le cinéma comme art et comme
source historique : contexte, point de vue, représentation, techniques,
preuves, biais, omissions et interprétation historique. Ne présente pas une
scène de film comme une preuve historique indépendante sans la contextualiser.
""",
    },
}

st.set_page_config(page_title="Adam's Study Tutor", page_icon="🎓", layout="centered")
st.title("🎓 Adam's Study Tutor")
st.caption("Collège Louis-Riel · 12e année · cours 40S")
st.info(
    "Utilise ce tuteur pour comprendre tes cours, t'entraîner avec des quiz "
    "et préparer tes examens."
)

# La clé API doit être ajoutée dans Streamlit Cloud > App settings > Secrets.
try:
    api_key = st.secrets.get("OPENAI_API_KEY")
except Exception:
    api_key = None
api_key = api_key or os.environ.get("OPENAI_API_KEY")

if not api_key:
    st.error(
        "La clé API OpenAI n'est pas configurée. L'administrateur doit ajouter "
        "OPENAI_API_KEY dans les Secrets de l'application Streamlit."
    )
    st.stop()

client = OpenAI(api_key=api_key)


def speak_text(text: str):
    """Lit la réponse dans le navigateur en français."""
    safe_text = json.dumps(text[:12000], ensure_ascii=False)
    js_code = f"""
    <script>
      window.speechSynthesis.cancel();
      const msg = new SpeechSynthesisUtterance({safe_text});
      msg.lang = "fr-FR";
      window.speechSynthesis.speak(msg);
    </script>
    """
    components.html(js_code, height=0)


def stop_speech():
    components.html(
        "<script>window.speechSynthesis.cancel();</script>",
        height=0,
    )


# État persistant de l'application
DEFAULT_STATE = {
    "quiz_data": None,
    "quiz_submitted": False,
    "quiz_answers": {},
    "next_question": None,
    "processed_audio_hash": None,
    "pending_audio_text": None,
    "histories_by_course": {},
}
for state_key, default_value in DEFAULT_STATE.items():
    if state_key not in st.session_state:
        st.session_state[state_key] = default_value


@st.cache_data(show_spinner=False)
def load_pdf_chunks(folder_string: str):
    """Extrait les PDF locaux et les découpe en passages."""
    folder_path = Path(folder_string)
    chunks = []
    if not folder_path.exists():
        return chunks

    for pdf_path in sorted(folder_path.glob("*.pdf")):
        try:
            reader = PdfReader(str(pdf_path))
            full_text = "\n".join(page.extract_text() or "" for page in reader.pages)
            full_text = re.sub(r"[ \t]+", " ", full_text)
            full_text = re.sub(r"\n{3,}", "\n\n", full_text).strip()
            if not full_text:
                continue

            paragraphs = [
                part.strip()
                for part in re.split(r"\n\s*\n", full_text)
                if part.strip()
            ]
            current = ""
            for paragraph in paragraphs:
                if len(paragraph) > 1800:
                    if current:
                        chunks.append({"source": pdf_path.name, "text": current})
                        current = ""
                    for start in range(0, len(paragraph), 1400):
                        piece = paragraph[start:start + 1400].strip()
                        if piece:
                            chunks.append({"source": pdf_path.name, "text": piece})
                elif current and len(current) + len(paragraph) + 2 > 1400:
                    chunks.append({"source": pdf_path.name, "text": current})
                    current = paragraph
                else:
                    current = (current + "\n\n" + paragraph).strip()

            if current:
                chunks.append({"source": pdf_path.name, "text": current})
        except Exception:
            # Un PDF défectueux ne doit pas empêcher les autres de charger.
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
        "le", "un", "et", "en", "je", "tu", "il", "elle",
    }
    terms = [
        term.lower()
        for term in re.findall(r"[A-Za-zÀ-ÿ0-9'-]{3,}", question)
        if term.lower() not in stop_words
    ]
    if not terms:
        return []

    scored = []
    for chunk in chunks:
        words = re.findall(r"[A-Za-zÀ-ÿ0-9'-]{3,}", chunk["text"].lower())
        counts = Counter(words)
        score = 0.0
        for term in set(terms):
            if term in counts:
                score += 1.0 + min(counts[term], 4) * 0.15
            elif any(term in word or word in term for word in counts if len(word) >= 5):
                score += 0.25
        if score > 0:
            scored.append((score, chunk))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _, chunk in scored[:limit]]


def generate_qcm(course_title, system_prompt, chunks_text, number_questions=10):
    """Demande un objet JSON et vérifie la structure du quiz avant affichage."""
    prompt = f"""
Crée exactement {number_questions} questions de QCM pour un élève de 12e année
du Manitoba, pour le cours : {course_title}.

Règles :
- Exactement {number_questions} questions.
- Quatre choix par question, avec les clés A, B, C et D.
- Une seule bonne réponse, indiquée par "correct": "A", "B", "C" ou "D".
- Chaque question doit contenir question, options, correct, hint et explanation.
- Écris en français.
- Les questions doivent être pertinentes pour le cours. Si les extraits sont
  insuffisants, utilise des connaissances générales raisonnables du cours.
- N'invente pas de citation ni de référence à un document.

Extraits de cours disponibles :
{chunks_text or "Aucun PDF de cours n'est disponible. Utilise les connaissances générales du cours."}

Retourne UNIQUEMENT un objet JSON valide, sans bloc Markdown, selon ce schéma :
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
      "hint": "Indice utile sans révéler directement la réponse",
      "explanation": "Explication de la bonne réponse"
    }}
  ]
}}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.4,
        )
        content = response.choices[0].message.content or ""
        data = json.loads(content)
        questions = data.get("questions")

        if not isinstance(questions, list) or len(questions) != number_questions:
            raise ValueError(
                f"Le modèle a renvoyé {len(questions) if isinstance(questions, list) else 0} "
                f"questions au lieu de {number_questions}."
            )

        required_letters = {"A", "B", "C", "D"}
        for index, item in enumerate(questions, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"La question {index} n'est pas un objet valide.")
            if not all(key in item for key in ("question", "options", "correct", "hint", "explanation")):
                raise ValueError(f"Il manque un champ dans la question {index}.")
            if not isinstance(item["options"], dict) or not required_letters.issubset(item["options"]):
                raise ValueError(f"La question {index} ne possède pas les quatre choix A, B, C et D.")
            item["correct"] = str(item["correct"]).strip().upper()
            if item["correct"] not in required_letters:
                raise ValueError(f"La réponse correcte de la question {index} est invalide.")
        return data

    except Exception as exc:
        st.error(f"Erreur lors de la génération du quiz : {exc}")
        return None


# Barre latérale : cours, quiz, audio
with st.sidebar:
    st.header("📚 Choisir un cours")
    course_name = st.selectbox("Matière active", list(COURSES.keys()))
    st.divider()

    st.header("🎯 Mode examen — 10 questions")
    st.caption("Génère un test blanc avec quatre choix par question.")
    if st.button("🎲 Générer un quiz de 10 questions", type="primary"):
        folder_path = DOCS_DIR / COURSES[course_name]["folder"]
        pdf_texts = []
        if folder_path.exists():
            for pdf_path in sorted(folder_path.glob("*.pdf"))[:3]:
                try:
                    reader = PdfReader(str(pdf_path))
                    text = "\n".join(page.extract_text() or "" for page in reader.pages)
                    if text.strip():
                        pdf_texts.append(f"[Fichier : {pdf_path.name}]\n{text[:6000]}")
                except Exception:
                    continue

        with st.spinner("Préparation du quiz…"):
            quiz = generate_qcm(
                course_name,
                COURSES[course_name]["system"],
                "\n\n".join(pdf_texts),
                number_questions=10,
            )

        if quiz and len(quiz.get("questions", [])) == 10:
            st.session_state.quiz_data = quiz
            st.session_state.quiz_course = course_name
            st.session_state.quiz_submitted = False
            st.session_state.quiz_answers = {}
            # Efface les anciennes valeurs des boutons radio.
            for i in range(10):
                key = f"quiz_answer_{i}"
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()
        elif quiz:
            st.session_state.quiz_data = None
            st.error("Le quiz reçu ne contient pas exactement 10 questions. Réessaie.")

    st.divider()
    st.header("🔊 Lecture vocale")
    enable_voice_output = st.checkbox("Lire les réponses à voix haute", value=True)
    if st.button("🛑 Arrêter la parole"):
        stop_speech()
        st.success("Commande d'arrêt envoyée au navigateur.")

    st.divider()
    st.header("🎤 Question vocale")
    audio_value = st.audio_input("Enregistrer ta question")


course = COURSES[course_name]
folder = DOCS_DIR / course["folder"]

if course_name not in st.session_state.histories_by_course:
    st.session_state.histories_by_course[course_name] = [
        {"role": "assistant", "content": course["welcome"]}
    ]
history = st.session_state.histories_by_course[course_name]

# Transcription audio avec Whisper
if audio_value is not None:
    audio_bytes = audio_value.getvalue()
    audio_hash = hashlib.sha256(audio_bytes).hexdigest()
    if audio_hash != st.session_state.processed_audio_hash:
        with st.spinner("Transcription de l'enregistrement…"):
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
                st.error(f"Échec de la transcription vocale : {exc}")
                st.session_state.processed_audio_hash = audio_hash


# Affichage du quiz et correction
if st.session_state.quiz_data and st.session_state.get("quiz_course") == course_name:
    questions = st.session_state.quiz_data.get("questions", [])
    total = len(questions)
    st.divider()
    st.subheader(f"🎯 Examen d'entraînement — {course_name}")
    st.write(f"**{total} questions** · Une seule réponse correcte par question")

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
                user_answers[i] = st.radio(
                    "Choisis une réponse :",
                    option_labels,
                    index=None,
                    key=f"quiz_answer_{i}",
                )
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
        st.markdown("### 📊 Résultats détaillés")
        for i, item in enumerate(questions):
            answer = user_answers.get(i)
            correct_letter = item["correct"]
            st.markdown(f"**Question {i + 1} : {item['question']}**")

            if answer:
                selected_letter = answer[0].upper()
                if selected_letter == correct_letter:
                    score += 1
                    st.success(f"✅ Correct ! Ta réponse : {answer}\n\n{item['explanation']}")
                else:
                    st.error(
                        f"❌ Incorrect. Ta réponse : {answer}\n\n"
                        f"Bonne réponse : **{correct_letter}. "
                        f"{item['options'].get(correct_letter, '')}**\n\n"
                        f"{item['explanation']}"
                    )
            else:
                st.warning(
                    f"⚠️ Sans réponse. Bonne réponse : **{correct_letter}. "
                    f"{item['options'].get(correct_letter, '')}**\n\n"
                    f"{item['explanation']}"
                )
            st.markdown("---")

        percentage = (score / total * 100) if total else 0
        st.markdown(f"## 🏆 Score final : {score} / {total} ({percentage:.0f} %)")
        if score >= 8:
            st.balloons()
            st.success("🎉 Excellent travail !")
        elif score >= 5:
            st.info("👍 Bon effort ! Révise les notions à améliorer.")
        else:
            st.warning("💡 Revois les explications puis réessaie.")

        if st.button("🔄 Générer un nouveau quiz"):
            st.session_state.quiz_data = None
            st.session_state.quiz_submitted = False
            st.session_state.quiz_answers = {}
            st.rerun()

    st.divider()

# Affiche l'historique de discussion
for message in history:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Permet de relire et corriger la transcription avant envoi
if st.session_state.pending_audio_text:
    st.info("Transcription vocale : vérifie le texte avant de l'envoyer.")
    with st.form("voice_transcript_form", clear_on_submit=True):
        corrected_text = st.text_area(
            "Ta question transcrite",
            value=st.session_state.pending_audio_text,
            height=100,
        )
        submitted_voice = st.form_submit_button("Envoyer la question")
    if submitted_voice and corrected_text.strip():
        st.session_state.pending_audio_text = None
        st.session_state.next_question = corrected_text.strip()
        st.rerun()

# Suggestions rapides
st.markdown("💡 **Suggestions rapides :**")
col1, col2, col3, col4 = st.columns(4)
button_query = None
with col1:
    if st.button("📖 Expliquer plus simplement"):
        button_query = "Peux-tu m'expliquer cela plus simplement en français avec une analogie claire ?"
with col2:
    if st.button("📝 Donner un exemple"):
        button_query = "Peux-tu me donner un exemple concret lié au cours ?"
with col3:
    if st.button("🎥 Rechercher une vidéo"):
        button_query = "Donne-moi un lien de recherche YouTube cliquable pour illustrer ce concept."
with col4:
    if st.button("🖼️ Décrire un schéma"):
        button_query = "Décris-moi un schéma visuel étape par étape en français."

if button_query:
    st.session_state.next_question = button_query
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
            f"[Fichier source : {item['source']}]\n{item['text']}"
            for item in relevant
        )
        context_block = (
            "Les passages suivants proviennent des PDF locaux du cours. "
            "Utilise-les s'ils sont pertinents, cite le nom du fichier source et "
            "indique clairement si les extraits ne permettent pas de répondre.\n\n"
            + excerpts
        )
        st.caption(
            "PDF consultés : "
            + ", ".join(sorted({item["source"] for item in relevant}))
        )
    else:
        context_block = (
            "Aucun passage pertinent n'a été retrouvé dans les PDF locaux. "
            "Réponds avec prudence à partir de connaissances générales et ne "
            "prétends pas citer un document local."
        )
        if not all_chunks:
            st.caption(
                "Astuce : ajoute des PDF de cours autorisés dans le dossier "
                f"`documents/{course['folder']}/` pour enrichir le tuteur."
            )

    # Important : ne transmet pas le message de bienvenue assistant comme
    # premier message de l'historique API. Cela aide les suggestions rapides.
    api_history = [
        message for message in history
        if not (
            message["role"] == "assistant"
            and message["content"] == course["welcome"]
        )
    ]

    system_message = (
        course["system"]
        + "\n\n"
        + context_block
        + "\n\nÀ la fin de ta réponse, propose si pertinent un lien Markdown "
        "cliquable de recherche YouTube, par exemple : "
        "[🎥 Rechercher sur YouTube](https://www.youtube.com/results?search_query=genetics+biology). "
        "N'invente pas une URL de vidéo spécifique. Réponds en français, sauf "
        "si l'élève demande explicitement l'anglais."
    )
    messages_for_api = [{"role": "system", "content": system_message}] + api_history[-12:]

    with st.chat_message("assistant"):
        with st.spinner("Réflexion…"):
            try:
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=messages_for_api,
                    temperature=0.4,
                )
                answer = (
                    response.choices[0].message.content
                    or "Je n'ai pas pu générer de réponse. Réessaie."
                )
                st.markdown(answer)
                history.append({"role": "assistant", "content": answer})
                if enable_voice_output:
                    speak_text(answer)
            except Exception as exc:
                st.error(f"Erreur lors de la génération de la réponse : {exc}")

    st.session_state.histories_by_course[course_name] = history

st.divider()
st.caption("Made with care by Dad ❤️ · Continue à poser des questions et à progresser.")
st.caption(
    "إلى ابني الحبيب، ضوء عيني ونبض قلبي آدم .. وجودك في حياتي هو أجمل عطايا "
    "الرحمن، أدامك الله لي سنداً وفخراً."
)
