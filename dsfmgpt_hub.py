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
    """
    Génère une illustration pédagogique et scientifique stricte basée exclusivement sur les faits locaux
    récupérés de la base de données souveraine (RAG), garantissant la véracité de l'image.
    """
    try:
        distill_prompt = f"""Tu es un conseiller en design pédagogique et illustrateur scientifique pour la DSFM.
Conçois un prompt descriptif ultra-précis pour une illustration ou un schéma éducatif de 12e année basé EXCLUSIVEMENT sur les données factuelles et locales fournies ci-dessous.
Surtout : pas de texte complexe, de mots ou de légendes floues ou mal orthographiés (limite au strict minimum ou supprime le texte pour privilégier des symboles ou des repères visuels clairs).

Sujet d'étude : {focus_visuel}
Données contextuelles issues de notre base souveraine : {contexte_texte}

Décris une illustration scientifique détaillée, de type schéma de biologie, diagramme, dessin réaliste ou plan technique, sans fioritures esthétiques ou artistiques, purement pédagogique, sur un fond sobre."""
        
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
if navigation_espace == "🎓 Espace Élève (Tuteur Socratique)":
    st.title(f"🎓 Tuteur Socratique — {course_name}")
    st.info(f"Posture active : **{mode_selectionne}**")

    # Initialisation de l'historique du cours
    if course_name not in st.session_state.histories_by_course:
        st.session_state.histories_by_course[course_name] = [{
            "role": "assistant",
            "content": course["welcome"],
        }]
    history = st.session_state.histories_by_course[course_name]

    # Transcription Whisper
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

    # Affichage du fil de discussion
    for idx, msg in enumerate(history):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg["role"] == "assistant" and idx == len(history) - 1 and enable_voice_output:
                speak_text(msg["content"])

        # Suggestions d'étayage, déclencheur de Quiz, et Générateur d'Image
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

    # Traitement des requêtes textuelles et vocales
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

        # RAG Local hybride
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
elif navigation_espace == "👩‍🏫 Espace Enseignant & Auxiliaire (BEF / EA)":
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
                p_prompt = f"""Tu es un conseiller pédagogique expert du Bureau de l'éducation française (BEF) au Manitoba.
Crée un plan de leçon rigoureux, complet et structuré pour le cours : {course_name}.
- Résultat d'apprentissage : {ras_input}
- Sujet : {sujet_lecon}
- Adaptations PAT : {profil_pat}
- Élèves avancés : {profil_avance}

Structure obligatoire du document :
1. 🎯 Objectifs ministériels et critères de réussite observables (BEF).
2. 📖 Déroulement de classe (Amorce 10 min, Enseignement explicite 15 min, Pratique guidée 25 min, Objectivation 10 min).
3. ♿ Volet Adaptations & PAT (Aménagements matériels, consignes dé
