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

# -----------------------------------------------------------------------------
# DSFMGPT / Hub — Écosystème Pédagogique Souverain DSFM / BEF Manitoba
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
Tu es le tuteur d'Adam pour le cours de Biologie 40S (12e année) au Collège Louis-Riel au Manitoba (normes DSFM et BEF).
APPROCHE SOCRATIQUE OBLIGATOIRE : Enseigne en FRANÇAIS. Ne donne jamais de réponses directes toutes faites.
Pose UNE SEULE question claire à la fois, utilise des indices gradués, stimule le raisonnement et valide chaque étape.
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
Tu es le tuteur d'Adam pour le cours « Le cinéma, témoin de l'histoire moderne 40S » (DSFM).
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
            "POSTURE TEMPÊTE & BLIZZARD (DSFM) : Adopte un ton particulièrement chaleureux, dynamique et bienveillant. "
            "Maintiens une immersion orale et écrite soutenue en français pour briser l'isolement de l'élève à la maison et préserver le bain linguistique."
        ),
        "temp": 0.5,
    },
    "⏱️ Examen Provincial 40S (Simulation BEF)": {
        "prompt": (
            "POSTURE EXAMINATEUR PROVINCIAL BEF : Évalue formellement selon les grilles ministérielles de 12e année. "
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

# Configuration Streamlit
st.set_page_config(
    page_title="DSFMGPT — Écosystème Pédagogique Souverain",
    page_icon="🎓",
    layout="wide"
)

api_key = st.secrets.get("OPENAI_API_KEY") if hasattr(st, "secrets") else None
api_key = api_key or os.environ.get("OPENAI_API_KEY")
if not api_key:
    st.error("Clé API OpenAI non configurée. Ajoutez OPENAI_API_KEY dans vos Secrets Streamlit.")
    st.stop()

client = OpenAI(api_key=api_key)


# Fonctions d'illustration Souveraine (DALL-E Grounded)
def generer_image_souveraine(contexte_texte: str, focus_visuel: str):
    try:
        distill_prompt = f"""Tu es un conseiller en design pédagogique et illustrateur scientifique pour la DSFM.
Conçois un prompt descriptif pour une illustration éducative de 12e année basée sur les données locales ci-dessous.
Évite le texte complexe, les mots flous ou mal orthographiés (privilégie des symboles clairs et un schéma épuré).

Sujet : {focus_visuel}
Données contextuelles locales : {contexte_texte}

Décris une illustration scientifique détaillée (schéma, diagramme ou dessin réaliste), pédagogique, sur fond sobre."""
        
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
        st.error(f"Erreur lors de la génération de l'image : {exc}")
        return None


# Synthèse Vocale Web
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
    components.html("<script>window.speechSynthesis.cancel();</script>", height=0)


# Variables d'état de session
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


# Générateur de QCM au format JSON strict
def generate_qcm_from_context(course_title, system_prompt, discussion_context, number_questions=10):
    prompt = f"""En te basant sur la discussion récente et le cours : {course_title}, crée un quiz d'entraînement de {number_questions} questions à choix multiples (QCM) en français.
Contexte récent :
{discussion_context}

Format strict :
- Exactement {number_questions} questions (A, B, C, D).
- Une seule réponse correcte.
- Un indice pédagogique et une explication par question.

Renvoie UNIQUEMENT un objet JSON valide :
{{
  "questions": [
    {{
      "question": "Texte",
      "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
      "correct": "A",
      "hint": "Indice",
      "explanation": "Explication"
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
            return json.loads(match.group(0))
        return None
    except Exception as e:
        print(f"Erreur JSON : {e}")
        return None


# Moteur RAG local (PDF Officiels BEF + Documents Personnels Enseignant)
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
            prefix = "[Ressource Enseignant]" if is_custom else "[Programme BEF Officiel]"
            
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
                if any(term in word or word in term for word in counts if len(word) >= 5):
                    score += 0.25
        if score > 0:
            scored.append((score, chunk))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _, chunk in scored[:limit]]


# --- BARRE LATÉRALE DE CONTRÔLE ---
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/school.png", width=64)
    st.title("DSFMGPT Hub")
    st.caption("Cadre d'IA Souverain · DSFM / BEF Manitoba")
    
    navigation_espace = st.radio(
        "Sélectionnez l'espace :",
        [
            "🎓 Espace Élève (Tuteur Socratique)",
            "👩‍🏫 Espace Enseignant & Auxiliaire (BEF / EA)",
            "👨‍👩‍👦 Espace Parents et Tuteurs légaux",
            "🏢 Espace Direction, Admin & Impact (Module 3)"
        ]
    )
    
    st.markdown("---")
    st.markdown("### 📚 Cours Actif")
    course_name = st.selectbox("Matière", list(COURSES.keys()))
    course = COURSES[course_name]
    folder = DOCS_DIR / course["folder"]

    st.markdown("---")
    st.markdown("### 🎛️ Mode Contextuel")
    mode_selectionne = st.selectbox("Posture pédagogique", list(CONTEXT_MODES.keys()))
    mode_info = CONTEXT_MODES[mode_selectionne]

    st.markdown("---")
    st.markdown("### 🔊 Audio & Voix")
    enable_voice_output = st.checkbox("Lecture vocale automatique", value=True)
    if st.button("🛑 Couper la voix", use_container_width=True):
        stop_speech()
        st.success("Voix coupée.")
    
    audio_value = st.audio_input("Dictée vocale (Whisper)")


# =============================================================================
# ESPACE 1 : ÉLÈVE & TUTEUR SOCRATIQUE
# =============================================================================
if "Élève" in navigation_espace:
    st.title(f"🎓 Tuteur Socratique — {course_name}")
    st.info(f"Posture active : **{mode_selectionne}**")

    if course_name not in st.session_state.histories_by_course:
        st.session_state.histories_by_course[course_name] = [{
            "role": "assistant",
            "content": course["welcome"],
        }]
    history = st.session_state.histories_by_course[course_name]

    if audio_value is not None:
        audio_bytes = audio_value.getvalue()
        audio_hash = hashlib.sha256(audio_bytes).hexdigest()
        if audio_hash != st.session_state.processed_audio_hash:
            with st.spinner("Transcription de votre voix en cours…"):
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
                    st.error(f"Erreur transcription vocale : {exc}")
                    st.session_state.processed_audio_hash = audio_hash

    for idx, msg in enumerate(history):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg["role"] == "assistant" and idx == len(history) - 1 and enable_voice_output:
                speak_text(msg["content"])

        if msg["role"] == "assistant" and idx == len(history) - 1:
            st.markdown("💡 **Suggestions rapides d'étayage :**")
            col1, col2, col3, col4 = st.columns(4)
            btn_query = None
            with col1:
                if st.button("📖 Expliquer simplement", key=f"s1_{idx}", use_container_width=True):
                    btn_query = "Peux-tu m'expliquer cette notion plus simplement avec une analogie visuelle en français ?"
            with col2:
                if st.button("📝 Exemple concret", key=f"s2_{idx}", use_container_width=True):
                    btn_query = "Donne-moi un exemple concret issu du quotidien manitobain ou de notre cours."
            with col3:
                if st.button("🎥 Vidéo YouTube", key=f"s3_{idx}", use_container_width=True):
                    btn_query = "Propose-moi un lien de recherche YouTube cliquable pour visualiser ce concept."
            with col4:
                if st.button("🚀 Approfondir", key=f"s4_{idx}", use_container_width=True):
                    btn_query = "Comment relier ce concept à un défi scientifique plus avancé ou universitaire ?"

            if btn_query:
                st.session_state.next_question = btn_query
                st.rerun()

            st.markdown("")
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                quiz_btn = st.button("🎯 🎲 Générer un quiz de 10 questions sur notre discussion", key=f"quiz_btn_{idx}", use_container_width=True)
            with col_b2:
                image_btn = st.button("🎨 🖼️ Illustrer cette notion (RAG Souverain)", key=f"img_btn_{idx}", use_container_width=True)

            if quiz_btn:
                with st.spinner("Conception du quiz formatif personnalisé…"):
                    recent_discussion = "\n".join([f"{m['role']}: {m['content']}" for m in history[-6:]])
                    quiz = generate_qcm_from_context(
                        course_name,
                        course["system"] + "\n" + mode_info["prompt"],
                        recent_discussion,
                        number_questions=10,
                    )
                if quiz and "questions" in quiz:
                    st.session_state.quiz_data = quiz
                    st.session_state.quiz_submitted = False
                    st.rerun()
                else:
                    st.error("Génération du quiz momentanément indisponible.")
            
            if image_btn:
                with st.spinner("Création de l'illustration scientifique sur mesure…"):
                    recent_discussion = "\n".join([f"{m['role']}: {m['content']}" for m in history[-4:]])
                    all_chunks = load_pdf_chunks(str(folder))
                    relevant_chunks = retrieve_chunks(recent_discussion, all_chunks)
                    chunks_text = "\n\n".join(c["text"] for c in relevant_chunks) if relevant_chunks else "Données générales du cours."
                    
                    img_url = generer_image_souveraine(chunks_text, recent_discussion)
                    if img_url:
                        st.image(img_url, caption="Schéma illustratif basé sur votre leçon souveraine (FIPPA Compliant)")
                    else:
                        st.error("Impossible de concevoir l'illustration pour le moment.")

    # Affichage du Quiz ACTIF
    if st.session_state.quiz_data:
        questions = st.session_state.quiz_data.get("questions", [])
        total = len(questions)
        st.divider()
        st.subheader(f"🎯 Quiz d'entraînement formatif — {course_name}")
        st.write(f"**{total} questions** · Adapté à votre échange actuel")

        if not st.session_state.quiz_submitted:
            with st.form("qcm_exam_form"):
                user_answers = {}
                for i, item in enumerate(questions):
                    st.markdown(f"**Question {i + 1} sur {total} :** {item['question']}")
                    labels = [f"{L}. {item['options'][L]}" for L in ("A", "B", "C", "D")]
                    choice = st.radio(
                        "Votre réponse :",
                        labels,
                        index=None,
                        key=f"q_ans_{i}",
                    )
                    user_answers[i] = choice
                    with st.expander("💡 Indice d'étayage"):
                        st.write(item.get("hint", "Pas d'indice particulier."))
                    st.divider()

                submitted = st.form_submit_button("✅ Soumettre le quiz et obtenir l'analyse", type="primary")

            if submitted:
                st.session_state.quiz_answers = user_answers
                st.session_state.quiz_submitted = True
                st.rerun()

        else:
            score = 0
            user_answers = st.session_state.quiz_answers
            st.markdown("### 📊 Analyse détaillée des résultats :")
            for i, item in enumerate(questions):
                ans = user_answers.get(i)
                correct_letter = item["correct"].upper()
                st.markdown(f"**Q{i + 1} : {item['question']}**")

                if ans:
                    selected_letter = ans[0].upper()
                    if selected_letter == correct_letter:
                        score += 1
                        st.success(f"✅ Exact ! Votre choix : {ans}\n\n*{item['explanation']}*")
                    else:
                        st.error(f"❌ À revoir. Votre choix : {ans} | Bonne réponse : **{correct_letter}. {item['options'].get(correct_letter, '')}**\n\n*{item['explanation']}*")
                else:
                    st.warning(f"⚠️ Non répondu. Réponse attendue : **{correct_letter}. {item['options'].get(correct_letter, '')}**\n\n*{item['explanation']}*")
                st.markdown("---")

            pct = (score / total) * 100 if total > 0 else 0
            st.markdown(f"## 🏆 Score obtenu : {score} / {total} ({pct:.0f}%)")
            if score >= 8:
                st.balloons()
                st.success("🎉 Excellente maîtrise des résultats d'apprentissage ciblés !")
            elif score >= 5:
                st.info("👍 Bon niveau de base. Poursuivez les échanges socratiques pour consolider.")
            else:
                st.warning("💡 Prenez le temps de revoir les concepts clés avec le tuteur.")

            if st.button("🔄 Fermer le quiz et reprendre la discussion"):
                st.session_state.quiz_data = None
                st.session_state.quiz_submitted = False
                st.session_state.quiz_answers = {}
                st.rerun()

        st.divider()

    if st.session_state.pending_audio_text:
        st.info("Transcription vocale prête — Validez ou ajustez le texte avant l'envoi :")
        with st.form("transcript_form", clear_on_submit=True):
            corrected_text = st.text_area("Texte transcrit :", value=st.session_state.pending_audio_text, height=90)
            if st.form_submit_button("Envoyer la question"):
                st.session_state.pending_audio_text = None
                st.session_state.next_question = corrected_text.strip()
                st.rerun()

    typed_q = st.chat_input("Posez votre question en français...")
    active_question = typed_q or st.session_state.pop("next_question", None)

    if active_question and active_question.strip():
        active_question = active_question.strip()
        history.append({"role": "user", "content": active_question})
        with st.chat_message("user"):
            st.markdown(active_question)

        all_chunks = load_pdf_chunks(str(folder))
        relevant_chunks = retrieve_chunks(active_question, all_chunks)
        if relevant_chunks:
            excerpts = "\n\n".join(f"[{c['source']}]\n{c['text']}" for c in relevant_chunks)
            context_block = (
                "Extraits officiels extraits des documents locaux (Curriculum BEF & Notes de l'enseignant) :\n\n"
                + excerpts
                + "\n\nConsigne : Utilise prioritairement ces sources, mentionne leur origine et respecte l'esprit du programme."
            )
            st.caption("Documents sources mobilisés : " + ", ".join(sorted({c["source"] for c in relevant_chunks})))
        else:
            context_block = "Aucun passage spécifique n'a été extrait des PDF locaux. Réponds selon les normes curriculaires manitobaines."

        api_history = [m for m in history if not (m["role"] == "assistant" and m["content"] == course["welcome"])]
        system_instructions = (
            f"{course['system']}\n\n{mode_info['prompt']}\n\n{context_block}\n\n"
            "RAPPEL CARDINAL : Réponds TOUJOURS en français. Pose UNE SEULE question socratique à la fois. Encourage l'élève."
        )

        with st.chat_message("assistant"):
            with st.spinner("Réflexion socratique…"):
                try:
                    res = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "system", "content": system_instructions}] + api_history[-10:],
                        temperature=mode_info["temp"],
                    )
                    assistant_answer = res.choices[0].message.content
                    st.markdown(assistant_answer)
                    history.append({"role": "assistant", "content": assistant_answer})
                    if enable_voice_output:
                        speak_text(assistant_answer)
                except Exception as err:
                    st.error(f"Erreur lors de la génération de la réponse : {err}")

        st.session_state.histories_by_course[course_name] = history
        st.rerun()


# =============================================================================
# ESPACE 2 : ENSEIGNANT BEF & AUXILIAIRE (EA)
# =============================================================================
elif "Enseignant" in navigation_espace:
    st.title("👩‍🏫 Espace Pédagogique — Conception Curriculaire & Inclusion")
    st.caption("Conforme aux directives du BEF, à la Conception Universelle de l'Apprentissage (CUA) et aux lois FIPPA")

    tab_bef, tab_eval, tab_ea, tab_notebook, tab_video = st.tabs([
        "📋 Planification Différenciée (BEF / PAT / Défi)",
        "📊 Évaluation Formative & par les Pairs",
        "🤝 Coordination Auxiliaire (EA)",
        "📚 Mon Classeur (Esprit NotebookLM)",
        "🎬 Studio Capsule Dialoguée (Continuité Blizzard)"
    ])

    with tab_bef:
        st.subheader("Générateur de Leçon Curriculaire Trifide")
        st.write("Conçoit simultanément le socle commun, les adaptations PAT et les pistes d'enrichissement pour élèves avancés.")
        
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            ras_input = st.text_input("Code RAS BEF ou Résultat d'apprentissage :", value="B12-2-03 (Lois de Mendel)")
            sujet_lecon = st.text_input("Sujet de la leçon :", value="Monohybridisme et grilles de Punnett")
        with col_t2:
            profil_pat = st.text_area("Besoins particuliers identifiés (PAT / Dyslexie / Francisation) :", 
                                      value="2 élèves en PAT (besoin de textes aérés et d'étayage visuel) ; 1 élève en francisation récente.")
            profil_avance = st.text_area("Besoins d'enrichissement (Élèves avancés / Douance) :", 
                                         value="3 élèves très rapides ayant déjà maîtrisé les calculs de probabilités simples.")

        col_btn1, col_btn2 = st.columns([1, 1])
        with col_btn1:
            l_btn = st.button("🚀 Générer la leçon multiniveau complète", type="primary", use_container_width=True)
        with col_btn2:
            img_btn_t = st.button("🖼️ Générer une illustration pédagogique souveraine", use_container_width=True)

        if l_btn:
            with st.spinner("Génération du plan pédagogique CUA…"):
                p_prompt = (
                    "Tu es un conseiller pédagogique expert du Bureau de l'éducation française (BEF) au Manitoba.\n"
                    f"Crée un plan de leçon rigoureux, complet et structuré pour le cours : {course_name}.\n"
                    f"- Résultat d'apprentissage : {ras_input}\n"
                    f"- Sujet : {sujet_lecon}\n"
                    f"- Adaptations PAT : {profil_pat}\n"
                    f"- Élèves avancés : {profil_avance}\n\n"
                    "Structure obligatoire du document :\n"
                    "1. 🎯 Objectifs ministériels et critères de réussite observables (BEF).\n"
                    "2. 📖 Déroulement de classe (Amorce 10 min, Enseignement explicite 15 min, Pratique guidée 25 min, Objectivation 10 min).\n"
                    "3. ♿ Volet Adaptations & PAT (Aménagements matériels, consignes découpées, réduction de la charge cognitive sans baisse d'exigence).\n"
                    "4. 🚀 Volet Enrichissement & Défi (Tâches à haut niveau taxonomique de Bloom, problèmes ouverts, liens de recherche pour élèves avancés).\n"
                    "5. 💡 Grille de 3 questions socratiques clés pour le bilan.\n"
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
                les_data = st.session_state.current_lesson_plan or f"Lesson plan: {sujet_lecon}. Adap: {profil_pat}."
                img_url_t = generer_image_souveraine(les_data, f"Schema of {sujet_lecon}")
                if img_url_t:
                    st.image(img_url_t, caption="Illustration générée à partir des ressources locales.")
                else:
                    st.error("Le rendu visuel a échoué.")

    with tab_eval:
        st.subheader("📊 Conception d'Évaluations Formatives & par les Pairs (Normes BEF)")
        st.caption("Axé sur l'évaluation formative continue et l'appréciation constructive entre élèves (sans stress de notation sommatif).")

        type_eval = st.radio(
            "Outil d'évaluation souhaité :",
            [
                "🎟️ Billet de Sortie Flash (Exit Ticket 3 minutes)",
                "👥 Grille d'Évaluation par les Pairs (Deux étoiles et un souhait)",
                "🎯 Sonde Diagnostique Rapide (Vérification de compréhension mi-parcours)"
            ],
            horizontal=True
        )

        col_ev1, col_ev2 = st.columns(2)
        with col_ev1:
            sujet_eval = st.text_input("Notion ou tâche ciblée :", value="L'analyse des arguments persuasifs et des sophismes")
            niveau_classe = st.selectbox("Niveau scolaire :", ["Secondaire 4 (12e année - 40S)", "Secondaire 3 (11e année - 30S)", "Secondaire 1 & 2 (9e/10e)"])
        with col_ev2:
            objectifs_observables = st.text_area(
                "Critères ou compétences observables clés (BEF) :",
                value="Repérer un argument fallacieux, expliquer son impact sur le public cible, suggérer une alternative valide."
            )

        col_ev_btn1, col_ev_btn2 = st.columns(2)
        with col_ev_btn1:
            go_eval_btn = st.button("✨ Générer l'outil d'évaluation formative", type="primary", use_container_width=True)
        with col_ev_btn2:
            img_eval_btn = st.button("🎨 Générer l'illustration de l'évaluation", use_container_width=True)

        if go_eval_btn:
            with st.spinner("Conception de l'instrument d'évaluation formateur…"):
                eval_prompt = f"""Tu es un conseiller pédagogique expert en mesure et évaluation au Bureau de l'éducation française (BEF) du Manitoba.
Conçois un instrument d'évaluation rigoureux, formatif et bienveillant.

Type d'outil demandé : {type_eval}
Matière : {course_name}
Niveau : {niveau_classe}
Notion / Tâche : {sujet_eval}
Critères observables : {objectifs_observables}

DIRECTIVES :
1. Si 'Billet de Sortie' : 3 questions (1 notion comprise, 1 doute, 1 application).
2. Si 'Par les Pairs' : 'Deux étoiles' (réussites) et 'Un souhait' (piste). Grille à 4 niveaux d'acquisition.
3. Si 'Sonde' : 3 QCM avec pièges typiques.
"""
                resp_eval = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": eval_prompt}],
                    temperature=0.3
                )
                st.session_state.current_eval_data = resp_eval.choices[0].message.content

        if st.session_state.current_eval_data:
            st.markdown(st.session_state.current_eval_data)

        if img_eval_btn:
            with st.spinner("Création de l'illustration pour l'évaluation..."):
                eval_data = st.session_state.current_eval_data or f"{type_eval}: {sujet_eval}"
                img_url_ev = generer_image_souveraine(eval_data, f"Visual asset for {sujet_eval}")
                if img_url_ev:
                    st.image(img_url_ev, caption="Visuel d'accompagnement de l'évaluation.")
                else:
                    st.error("Le rendu a échoué.")

    with tab_ea:
        st.subheader("Coordination avec l'Auxiliaire d'Enseignement (EA Daily Briefing)")
        st.write("Produit une feuille de route claire pour l'auxiliaire afin d'accompagner un élève sous PAT sans faire le devoir à sa place.")
        
        contenu_cours = st.text_area("Résumé de la leçon du jour ou extrait du cours :", 
                                     value="Exercices d'application sur les croisements génétiques et calculs de ratios phénotypiques (3:1).",
                                     height=100)
        
        if st.button("📋 Générer la fiche de mission pour l'auxiliaire"):
            with st.spinner("Rédaction de la fiche de mission EA…"):
                ea_prompt = f"""Tu es un spécialiste de l'inclusion scolaire au Manitoba.
Rédige une fiche de mission minute destinée à un auxiliaire d'enseignement (Educational Assistant) accompagnant un élève sous PAT.
Leçon du jour : {contenu_cours}

Structure :
1. Rôle de l'auxiliaire (magistral vs individuel).
2. Questionnement socratique : 3 questions en cas de blocage.
3. Vigilances (ne pas faire à la place, fatigue).
4. Mini-grille d'observation en 3 critères.
"""
                resp_ea = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": ea_prompt}],
                    temperature=0.3
                )
                st.markdown(resp_ea.choices[0].message.content)

    with tab_notebook:
        st.subheader("Mon Espace Documents : Enrichissement (NotebookLM Souverain)")
        st.caption("Déposez vos propres notes de cours, devoirs types ou manuels. Ils sont indexés localement pour vos élèves.")
        
        custom_folder = DOCS_DIR / course["folder"] / "custom_teacher"
        custom_folder.mkdir(parents=True, exist_ok=True)
        
        uploaded_files = st.file_uploader("Ajouter des fichiers PDF personnels pour ce cours", type=["pdf"], accept_multiple_files=True)
        if uploaded_files:
            for f in uploaded_files:
                target_file = custom_folder / f.name
                with open(target_file, "wb") as buffer:
                    buffer.write(f.getbuffer())
            st.success(f"✅ {len(uploaded_files)} ressource(s) ajoutée(s) et indexée(s) !")
            st.cache_data.clear()

        existing_custom = list(custom_folder.glob("*.pdf"))
        if existing_custom:
            st.markdown("#### Fichiers personnels actuellement actifs :")
            for doc in existing_custom:
                st.write(f"📄 `{doc.name}`")

    with tab_video:
        st.subheader("🎬 Studio Capsule Dialoguée Élève-Professeur (Continuité Blizzard)")
        st.write("Génère un script scénarisé interactif entre un élève virtuel et le professeur, prêt pour le clonage vocal.")
        
        notion_cle = st.text_input("Notion clé à scénariser :", value="La différence entre allèle dominant et allèle récessif")
        if st.button("🎥 Générer le script du dialogue vidéo"):
            with st.spinner("Scénarisation de la capsule…"):
                vid_prompt = f"""Rédige un script de dialogue de 2 minutes entre un élève (hésitant) et son enseignant (bienveillant) pour la DSFM.
Matière : {course_name}
Notion : {notion_cle}

Format : [Élève] / [Enseignant] + [Visuel suggéré].
"""
                resp_vid = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": vid_prompt}],
                    temperature=0.6
                )
                st.markdown(resp_vid.choices[0].message.content)


# =============================================================================
# ESPACE 3 : PARENTS ET TUTEURS LÉGAUX
# =============================================================================
elif "Parents" in navigation_espace:
    st.title("👨‍👩‍👦 Espace Parents, Tutrices et Tuteurs Légaux")
    st.caption("Suivi du cheminement, projets collaboratifs et liaison école-foyer (Conformité FIPPA & Loi sur les écoles publiques)")

    tab_suivi, tab_binome, tab_liaison = st.tabs([
        "📊 Métriques d'Effort & Autonomie",
        "🤝 Projets en Binôme (Esprit TeamSnap)",
        "📬 Liaison École-Maison"
    ])

    with tab_suivi:
        st.subheader("Indicateurs d'activité de la semaine")
        c1, c2, c3 = st.columns(3)
        c1.metric("Sessions d'étude avec le tuteur", "4", "+1 vs sem. passée")
        c2.metric("Quiz complétés", "3", "Moyenne : 83%")
        c3.metric("Notion approfondie", "Génétique 40S", "Solide")
        
        st.markdown("#### Dernières validations d'apprentissage :")
        st.write("• **Biologie 40S** : 9/10 au quiz formatif (1 indice socratique utilisé).")
        st.write("• **Anglais 40S** : Structuration de texte argumentatif complétée avec succès.")

    with tab_binome:
        st.subheader("Coordination des travaux d'équipe & Binômes")
        st.info("🔒 La participation à un groupe de travail nécessite le consentement explicite du parent ou tuteur légal de chaque participant.")
        
        with st.expander("🔬 Laboratoire d'hérédité mendélienne — Binôme avec Marc L.", expanded=True):
            st.write("**Échéance divisionnaire :** Vendredi 30 octobre")
            st.progress(70, text="Progression du dossier : 70%")
            st.checkbox("Étape 1 : Hypothèses et protocoles de recherche (Validé)", value=True, disabled=True)
            st.checkbox("Étape 2 : Recueil des données de croisement (Validé)", value=True, disabled=True)
            st.checkbox("Étape 3 : Révision finale avec le tuteur socratique", value=False)
            st.write("📍 **Coordination logistique :** Séance de révision partagée prévue à la bibliothèque le mercredi à 16 h 30.")

    with tab_liaison:
        st.subheader("Synthèse hebdomadaire transmise au foyer")
        st.success(
            "💡 **Note pédagogique de l'équipe :** Adam fait preuve d'une excellente assiduité dans ses démarches socratiques. "
            "Il formule ses questions avec clarté en français. Encouragez-le à continuer ses sessions régulières !"
        )


# =============================================================================
# ESPACE 4 : DIRECTION & IMPACT DIVISIONNAIRE (MODULE 3)
# =============================================================================
elif "Direction" in navigation_espace or "Admin" in navigation_espace:
    st.title("🏢 Espace Direction, Admin & Impact — DSFMGPT")
    st.caption("Mesure du soulagement de la tâche de travail (MTS) et efficacité divisionnaire (FIPPA Secured)")

    st.markdown("### 🎛️ Paramétrez votre établissement :")
    col_param1, col_param2, col_param3 = st.columns(3)
    with col_param1:
        nb_profs = st.slider("Nombre d'enseignants dans l'école :", min_value=5, max_value=60, value=25, step=1)
        lecons_semaine = st.slider("Plans de leçons différenciées générés / prof / sem. :", 1, 10, 3)
    with col_param2:
        nb_ea = st.slider("Nombre d'auxiliaires d'enseignement (EA) :", min_value=1, max_value=20, value=6, step=1)
        nb_suppleances = st.slider("Journées de suppléance par mois :", 2, 40, 12)
    with col_param3:
        nb_eleves = st.slider("Élèves utilisant le tuteur socratique :", 20, 500, 150, step=10)
        sessions_eleve_sem = st.slider("Sessions de tutorat par élève / sem. :", 1, 7, 3)

    GAIN_LECON_DIFF = 45      # min économisées par plan complet BEF/PAT/Défi
    GAIN_EVAL_FORMA = 50      # min économisées par évaluation
    GAIN_EA_JOUR = 25         # min gagnées/jour par EA (briefing minute + bilan)
    GAIN_SUPPLEANCE_JOUR = 40 # min gagnées/journée de suppléance
    GAIN_ELEVE_SESSION = 30   # min d'étude efficace gagnée sans blocage

    gain_profs_heures_sem = (nb_profs * lecons_semaine * (GAIN_LECON_DIFF + GAIN_EVAL_FORMA)) / 60
    gain_ea_heures_sem = (nb_ea * 5 * GAIN_EA_JOUR) / 60
    gain_suppleance_heures_mois = (nb_suppleances * GAIN_SUPPLEANCE_JOUR) / 60
    gain_eleves_heures_sem = (nb_eleves * sessions_eleve_sem * GAIN_ELEVE_SESSION) / 60

    total_personnel_heures_mois = (gain_profs_heures_sem * 4) + (gain_ea_heures_sem * 4) + gain_suppleance_heures_mois
    total_jours_recupere_mois = total_personnel_heures_mois / 7.5

    st.divider()
    st.subheader("📊 Résultats de l'Impact Mensuel Estimé :")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Heures gagnées / enseignant", f"~{gain_profs_heures_sem / nb_profs:.1f} h / sem", "Soulagement direct")
    m2.metric("Temps total personnel école", f"{total_personnel_heures_mois:.0f} h / mois", "Heures réinvesties")
    m3.metric("Équivalent journées de travail", f"{total_jours_recupere_mois:.1f} jours", "Par mois d'école")
    m4.metric("Temps d'étude actif élèves", f"{gain_eleves_heures_sem * 4:.0f} h / mois", "En immersion française")

    st.markdown("---")
    st.markdown("#### 💡 Où va ce temps précieux réinvesti ?")
    c_a, c_b = st.columns(2)
    with c_a:
        st.success(
            "👩‍🏫 **Pour les Enseignants & la MTS :**\n\n"
            "• Réduction de la charge mentale en soirée et en fin de semaine.\n"
            "• Plus de disponibilité pour la relation humaine et l'accompagnement individuel.\n"
            "• Simplification de la prise en charge des élèves à besoins spécifiques (PAT)."
        )
    with c_b:
        st.info(
            "🎓 **Pour les Élèves & la Communauté :**\n\n"
            "• Déblocage immédiat face aux devoirs sans frustration à la maison.\n"
            "• Augmentation mesurable du temps d'exposition à la langue française.\n"
            "• Continuité pédagogique assurée lors des suppléances et blizzards d'hiver."
        )


# Pied de page institutionnel
st.divider()
st.markdown(
    """
    <div style="text-align: center; color: #6c757d; font-size: 0.85rem; padding-top: 5px;">
        DSFMGPT · Conçu avec rigueur pour l'excellence et l'équité éducative au Manitoba 
        <span style="font-size: 1.1rem; vertical-align: middle;">🦬</span> 
        <img src="https://upload.wikimedia.org/wikipedia/commons/thumb/c/ce/Franco-Manitobain_flag.svg/40px-Franco-Manitobain_flag.svg.png" 
             alt="Drapeau Franco-Manitobain" 
             style="height: 14px; vertical-align: middle; border-radius: 2px; margin-left: 3px; box-shadow: 0 1px 2px rgba(0,0,0,0.15);">
        · 2026-2032
    </div>
    """,
    unsafe_allow_html=True
)
