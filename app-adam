import hashlib
import io
import os
import re
from pathlib import Path
from collections import Counter

import streamlit as st
from openai import OpenAI
from pypdf import PdfReader

# ------------------------------------------------------------
# Adam's tutor — separate application. Does not modify Toutou.
# ------------------------------------------------------------

APP_DIR = Path(__file__).parent
DOCS_DIR = APP_DIR / "documents"

COURSES = {
    "Biology 40S": {
        "folder": "biology",
        "welcome": (
            "Hi Adam! Welcome to Biology 40S. What topic are you working on today? "
            "We can review genetics, heredity, evolution, biodiversity, or a question from class."
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
"""
    },
    "English — Comprehensive Focus 40S": {
        "folder": "english",
        "welcome": (
            "Hi Adam! Welcome to English Comprehensive Focus 40S. "
            "We can work on reading, literary analysis, persuasive writing, grammar, or revision."
        ),
        "system": """
You are Adam's supportive Grade 12 English Language Arts tutor for Comprehensive Focus 40S in Manitoba.
Use English by default. If Adam is stuck, explain the strategy briefly in French, then provide an English example and invite him to try.
Comprehensive Focus gives substantial attention to both literary and transactional texts. Support reading comprehension, thesis statements, evidence and quotation integration, paragraph structure, argumentation, tone, voice, rhetorical choices, grammar, editing, and revision.
Ask what the assignment asks and what Adam has tried. Teach a repeatable process; do not invent a teacher's rubric or pretend to know an assignment's requirements unless Adam supplies them.
When documents are retrieved, prioritize them and name the source filename. If no course document is available, be clear that the advice is general.
When giving writing feedback, identify a few high-impact improvements, explain why, and offer a revised example without erasing Adam's own voice.
"""
    },
    "Cinema — Witness to Modern History 40S": {
        "folder": "cinema",
        "welcome": (
            "Hi Adam! Welcome to Cinema, Witness to Modern History 40S. "
            "Tell me which film, historical period, or assignment you are studying."
        ),
        "system": """
You are Adam's Grade 12 tutor for the Manitoba course “Le cinéma, témoin de l'histoire moderne 40S”.
Teach primarily in English, but explain difficult concepts in French if Adam requests it.
Help him analyze cinema as an art form, a historical artifact, and an interpreter of history. Focus on historical context, point of view, representation, evidence, film techniques, bias, omissions, historical thinking, and critical media literacy.
Do not treat a film as a transparent or perfectly accurate record of the past: distinguish what the film depicts from what historians can substantiate.
When retrieved official course excerpts are supplied, prioritize them and cite their source filename. Do not claim that an idea is an official course requirement unless the excerpt supports it.
For essays, guide Adam through a claim, evidence, analysis, and connection to historical context. Ask one question at a time and support his independent thinking.
"""
    },
}

st.set_page_config(page_title="Adam's Study Tutor", page_icon="🎓", layout="centered")
st.title("🎓 Adam's Study Tutor")
st.caption("Collège Louis-Riel · Grade 12 · 40S")
st.info("Use this tutor to understand your courses, practise, and prepare for assessments. Always follow your teacher's assignment instructions.")

api_key = st.secrets.get("OPENAI_API_KEY") if hasattr(st, "secrets") else None
api_key = api_key or os.environ.get("OPENAI_API_KEY")
if not api_key:
    st.error("The OpenAI API key is not configured. The app administrator must add OPENAI_API_KEY in Streamlit app Secrets.")
    st.stop()

client = OpenAI(api_key=api_key)

with st.sidebar:
    st.header("📚 Choose a course")
    course_name = st.selectbox("Active course", list(COURSES.keys()))
    st.divider()
    st.header("🎤 Voice input")
    st.caption("Record a short question. Check the transcription before relying on it.")
    audio_value = st.audio_input("Record your question")
    st.divider()
    st.caption("Course documents are retrieved from PDFs placed in this app's documents folders.")
    st.caption("Your questions are sent to the AI service to generate responses.")

course = COURSES[course_name]
folder = DOCS_DIR / course["folder"]

# Simple local retrieval over official PDFs. This is a first, transparent RAG stage:
# retrieve matching text chunks locally and pass only those excerpts to the model.
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
            # Chunk at paragraph boundaries, with a safe maximum size.
            paragraphs = [p.strip() for p in re.split(r"\n\s*\n", full_text) if p.strip()]
            current = ""
            for para in paragraphs:
                if len(current) + len(para) > 1400 and current:
                    chunks.append({"source": pdf_path.name, "text": current})
                    current = ""
                if len(para) > 1800:
                    for start in range(0, len(para), 1400):
                        piece = para[start:start + 1400]
                        if piece.strip():
                            chunks.append({"source": pdf_path.name, "text": piece})
                else:
                    current = (current + "\n\n" + para).strip()
            if current:
                chunks.append({"source": pdf_path.name, "text": current})
        except Exception:
            # One malformed PDF should not prevent the tutor from opening.
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
                # Simple substring match supports plural/suffix variations.
                if any(term in word or word in term for word in counts if len(word) >= 5):
                    score += 0.25
        if score > 0:
            scored.append((score, chunk))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _, chunk in scored[:limit]]

# Keep separate conversation histories for each course in this browser session.
if "histories_by_course" not in st.session_state:
    st.session_state.histories_by_course = {}
if course_name not in st.session_state.histories_by_course:
    st.session_state.histories_by_course[course_name] = [
        {"role": "assistant", "content": course["welcome"]}
    ]

history = st.session_state.histories_by_course[course_name]

# Handle a microphone recording once only; Streamlit reruns the script after interactions.
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
                    file=(getattr(audio_value, "name", "recording.wav"), audio_bytes,
                          getattr(audio_value, "type", None) or "audio/wav"),
                )
                st.session_state.pending_audio_text = transcript.text.strip()
                st.session_state.processed_audio_hash = audio_hash
            except Exception as exc:
                st.error(f"Voice transcription failed: {exc}")
                st.session_state.processed_audio_hash = audio_hash

for msg in history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if st.session_state.pending_audio_text:
    st.info("Voice transcription — review it, then press Send.")
    with st.form("voice_transcript_form", clear_on_submit=True):
        corrected_text = st.text_area("Your transcribed question", value=st.session_state.pending_audio_text, height=100)
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
            "The following are excerpts retrieved from local course PDFs. "
            "Use them when relevant, cite the source filename in your response, "
            "and say when they do not answer the question. Do not invent quotations.\n\n"
            + excerpts
        )
        st.caption("Course references used: " + ", ".join(sorted({item["source"] for item in relevant})))
    else:
        context_block = (
            "No relevant passage was retrieved from the local course PDFs for this question. "
            "Answer helpfully from general knowledge, but do not claim to be quoting an official course document."
        )
        if not all_chunks:
            st.caption("No course PDFs have been added for this subject yet; the tutor is currently using its course instructions and general knowledge.")

    messages_for_api = [
        {"role": "system", "content": course["system"] + "\n\n" + context_block}
    ] + history[-12:]

    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            try:
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=messages_for_api,
                    temperature=0.4,
                )
                answer = response.choices[0].message.content or "I couldn't generate an answer. Please try again."
                st.markdown(answer)
                history.append({"role": "assistant", "content": answer})
            except Exception as exc:
                st.error(f"An error occurred while generating the answer: {exc}")

    st.session_state.histories_by_course[course_name] = history

st.divider()
st.caption("Made with care by Dad ❤️ · Keep asking questions, practise, and build your own understanding.")
