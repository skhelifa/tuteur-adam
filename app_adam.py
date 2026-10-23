# =====================================================================
# 1. AFFICHAGE DE L'HISTORIQUE ET DES SUGGESTIONS (EN PREMIER)
# =====================================================================
for idx, msg in enumerate(history):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        
        if msg["role"] == "assistant" and idx == len(history) - 1 and enable_voice_output:
            speak_text(msg["content"])
    
    # Suggestions et bouton de quiz sous la dernière réponse
    if msg["role"] == "assistant" and idx == len(history) - 1:
        st.markdown("💡 **Suggestions rapides :**")
        col1, col2, col3, col4 = st.columns(4)
        btn_query = None
        with col1:
            if st.button("📖 Expliquer plus simplement", key=f"s1_{idx}", use_container_width=True):
                btn_query = "Peux-tu m'expliquer cela plus simplement en français avec une analogie claire ?"
        with col2:
            if st.button("📝 Donner un exemple", key=f"s2_{idx}", use_container_width=True):
                btn_query = "Peux-tu me donner un exemple concret issu du cours en français ?"
        with col3:
            if st.button("🎥 Rechercher une vidéo", key=f"s3_{idx}", use_container_width=True):
                btn_query = "Peux-tu me donner des liens de recherche YouTube cliquables pour illustrer ce concept ?"
        with col4:
            if st.button("🖼️ Décrire un schéma", key=f"s4_{idx}", use_container_width=True):
                btn_query = "Peux-tu me décrire un schéma visuel étape par étape en français ?"

        if btn_query:
            st.session_state.next_question = btn_query
            st.rerun()

        st.markdown("")
        # Bouton Quiz : lorsqu'on clique, le quiz apparaîtra juste en dessous !
        if st.button("🎯 🎲 Générer un quiz de 10 questions sur cette discussion", key=f"quiz_btn_{idx}", use_container_width=True):
            with st.spinner("Génération du quiz personnalisé basé sur vos échanges..."):
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
# 2. AFFICHAGE DU QUIZ (PLACÉ ICI : IL APPARAÎT DIRECTEMENT SOUS LE CHAT)
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
