# Husam Prime AI Final Stable

نسخة نهائية مستقرة أكثر: **FastAPI + SQLite + واجهة HTML/CSS/JS جاهزة** بدون Streamlit وبدون Node/npm، لتقليل أخطاء Render نهائيًا.

## لماذا هذه النسخة أكثر ثباتًا؟

- لا يوجد `streamlit`.
- لا يوجد `npm install`.
- لا يوجد Vite/React build conflict.
- الواجهة مبنية Static مباشرة داخل `frontend/dist` وتُخدم من FastAPI.
- Python مثبت على 3.11.11 لتجنب مشاكل `pydantic-core`.

## المزايا

- واجهة Chat حديثة قريبة من تطبيقات الذكاء الاصطناعي.
- محادثات متعددة محفوظة في SQLite.
- أوضاع: مساعد، مبرمج، تصحيح، معماري، إبداعي.
- Auto Model Router بين Groq وHugging Face.
- زر فحص النماذج.
- ضغط الأكواد إلى ZIP من أي رد يحتوي على كتل كود.
- Python Runner اختياري ومغلق افتراضيًا للأمان.
- GitHub Sync يدوي.
- دعم عربي UTF-8 بدون Mojibake.

## Render

Build Command:

```bash
pip install -r requirements.txt
```

Start Command:

```bash
uvicorn backend.main:app --host 0.0.0.0 --port $PORT
```

Environment Variables:

```env
PYTHON_VERSION=3.11.11
HUSAM_PROVIDER=auto
GROQ_API_KEY=your_groq_key
GROQ_MODEL_CANDIDATES=llama-3.3-70b-versatile,llama-3.1-8b-instant
```

اختياري لـ Hugging Face:

```env
HF_TOKEN=your_hf_token
HF_MODEL_CANDIDATES=meta-llama/Llama-3.1-8B-Instruct,Qwen/Qwen2.5-Coder-32B-Instruct,mistralai/Mistral-7B-Instruct-v0.3
```

اختياري لـ GitHub Sync:

```env
GITHUB_TOKEN=your_github_token
GITHUB_REPO_URL=https://github.com/abdala13/DeepSeek-.git
GITHUB_BRANCH=main
GIT_USER_NAME=Husam Prime AI
GIT_USER_EMAIL=abdala0592656289@gmail.com
```

تشغيل السكربتات اختياري ومغلق افتراضيًا:

```env
ENABLE_SCRIPT_RUNNER=false
SCRIPT_TIMEOUT_SECONDS=8
```

لا تفعل `ENABLE_SCRIPT_RUNNER=true` إلا إذا الموقع خاص بك وغير مفتوح للناس.
