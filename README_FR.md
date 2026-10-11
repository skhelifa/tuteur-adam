# Adam's Study Tutor — deployment package

This is a separate Streamlit application for Adam. It is designed to be uploaded to a **new GitHub repository**, so Toutou's working app and repository are left untouched.

## Included
- `app_adam.py`: three courses, bilingual support (English by default; French explanations on request), microphone transcription, separate chat history per course.
- `requirements.txt`: dependencies.
- `documents/biology/`, `documents/english/`, `documents/cinema/`: place official course PDFs in the matching folder to enable local PDF retrieval.

## Stage 1: create a separate GitHub repository
1. Sign in to GitHub.
2. Click `+` → `New repository`.
3. Name it `tuteur-adam`.
4. Choose **Private** if available and appropriate for your Streamlit account. Do not upload any API keys.
5. Create the repository.
6. Upload the contents of this ZIP (not the ZIP file itself) to the new repository. Keep the folder structure shown below.
7. Commit the files.

Expected layout:
```
tuteur-adam/
├── app_adam.py
├── requirements.txt
└── documents/
    ├── biology/
    ├── english/
    └── cinema/
```

## Stage 2: deploy on Streamlit Community Cloud
1. Open https://share.streamlit.io/ and sign in with GitHub.
2. Click **Create app**.
3. Select the new `tuteur-adam` repository and branch `main`.
4. Set **Main file path** to `app_adam.py`.
5. Open **Advanced settings** → **Secrets** and enter:
   ```
   OPENAI_API_KEY = "YOUR_OPENAI_API_KEY"
   ```
   Replace the placeholder with your own key. Do not put the key in GitHub or in this README.
6. Click **Deploy** and wait for the app to finish starting.
7. Open the generated `*.streamlit.app` link and test all three subjects, text chat, and microphone transcription.

## Stage 3: add official Manitoba course documents gradually
Download official PDFs from the sources below and upload them into the matching folder. You can start with one or two PDFs per course and add more later.

- Biology 12e, Manitoba curriculum: https://www.edu.gov.mb.ca/m12/frpub/ped/sn/biologie_12e/index.html
- Grade 12 English Language Arts (Comprehensive Focus overview): https://www.edu.gov.mb.ca/k12/framework/english/ela/ela_gr12.html
- Le cinéma, témoin de l'histoire moderne 12e année: https://www.edu.gov.mb.ca/m12/frpub/ped/sh/cinema/index.html

For English, save the official curriculum page as a PDF using your browser's Print → Save as PDF, or add teacher-provided course documents. Name the files clearly, e.g. `biology_40s_implementation.pdf`, `ela_grade12.pdf`, `cinema_12e_implementation.pdf`.

After uploading PDFs, commit the changes. Streamlit will redeploy the app. The app extracts text from the PDFs and retrieves passages using a simple local keyword-based method. This is an initial, transparent retrieval stage—not a semantic vector database. It works best when Adam's question uses words from the documents. Later, the retrieval can be upgraded to semantic embeddings if needed.

## Important notes
- The app sends questions to OpenAI for responses and sends recorded audio to OpenAI for transcription.
- API use may incur charges. Check the limits and billing settings on the OpenAI account used for the key.
- Never commit API keys, student passwords, or other secrets.
- Streamlit Community Cloud sharing/privacy settings should be checked before sharing the link.
- The PDF retrieval feature uses text extraction. Scanned image-only PDFs may not yield searchable text unless OCR is applied.
