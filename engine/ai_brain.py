import os
import sys
import json
import re
from huggingface_hub import hf_hub_download

# Check if llama-cpp is installed
try:
    from llama_cpp import Llama
    HAS_LLAMA = True
except ImportError:
    HAS_LLAMA = False

class AIBrain:
    HAS_LLAMA = HAS_LLAMA
    SYSTEM_PROMPT = """You are CrossMailer Assistant, a helpful email-campaign copywriting helper.

You write clear, honest, permission-based marketing and customer communications.
Do not generate phishing, scams, impersonation, or instructions for wrongdoing.

When writing emails:
- Produce a subject line and an HTML body suitable for legitimate use.
- Use placeholders like {first_name}, {email}, {company_name} when asked.
- Output STRICT JSON with keys "subject" and "body" only."""

    MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "models")

    def __init__(self, model_config=None):
        self.llm = None
        self._ensure_model_dir()

        self.model_config = {
            'source': 'Ollama',
            'hf_repo_id': "",
            'hf_filename': "",
            'local_path': '',
            'ollama_model': 'spamqueen:latest'
        }
        if model_config:
            self.model_config.update(model_config)

    def _ensure_model_dir(self):
        os.makedirs(self.MODEL_DIR, exist_ok=True)

    def _get_current_model_path(self):
        if self.model_config['source'] == 'HuggingFace':
            # Construct path to downloaded model within MODEL_DIR
            return os.path.join(self.MODEL_DIR, self.model_config['hf_filename'])
        elif self.model_config['source'] == 'LocalFile':
            return self.model_config['local_path']
        return None

    def is_model_downloaded(self):
        if self.model_config['source'] == 'Ollama':
            return True # Assumed available if user says so
        current_path = self._get_current_model_path()
        return os.path.exists(current_path) if current_path else False

    def download_model(self):
        if self.model_config['source'] == 'Ollama':
            print("[AIBrain] Ollama models are managed externally.")
            return True

        if self.model_config['source'] != 'HuggingFace':
            print("[AIBrain] Not a HuggingFace model. Skipping download.")
            return False

        repo_id = self.model_config.get('hf_repo_id')
        filename = self.model_config.get('hf_filename')

        if not repo_id or not filename:
            print("[AIBrain] HuggingFace repo_id or filename missing in config.")
            return False

        print(f"[AIBrain] Downloading {filename} from {repo_id}...")
        try:
            hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                local_dir=self.MODEL_DIR,
                local_dir_use_symlinks=False,
                resume_download=True
            )
            print("[AIBrain] Download complete.")
            return True
        except Exception as e:
            print(f"[AIBrain] Download failed: {e}")
            return False

    def load_model(self):
        if self.model_config['source'] == 'Ollama':
            # No explicit load needed for Ollama API, but we set a flag
            self.llm = "Ollama"
            print(f"[AIBrain] Using Ollama model: {self.model_config['ollama_model']}")
            return

        if not HAS_LLAMA:
            raise ImportError("llama-cpp-python is not installed.")
        
        model_path = self._get_current_model_path()

        if not model_path or not os.path.exists(model_path):
            raise FileNotFoundError(f"Model file not found at {model_path}. Please download/select it first.")

        if self.llm is None:
            print(f"[AIBrain] Loading model from {os.path.basename(model_path)} as SC_spam_queen...")
            self.llm = Llama(
                model_path=model_path,
                n_ctx=4096,
                n_gpu_layers=-1, 
                verbose=False
            )
            print("[AIBrain] Persona Initialized.")

    def _query_model(self, prompt, max_tokens=1024, stop=None, temp=1.1):
        if self.model_config['source'] == 'Ollama':
            import requests
            try:
                resp = requests.post('http://localhost:11434/api/generate', json={
                    'model': self.model_config['ollama_model'],
                    'prompt': prompt,
                    'stream': False,
                    'options': {
                        'temperature': temp,
                        'num_predict': max_tokens,
                        'stop': stop or []
                    }
                })
                if resp.status_code == 200:
                    return resp.json().get('response', '')
                return f"Ollama Error: {resp.text}"
            except Exception as e:
                return f"Connection Error: {e}"
        else:
            output = self.llm(
                prompt,
                max_tokens=max_tokens,
                stop=stop or [],
                temperature=temp
            )
            return output['choices'][0]['text'].strip()

    def chat(self, user_input, history=None):
        if not self.llm:
            self.load_model()
            
        full_prompt = f"<|im_start|>system\n{self.SYSTEM_PROMPT}<|im_end|>\n"
        if history:
            for msg in history:
                role = "user" if msg['sender'] == 'You' else 'assistant'
                full_prompt += f"<|im_start|>{role}\n{msg['text']}<|im_end|>\n"
        
        full_prompt += f"<|im_start|>user\n{user_input}<|im_end|>\n<|im_start|>assistant\n"
        
        return self._query_model(full_prompt, max_tokens=1024, stop=["<|im_end|>"])

    def generate_email_campaign(self, topic, target_audience, tone="Professional"):
        if not self.llm:
            self.load_model()

        user_prompt = f"""
Write a permission-based marketing email for: {topic}
Audience: {target_audience}
Desired Tone: {tone}

Requirements:
1. HTML body with inline CSS.
2. Use placeholders: {{first_name}}, {{email}}, {{company_name}}.
3. Output strict JSON: {{"subject": "...", "body": "..."}}
"""
        full_prompt = f"<|im_start|>system\n{self.SYSTEM_PROMPT}<|im_end|>\n<|im_start|>user\n{user_prompt}<|im_end|>\n<|im_start|>assistant\n"

        text = self._query_model(full_prompt, max_tokens=2048, stop=["<|im_end|>"], temp=1.25)
        
        try:
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            return {"subject": "SC_spam_queen Alert", "body": text}
        except:
            return {"subject": "Generation Failure", "body": text}

    def generate_variations(self, base_body, count=5):
        if not self.llm:
            self.load_model()
            
        user_prompt = f"Rewrite this email {count} times using synonyms and different structures to evade filters. Keep HTML tags. Output ONLY a valid JSON list of strings.\n\nOriginal:\n{base_body}"
        full_prompt = f"<|im_start|>system\n{self.SYSTEM_PROMPT}<|im_end|>\n<|im_start|>user\n{user_prompt}<|im_end|>\n<|im_start|>assistant\n"
        
        text = self._query_model(full_prompt, max_tokens=2048, stop=["<|im_end|>"], temp=1.25)
        try:
            match = re.search(r'\[.*\]', text, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            return [base_body]
        except:
            return [base_body]

    def analyze_spam_risk(self, subject, body):
        if not self.llm:
            self.load_model()
        user_prompt = f"Critique this for deliverability and spam risks. Subject: {subject}\nBody: {body}"
        full_prompt = f"<|im_start|>system\n{self.SYSTEM_PROMPT}<|im_end|>\n<|im_start|>user\n{user_prompt}<|im_end|>\n<|im_start|>assistant\n"
        return self._query_model(full_prompt, max_tokens=1024, stop=["<|im_end|>"])

    def get_strategic_advice(self, stats):
        if not self.llm:
            self.load_model()
        user_prompt = f"Campaign Stats: {json.dumps(stats)}. Give me a practical action plan to improve deliverability and engagement for a legitimate opt-in campaign."
        full_prompt = f"<|im_start|>system\n{self.SYSTEM_PROMPT}<|im_end|>\n<|im_start|>user\n{user_prompt}<|im_end|>\n<|im_start|>assistant\n"
        return self._query_model(full_prompt, max_tokens=1024, stop=["<|im_end|>"])
