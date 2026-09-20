
import os
from openai import OpenAI

MODEL = "nvidia/nemotron-3-ultra-550b-a55b"


client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=os.environ.get("NVIDIA_API_KEY"),
)

def ask(prompt, system=None, temperature=0.2, enable_thinking=True, timeout=60.0):
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    completion = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=temperature,
        top_p=0.95,
        max_tokens=1024,
        extra_body={"chat_template_kwargs": {"enable_thinking": enable_thinking}},
        stream=True,
        timeout=timeout,
    )

    reasoning_parts, answer_parts = [], []
    for chunk in completion:
        if not chunk.choices:
            continue
        r = getattr(chunk.choices[0].delta, "reasoning_content", None)
        if r:
            reasoning_parts.append(r)
        c = chunk.choices[0].delta.content
        if c is not None:
            answer_parts.append(c)
    return "".join(reasoning_parts), "".join(answer_parts)
