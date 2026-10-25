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
# DSFMGPT / Adam's Study Tutor — Écosystème Pédagogique Souverain DSFM / BEF
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


# Fonctions Audio / Synthèse Vocale Web
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
    # Parcourt également les sous-dossiers (ex. ressources de l'enseignant)
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
            "👨‍👩‍👦 Espace Parents et Tuteurs légaux"
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

        # Suggestions d'étayage et déclencheur de Quiz
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
            if st.button("🎯 🎲 Générer un quiz de 10 questions sur notre discussion", key=f"quiz_btn_{idx}", use_container_width=True):
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

    # Affichage du Quiz ACTIF (Placé directement sous la discussion)
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

    tab_bef, tab_ea, tab_notebook, tab_video = st.tabs([
        "📋 Planification Différenciée (BEF / PAT / Défi)",
        "🤝 Coordination Auxiliaire (EA)",
        "📚 Mon Classeur de Cours (Esprit NotebookLM)",
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

        if st.button("🚀 Générer la leçon multiniveau complète", type="primary"):
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
3. ♿ Volet Adaptations & PAT (Aménagements matériels, consignes découpées, réduction de la charge cognitive sans baisse d'exigence).
4. 🚀 Volet Enrichissement & Défi (Tâches à haut niveau taxonomique de Bloom, problèmes ouverts, liens de recherche pour élèves avancés).
5. 💡 Grille de 3 questions socratiques clés pour le bilan.
"""
                resp = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": p_prompt}],
                    temperature=0.3
                )
                st.markdown(resp.choices[0].message.content)

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

Structure attendue :
1. 🎯 Rôle précis de l'auxiliaire pendant la période (Ce qu'il fait pendant le cours magistral vs travail individuel).
2. 💡 Guide de questionnement socratique : 3 questions ciblées à poser à l'élève en cas de blocage pour stimuler son autonomie.
3. ⚠️ Vigilances et pièges à éviter (ex. ne pas faire le calcul à sa place, surveiller les signes de fatigue).
4. 📝 Mini-grille d'observation en 3 critères rapides pour le retour à l'enseignant titulaire en fin d'heure.
"""
                resp_ea = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": ea_prompt}],
                    temperature=0.3
                )
                st.markdown(resp_ea.choices[0].message.content)

    with tab_notebook:
        st.subheader("📚 Mon Espace Documents : Enrichissement du cours (Esprit NotebookLM)")
        st.caption("Déposez vos propres notes de cours, devoirs types ou manuels. Ils sont indexés localement dans le RAG pour vos élèves.")
        
        custom_folder = DOCS_DIR / course["folder"] / "custom_teacher"
        custom_folder.mkdir(parents=True, exist_ok=True)
        
        uploaded_files = st.file_uploader("Ajouter des fichiers PDF personnels pour ce cours", type=["pdf"], accept_multiple_files=True)
        if uploaded_files:
            for f in uploaded_files:
                target_file = custom_folder / f.name
                with open(target_file, "wb") as buffer:
                    buffer.write(f.getbuffer())
            st.success(f"✅ {len(uploaded_files)} ressource(s) ajoutée(s) et indexée(s) avec succès dans le moteur RAG !")
            st.cache_data.clear()

        existing_custom = list(custom_folder.glob("*.pdf"))
        if existing_custom:
            st.markdown("#### Fichiers personnels actuellement actifs :")
            for doc in existing_custom:
                st.write(f"📄 `{doc.name}`")

    with tab_video:
        st.subheader("🎬 Studio Capsule Dialoguée Élève-Professeur (Continuité Blizzard)")
        st.write("Génère un script scénarisé interactif entre un élève virtuel et le professeur, prêt pour le clonage vocal éthique et l'animation.")
        
        notion_cle = st.text_input("Notion clé à scénariser :", value="La différence entre allèle dominant et allèle récessif")
        if st.button("🎥 Générer le script du dialogue vidéo"):
            with st.spinner("Scénarisation de la capsule pédagogique…"):
                vid_prompt = f"""Rédige un script de dialogue vivant et chaleureux de 2 minutes entre un élève (curieux mais hésitant) et son enseignant (bienveillant et pédagogue) pour la DSFM.
Matière : {course_name}
Notion : {notion_cle}

Format attendu :
- [Élève] : Pose les vraies questions de blocage du quotidien.
- [Enseignant] : Répond avec des analogies simples et invite l'élève à déduire la solution.
- [Visuel suggéré] : Description des schémas ou animations qui doivent apparaître à l'écran.
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
elif navigation_espace == "👨‍👩‍👦 Espace Parents et Tuteurs légaux":
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

# Pied de page institutionnel
st.divider()
st.caption("DSFMGPT · Conçu avec rigueur pour l'excellence et l'équité éducative au Manitoba ❤️ · 2026-2032")
