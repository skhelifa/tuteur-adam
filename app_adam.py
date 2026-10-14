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
            "Hi Adam! Welcome to Biology 40S. What topic are you working on"
            " today? We can review genetics, heredity, evolution, biodiversity,"
            " or a question from class."
        ),
        "system": """
You are Adam's patient, rigorous Grade 12 Biology 40S tutor at Collège Louis-Riel in Manitoba.
Teach primarily in English. If Adam asks in French or says he is confused, explain the difficult idea in French, then return to English practice.
Use a Socratic approach: ask one manageable question at a time, give hints before full solutions, check understanding with a new example, and correct misconceptions kindly.
Relevant Manitoba Biology 12 themes include genetic transmission, mechanisms of heredity, evolution and biodiversity, organization of biodiversity, and biodiversity conservation.
When retrieved course-document excerpts are supplied, prioritize them and identify the source filename in your answer. Never claim that a statement is from an official Manitoba document unless the supplied excerpts support it.
If no relevant excerpt is supplied, answer from general biology knowledge and be transparent that you are not quoting a retrieved course document.
For homework, help Adam understand and construct his own answer; do not simply complete an assessed assignment without explanation.
Use clear headings, concise explanations, examples, and accurate scientific vocabulary.
""",
    },
    "English — Comprehensive Focus 40S": {
        "folder": "english",
        "welcome": (
            "Hi Adam! Welcome to English Comprehensive Focus 40S. We can work"
            " on reading, literary analysis, persuasive writing, grammar, or"
            " revision."
        ),
        "system": """
You are Adam's supportive Grade 12 English Language Arts tutor for Comprehensive Focus 40S in Manitoba.
Use English by default. If Adam is stuck, explain the strategy briefly in French, then provide an English example and invite him to try.
Comprehensive Focus gives substantial attention to both literary and transactional texts. Support reading comprehension, thesis statements, evidence and quotation integration, paragraph structure, argumentation, tone, voice, rhetorical choices, grammar, editing, and revision.
Ask what the assignment asks and what Adam has tried. Teach a repeatable process; do not invent a teacher's rubric or pretend to know an assignment's requirements unless Adam supplies them.
When documents are retrieved, prioritize them and name the source filename. If no course document is available, be clear that the advice is general.
When giving writing feedback, identify a few high-impact improvements, explain why, and offer a revised example without erasing Adam's own voice.
""",
    },
    "Cinema — Witness to Modern History 40S": {
        "folder": "cinema",
        "welcome": (
            "Hi Adam! Welcome to Cinema, Witness to Modern History 40S. Tell me"
            " which film, historical period, or assignment you are studying."
        ),
        "system": """
You are Adam's Grade 12 tutor for the Manitoba course “Le cinéma, témoin de l'histoire moderne 40S”.
Teach primarily in English, but explain difficult concepts in French if Adam requests it.
Help him analyze cinema as an art form, a historical artifact, and an interpreter of history. Focus on historical context, point of view, representation, evidence, film techniques, bias, omissions, historical thinking, and critical media literacy.
Do not treat a film as a transparent or perfectly accurate record of the past: distinguish what the film depicts from what historians can substantiate.
When retrieved official course excerpts are supplied, prioritize them and cite their source filename. Do not claim that an idea is an official course requirement unless the excerpt supports it.
For essays, guide Adam through a claim, evidence, analysis, and connection to historical context. Ask one question at a time and support his independent thinking.
""",
    },
}

