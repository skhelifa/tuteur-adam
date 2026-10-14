from collections import Counter
import hashlib
import io
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


# Gestion des états du Quiz / QCM
if "quiz_data" not in st.session_state:
  st.session_state.quiz_data = None
if "show_hint" not in st.session_state:
  st.session_state.show_hint = False
if "quiz_answered" not in st.session_state:
  st.session_state.quiz_answered = False


def generate_qcm(course_title, system_prompt, chunks_text):
  prompt = f"""
    As an expert tutor for the course: {course_title}, generate ONE multiple-choice question (QCM) with 4 options (A, B, C, D) suitable for Grade 12.
    Use these course excerpts if relevant:
    {chunks_text}
    
    You MUST format your response strictly using these tags:
    QUESTION: [The question text]
    A: [Option A]
    B: [Option B]
    C: [Option C]
    D: [Option D]
    CORRECT: [A, B, C, or D]
    HINT: [A helpful Socratic hint that guides without revealing the answer]
    EXPLANATION: [A brief explanation of why the correct answer is right]
    """
  try:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
    )
    return response.choices[0].message.content
  except Exception as exc:
    return None


def parse_qcm(text):
  lines = text.split("\n")
  q, a, b, c, d, correct, hint, explanation = "", "", "", "", "", "", "", ""
  for line in lines:
    if line.startswith("QUESTION:"):
      q = line.replace("QUESTION:", "").strip()
    elif line.startswith("A:"):
      a = line.replace("A:", "").strip()
    elif line.startswith("B:"):
      b = line.replace("B:", "").strip()
    elif line.startswith("C:"):
      c = line.replace("C:", "").strip()
    elif line.startswith("D:"):
      d = line.replace("D:", "").strip()
    elif line.startswith("CORRECT:"):
      correct = line.replace("CORRECT:", "").strip()
    elif line.startswith("HINT:"):
      hint = line.replace("HINT:", "").strip()
    elif line.startswith("EXPLANATION:"):
      explanation = line.replace("EXPLANATION:", "").strip()
  return q, [a, b, c, d], correct, hint, explanation


with st.sidebar:
  st.header("📚 Choose a course")
  course_name = st.selectbox("Active course", list(COURSES.keys()))
  st.divider()

  st.header("🎯 Mode Quiz & QCM")
  st.caption("Teste tes connaissances avec un QCM interactif.")
  if st.button("🎲 Générer un QCM"):
    st.session_state.show_hint = False
    st.session_state.quiz_answered = False
    folder_path = DOCS_DIR / COURSES[course_name]["folder"]
    all_chunks_temp = []
    if folder_path.exists():
      for pdf_path in sorted(folder_path.glob("*.pdf")):
        try:
          reader = PdfReader(str(pdf_path))
          full_text = "\n".join(
              (page.extract_text() or "") for page in reader.pages
          )
          all_chunks_temp.append(full_text[:2000])
        except:
          pass
    chunks_text = "\n".join(all_chunks_temp[:2])
    raw_qcm = generate_qcm(
        course_name, COURSES[course_name]["system"], chunks_text
    )
    if raw_qcm:
      st.session_state.quiz_data = parse_qcm(raw_qcm)
    else:
      st.error("Impossible de générer le QCM pour l'instant.")

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
      "the",
      "and",
      "for",
      "with",
      "that",
      "this",
      "from",
      "what",
      "when",
      "where",
      "which",
      "how",
      "why",
      "are",
      "was",
      "were",
      "have",
      "has",
      "does",
      "did",
      "can",
      "could",
      "would",
      "should",
      "into",
      "about",
      "les",
      "des",
      "une",
      "dans",
      "pour",
      "avec",
      "est",
      "que",
      "qui",
      "quoi",
      "comment",
      "pourquoi",
      "sur",
      "par",
      "aux",
      "du",
      "de",
      "la",
      "le",
      "un",
      "et",
      "en",
      "je",
      "tu",
      "il",
      "elle",
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

# --- AFFICHAGE DU QUIZ ACTIF ---
if st.session_state.quiz_data:
  q_text, options, correct_ans, hint_text, explanation_text = (
      st.session_state.quiz_data
  )
  if q_text:
    with st.container():
      st.markdown(f"### 🎯 Quiz — {course_name}")
      st.info(f"**Question :** {q_text}")

      with st.form("qcm_form"):
        choice = st.radio("Choisis une réponse :", options, index=None)
        submitted_qcm = st.form_submit_button("Valider ma réponse")

      if submitted_qcm:
        if choice:
          selected_letter = choice[0].upper()
          if selected_letter == correct_ans.upper():
            st.success(f"✅ Correct ! {explanation_text}")
          else:
