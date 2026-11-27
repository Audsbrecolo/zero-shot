"""两个模型入口共用同一种调用方式：输入提示词和 PIL 图像，返回一段文字。"""

import base64
import io
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MODEL = "Qwen/Qwen3-VL-8B-Instruct"


class HttpModel:
    """连接已启动的视觉模型服务。图片用 PNG 传输，不引入额外 JPEG 压缩。"""

    def __init__(self, model, base_url, timeout=600):
        self.model = model
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.timeout = timeout
        self.backend = "api"

    def ask(self, system, prompt, images):
        parts = []
        for image in images:
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
            parts.append({"type": "image_url", "image_url": {"url": "data:image/png;base64," + encoded}})
        parts.append({"type": "text", "text": prompt})
        body = {"model": self.model, "temperature": 0, "max_tokens": 1100,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": parts}]}
        headers = {"Content-Type": "application/json"}
        key = os.environ.get("SCI_IMAGE_API_KEY")
        if key:
            headers["Authorization"] = "Bearer " + key
        request = Request(self.url, data=json.dumps(body).encode(), headers=headers, method="POST")
        try:
            with urlopen(request, timeout=self.timeout) as response:
                data = json.load(response)
        except HTTPError as exc:
            raise RuntimeError(f"模型服务返回 HTTP {exc.code}。请核对模型名、密钥及多图/JSON 支持。") from exc
        except (URLError, TimeoutError) as exc:
            raise RuntimeError(f"无法连接模型服务或请求超时，请检查服务地址、启动状态和日志。{exc.reason if isinstance(exc, URLError) else exc}") from exc
        try:
            message = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("模型服务的回复缺少 choices[0].message.content。") from exc
        if not isinstance(message, str):
            raise ValueError("模型服务未返回文本。")
        return message


class LocalModel:
    """直接加载一份 Qwen3-VL 权重，所有角色依次复用。"""

    def __init__(self, model):
        try:
            import torch
            from transformers import AutoProcessor, Qwen3VLForConditionalGeneration
        except ImportError as exc:
            raise RuntimeError("本地推理需要 PyTorch、torchvision 和 requirements-image-local.txt 中的依赖。") from exc
        if not torch.cuda.is_available():
            raise RuntimeError("本地 Transformers 入口需要 CUDA GPU。CPU 或量化服务请使用 --backend api。")
        self.model = model
        self.backend = "transformers"
        self.torch = torch
        dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        self.processor = AutoProcessor.from_pretrained(model)
        self.network = Qwen3VLForConditionalGeneration.from_pretrained(
            model, dtype=dtype, device_map={"": 0}, attn_implementation="sdpa"
        ).eval()

    def ask(self, system, prompt, images):
        # 先套用模型自带的聊天模板，再把 PIL 像素交给视觉处理器。
        parts = [{"type": "image"} for _ in images] + [{"type": "text", "text": prompt}]
        messages = [{"role": "system", "content": system}, {"role": "user", "content": parts}]
        text = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self.processor(text=[text], images=images, return_tensors="pt").to(self.network.device)
        with self.torch.inference_mode():
            output = self.network.generate(**inputs, do_sample=False, max_new_tokens=1100)
        generated = output[:, inputs["input_ids"].shape[1]:]
        return self.processor.batch_decode(generated, skip_special_tokens=True)[0]
