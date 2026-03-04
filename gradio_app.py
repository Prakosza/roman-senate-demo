from __future__ import annotations

import json
import os
from typing import List, Dict, Generator

import gradio as gr
import requests

API_BASE = os.getenv("DEBATE_API_BASE", "http://senate-server:8000/v1/chat/completions")
API_KEY = os.getenv("DEBATE_API_KEY", "dummy")


def _call(payload: dict, chat_id: str, stream: bool = False):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
        "X-Chat-Id": chat_id,
    }
    return requests.post(API_BASE, headers=headers, data=json.dumps(payload), stream=stream, timeout=300)


def start(topic: str, history: List[Dict], chat_id: str) -> Generator:
    payload = {
        "model": "roman-senate",
        "stream": True,
        "messages": [{"role": "user", "content": f"/debate start {topic}"}],
    }
    resp = _call(payload, chat_id, stream=True)
    resp.raise_for_status()

    for line in resp.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        data = line[6:]
        if data == "[DONE]":
            break
        obj = json.loads(data)
        delta = obj.get("choices", [{}])[0].get("delta", {}).get("content", "")
        if not delta.strip():
            continue

        if delta.startswith("**Caesar:**"):
            history.append({"role": "assistant", "content": f"🟥 Caesar\n\n{delta.replace('**Caesar:**','').strip()}"})
            yield history, chat_id
        elif delta.startswith("**Pompey:**"):
            history.append({"role": "assistant", "content": f"🟦 Pompey\n\n{delta.replace('**Pompey:**','').strip()}"})
            yield history, chat_id
        elif "Debate finished." in delta:
            history.append({"role": "assistant", "content": "✅ Debate finished."})
            yield history, chat_id


def stop(history: List[Dict], chat_id: str):
    payload = {"model": "roman-senate", "stream": False, "messages": [{"role": "user", "content": "/debate stop"}]}
    resp = _call(payload, chat_id, stream=False)
    resp.raise_for_status()
    msg = resp.json()["choices"][0]["message"]["content"]
    history.append({"role": "assistant", "content": f"⏹️ {msg}"})
    return history, chat_id


def agenda(text: str, history: List[Dict], chat_id: str):
    if not text.strip():
        return history, chat_id, ""
    payload = {"model": "roman-senate", "stream": False, "messages": [{"role": "user", "content": text}]}
    resp = _call(payload, chat_id, stream=False)
    resp.raise_for_status()
    msg = resp.json()["choices"][0]["message"]["content"]
    history.append({"role": "assistant", "content": f"📝 {msg}"})
    return history, chat_id, ""


with gr.Blocks(title="Roman Senate Debate") as demo:
    gr.Markdown("## Roman Senate Debate (ready-made UI, one turn = one bubble)")
    chat_id = gr.State("gradio-default")

    with gr.Row():
        topic = gr.Textbox(value="Rubicon legality", label="Topic")
        start_btn = gr.Button("Start debate")
        stop_btn = gr.Button("Stop debate")

    with gr.Row():
        agenda_text = gr.Textbox(label="Moderator agenda update")
        agenda_btn = gr.Button("Send agenda")

    chatbot = gr.Chatbot(type="messages", height=560)

    start_btn.click(start, inputs=[topic, chatbot, chat_id], outputs=[chatbot, chat_id])
    stop_btn.click(stop, inputs=[chatbot, chat_id], outputs=[chatbot, chat_id])
    agenda_btn.click(agenda, inputs=[agenda_text, chatbot, chat_id], outputs=[chatbot, chat_id, agenda_text])


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
