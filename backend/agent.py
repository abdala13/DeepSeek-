import os
import json
import time
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

import requests

from .utils import split_csv_env

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
MODEL_CACHE_FILE = DATA_DIR / "model_cache.json"


class HusamAgent:
    def __init__(self) -> None:
        self.provider_pref = os.getenv("HUSAM_PROVIDER", "auto").strip().lower()
        self.groq_key = os.getenv("GROQ_API_KEY", "").strip()
        self.hf_token = (os.getenv("HF_TOKEN", "") or os.getenv("HUGGINGFACE_API_TOKEN", "")).strip()
        self.groq_models = split_csv_env("GROQ_MODEL_CANDIDATES", "llama-3.3-70b-versatile,llama-3.1-8b-instant")
        self.hf_models = split_csv_env("HF_MODEL_CANDIDATES", "meta-llama/Llama-3.1-8B-Instruct,Qwen/Qwen2.5-Coder-32B-Instruct,mistralai/Mistral-7B-Instruct-v0.3")
        self.temperature = float(os.getenv("HUSAM_TEMPERATURE", "0.35"))
        self.max_tokens = int(os.getenv("HUSAM_MAX_TOKENS", "4096"))
        self.timeout = int(os.getenv("HUSAM_API_TIMEOUT", "90"))

    def system_prompt(self, mode: str = "assistant", language: str = "auto") -> str:
        modes = {
            "assistant": "مساعد ذكي عام، واضح، عملي، ومباشر.",
            "coder": "مهندس برمجيات خبير. اكتب كود كامل ونظيف وقابل للتشغيل ولا تختصر الملفات المهمة.",
            "debugger": "خبير تحليل أخطاء. اشرح سبب الخطأ ثم أعط خطوات تصحيح دقيقة.",
            "architect": "مهندس أنظمة. قدّم بنية احترافية، ملفات، APIs، أمان، ونشر.",
            "creative": "مساعد إبداعي لصناعة المحتوى والأفكار والسكريبتات.",
        }
        lang_rule = "اكتشف لغة المستخدم وأجب بنفس اللغة." if language == "auto" else f"أجب باللغة: {language}."
        return f"""
أنت Husam Prime AI، مساعد ذكاء اصطناعي شخصي بواجهة ويب شبيهة بتجربة ChatGPT.
الدور الحالي: {modes.get(mode, modes['assistant'])}
{lang_rule}

قواعد مهمة:
- لا تخترع أنك شغلت كودًا أو زرت موقعًا إذا لم يحدث فعليًا.
- عند طلب مشروع برمجي، أعط ملفات كاملة منظمة، واشرح أوامر التشغيل.
- استخدم Markdown واضح، وجداول عند الحاجة، وكتل كود بأسماء الملفات.
- لا تضع مفاتيح API أو أسرار داخل الكود. استخدم Environment Variables.
- في الإجابات العربية حافظ على UTF-8 طبيعي ولا تستخدم رموز غريبة.
""".strip()

    def build_messages(self, messages: List[Dict[str, str]], mode: str, language: str) -> List[Dict[str, str]]:
        result = [{"role": "system", "content": self.system_prompt(mode, language)}]
        for item in messages[-24:]:
            role = item.get("role")
            if role in {"user", "assistant"}:
                result.append({"role": role, "content": item.get("content", "")})
        return result

    def providers_to_try(self) -> List[Tuple[str, str]]:
        pairs: List[Tuple[str, str]] = []
        if self.provider_pref in {"auto", "groq"} and self.groq_key:
            pairs.extend(("groq", m) for m in self.groq_models)
        if self.provider_pref in {"auto", "huggingface", "hf"} and self.hf_token:
            pairs.extend(("huggingface", m) for m in self.hf_models)
        if self.provider_pref == "auto":
            cached = self.load_cached_model()
            if cached:
                pair = (cached.get("provider", ""), cached.get("model", ""))
                if pair in pairs:
                    pairs.remove(pair)
                    pairs.insert(0, pair)
        return pairs

    def load_cached_model(self) -> Optional[Dict[str, str]]:
        try:
            return json.loads(MODEL_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return None

    def save_cached_model(self, provider: str, model: str) -> None:
        MODEL_CACHE_FILE.write_text(json.dumps({"provider": provider, "model": model}, ensure_ascii=False, indent=2), encoding="utf-8")

    def call(self, history_messages: List[Dict[str, str]], mode: str = "assistant", language: str = "auto") -> Dict[str, Any]:
        messages = self.build_messages(history_messages, mode, language)
        errors = []
        for provider, model in self.providers_to_try():
            started = time.time()
            try:
                if provider == "groq":
                    answer, usage = self.call_groq(model, messages)
                else:
                    answer, usage = self.call_hf(model, messages)
                self.save_cached_model(provider, model)
                return {
                    "ok": True,
                    "answer": answer,
                    "provider": provider,
                    "model": model,
                    "usage": usage,
                    "latency": round(time.time() - started, 3),
                    "errors": errors,
                }
            except Exception as exc:
                errors.append({"provider": provider, "model": model, "error": str(exc)[:900]})
        return {"ok": False, "answer": "", "provider": "none", "model": "none", "usage": {}, "latency": 0, "errors": errors}

    def call_groq(self, model: str, messages: List[Dict[str, str]]) -> Tuple[str, Dict[str, Any]]:
        endpoint = "https://api.groq.com/openai/v1/chat/completions"
        payload = {"model": model, "messages": messages, "temperature": self.temperature, "max_tokens": self.max_tokens}
        headers = {"Authorization": f"Bearer {self.groq_key}", "Content-Type": "application/json; charset=utf-8"}
        r = requests.post(endpoint, headers=headers, json=payload, timeout=self.timeout)
        if r.status_code >= 400:
            raise RuntimeError(f"Groq API {r.status_code}: {r.text[:1000]}")
        data = r.json()
        return data["choices"][0]["message"]["content"].strip(), data.get("usage", {})

    def call_hf(self, model: str, messages: List[Dict[str, str]]) -> Tuple[str, Dict[str, Any]]:
        endpoint = "https://router.huggingface.co/v1/chat/completions"
        payload = {"model": model, "messages": messages, "temperature": self.temperature, "max_tokens": self.max_tokens}
        headers = {"Authorization": f"Bearer {self.hf_token}", "Content-Type": "application/json; charset=utf-8"}
        r = requests.post(endpoint, headers=headers, json=payload, timeout=self.timeout)
        if r.status_code >= 400:
            raise RuntimeError(f"Hugging Face API {r.status_code}: {r.text[:1000]}")
        data = r.json()
        return data["choices"][0]["message"]["content"].strip(), data.get("usage", {})

    def health_check(self) -> Dict[str, Any]:
        probe = [{"role": "user", "content": "Reply with OK only."}]
        errors = []
        for provider, model in self.providers_to_try():
            try:
                if provider == "groq":
                    answer, _ = self.call_groq(model, self.build_messages(probe, "assistant", "English"))
                else:
                    answer, _ = self.call_hf(model, self.build_messages(probe, "assistant", "English"))
                self.save_cached_model(provider, model)
                return {"ok": True, "provider": provider, "model": model, "answer": answer, "errors": errors}
            except Exception as exc:
                errors.append({"provider": provider, "model": model, "error": str(exc)[:500]})
        return {"ok": False, "provider": "none", "model": "none", "errors": errors}