st.set_page_config(
    page_title="Adam's Study Tutor", page_icon="🎓", layout="centered"
)
st.title("🎓 Adam's Study Tutor")
st.caption("Collège Louis-Riel · Grade 12 · 40S")
st.info(
    "Use this tutor to understand your courses, practise, and prepare for"
    " assessments. Always follow your teacher's assignment instructions."
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
        msg.lang = 'en-US';
        window.speechSynthesis.speak(msg);
    </script>
    """
    components.html(js_code, height=0)


# Gestion des états du Quiz (10 questions)
if "quiz_data" not in st.session_state:
    st.session_state.quiz_data = None
if "show_hint" not in st.session_state:
    st.session_state.show_hint = False
if "quiz_submitted" not in st.session_state:
    st.session_state.quiz_submitted = False
if "quiz_answers" not in st.session_state:
    st.session_state.quiz_answers = {}


def generate_qcm(course_title, system_prompt, chunks_text, number_questions=10):
    prompt = f"""Create a practice exam with AT LEAST {number_questions} multiple-choice questions for a Grade 12 student in this course: {course_title}.
Exam format:
- Exactly {number_questions} questions.
- Four options per question, labelled A, B, C, D.
- Exactly one correct answer per question.
- Questions should test understanding, application, and reasoning.
- Use varied difficulty, from accessible to challenging.
- Avoid duplicate questions and ambiguous wording.
- Use the course excerpts when relevant.
- If no excerpts are provided, use reliable general subject knowledge.
- Do not claim this is an official exam.
- Write the questions and options in English.
- Include a short explanation and a helpful hint for every question.

Use these course excerpts if relevant:
{chunks_text}

Return ONLY valid JSON in this exact structure:
{{
  "questions": [
    {{
      "question": "Question text",
      "options": {{
        "A": "First option",
        "B": "Second option",
        "C": "Third option",
        "D": "Fourth option"
      }},
      "correct": "A",
      "hint": "A hint that does not reveal the answer",
      "explanation": "Why the correct answer is correct"
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


with st.sidebar:
    st.header("📚 Choose a course")
    course_name = st.selectbox("Active course", list(COURSES.keys()))
    st.divider()

    st.header("🎯 Mode Examen (Quiz 10 Questions)")
    st.caption("Génère un test complet de 10 questions avec correction et score final.")
    if st.button("🎲 Générer un quiz de 10 questions"):
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
                        all_chunks_temp.append(
                            f"\n{full_text[:6000]}"
                        )
                except Exception:
                    continue
        chunks_text = "\n\n".join(all_chunks_temp[:3])
        with st.spinner("Preparing Adam's 10-question practice exam..."):
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
    st.header("🔊 Audio Output")
    enable_voice_output = st.checkbox("Lecture vocale automatique", value=True)
    st.divider()

    st.header("🎤 Voice input")
    audio_value = st.audio_input("Record your question")

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
        with st.spinner("Transcribing your recording…"):
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
                st.error(f"Voice transcription failed: {exc}")
                st.session_state.processed_audio_hash = audio_hash


# --- DISPLAY THE FULL MULTIPLE-CHOICE EXAM ---
if st.session_state.quiz_data:
    questions = st.session_state.quiz_data.get("questions", [])
    total = len(questions)
    st.divider()
    st.subheader(f"🎯 Practice Exam — {course_name}")
    st.write(f"**{total} questions** · One correct answer per question")

    if not st.session_state.quiz_submitted:
        with st.form("qcm_exam_form"):
            user_answers = {}
            for i, item in enumerate(questions):
                st.markdown(f"### Question {i + 1} of {total}")
                st.write(item["question"])
                option_labels = [
                    f"{letter}. {item['options'][letter]}"
                    for letter in ("A", "B", "C", "D")
                ]
                choice = st.radio(
                    "Choose one answer:",
                    option_labels,
                    index=None,
                    key=f"quiz_answer_{i}",
                )
                user_answers[i] = choice
                with st.expander("💡 Need a hint?"):
                    st.write(item.get("hint", "No hint available."))
                st.divider()

            submitted = st.form_submit_button(
                "✅ Submit exam and see my score",
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

        if st.button("🔄 Recommencer un nouveau quiz"):
            st.session_state.quiz_data = None
            st.session_state.quiz_submitted = False
            st.session_state.quiz_answers = {}
            st.rerun()

    st.divider()


# Affichage de l'historique du chat normal
for msg in history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if st.session_state.pending_audio_text:
    st.info("Voice transcription — review it, then press Send.")
    with st.form("voice_transcript_form", clear_on_submit=True):
        corrected_text = st.text_area(
            "Your transcribed question",
            value=st.session_state.pending_audio_text,
            height=100,
        )
        submitted_voice = st.form_submit_button("Send question")
    if submitted_voice and corrected_text.strip():
        st.session_state.pending_audio_text = None
        st.session_state.next_question = corrected_text.strip()
        st.rerun()

typed_question = st.chat_input("Ask a question in English or French…")
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
            "The following are excerpts retrieved from local course PDFs. Use them"
            " when relevant, cite the source filename in your response, and say"
            " when they do not answer the question. Do not invent quotations.\n\n"
            + excerpts
        )
        st.caption(
            "Course references used: "
            + ", ".join(sorted({item["source"] for item in relevant}))
        )
    else:
        context_block = (
            "No relevant passage was retrieved from the local course PDFs for this"
            " question. Answer helpfully from general knowledge, but do not claim"
            " to be quoting an official course document."
        )
        if not all_chunks:
            st.caption(
                "No course PDFs have been added for this subject yet; the tutor is"
                " currently using its course instructions and general knowledge."
            )

    messages_for_api = [{
        "role": "system",
        "content": course["system"] + "\n\n" + context_block,
    }] + history[-12:]

    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            try:
                response = client.chat.completions.create(
                    model="gpt-4o-mini", messages=messages_for_api, temperature=0.4
                )
                answer = (
                    response.choices[0].message.content
                    or "I couldn't generate an answer. Please try again."
                )
                st.markdown(answer)
                history.append({"role": "assistant", "content": answer})

                if enable_voice_output:
                    speak_text(answer)

            except Exception as exc:
                st.error(f"An error occurred while generating the answer: {exc}")

    st.session_state.histories_by_course[course_name] = history

st.divider()
st.caption(
    "Made with care by Dad ❤️ · Keep asking questions, practise, and build"
    " your own understanding."
)
st.caption(
    "إلى ابني الحبيب، ضوء عيني ونبض قلبي ادم .. وجودك في حياتي هو أجمل عطايا"
    " الرحمن، أدامك الله لي سنداً وفخراً."
)
