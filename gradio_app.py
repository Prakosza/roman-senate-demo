from __future__ import annotations

import json
import os
import time
import uuid

import gradio as gr
import requests
from gradio.themes import Base as BaseTheme
from gradio.themes import Color as ThemeColor
from gradio.themes import GoogleFont

API_BASE = os.getenv("DEBATE_API_BASE", "http://senate-server:8000/v1/chat/completions")
API_KEY = os.getenv("DEBATE_API_KEY", "dummy")

# ── Custom CSS ──────────────────────────────────────────────────────────────
CUSTOM_CSS = """
/* Import a serif font for the Roman feel */
@import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@400;700&family=Spectral:ital,wght@0,400;0,600;1,400&display=swap');

/* ── Force dark regardless of OS light-mode preference ── */
:root, :root * {
    color-scheme: dark !important;
}

/* Global overrides */
.gradio-container {
    font-family: 'Spectral', Georgia, serif !important;
    background: linear-gradient(170deg, #1a1410 0%, #2a2018 40%, #1a1410 100%) !important;
    color: #e8dcc8 !important;
}

/* Header banner */
#senate-header {
    text-align: center;
    padding: 1.2rem 1rem 0.8rem;
    background: linear-gradient(180deg, rgba(139,69,19,0.3) 0%, transparent 100%);
    border-bottom: 2px solid #DAA520;
    margin-bottom: 0.5rem;
}
#senate-header h1 {
    font-family: 'Cinzel', serif !important;
    color: #DAA520 !important;
    font-size: 2rem !important;
    letter-spacing: 3px;
    margin: 0 0 0.25rem 0 !important;
    text-shadow: 0 2px 8px rgba(0,0,0,0.6);
}
#senate-header p {
    color: #b8a88a !important;
    font-style: italic;
    font-size: 0.95rem;
    margin: 0 !important;
}

/* Chatbot area */
.chatbot-container, #chatbot {
    background: #1e1a14 !important;
    border: 1px solid #3d3425 !important;
    border-radius: 8px !important;
}

/* Message bubbles — Gradio 6 selectors */
#chatbot .message-wrap .message,
#chatbot .message {
    border-radius: 8px !important;
    padding: 0.9rem 1rem !important;
    line-height: 1.6 !important;
    color: #e8dcc8 !important;
}
/* Bot (Caesar) bubbles */
#chatbot .bot .message-bubble,
#chatbot .message-wrap .bot,
#chatbot .bot {
    background: #2a2418 !important;
    border-left: 3px solid #DAA520 !important;
    color: #e8dcc8 !important;
}
/* User (Pompey) bubbles */
#chatbot .user .message-bubble,
#chatbot .message-wrap .user,
#chatbot .user {
    background: #1e2a1e !important;
    border-left: 3px solid #8B9A6B !important;
    color: #e8dcc8 !important;
}
/* Markdown inside chat bubbles */
#chatbot .message-bubble p,
#chatbot .message-bubble li,
#chatbot .message-bubble span,
#chatbot .message p,
#chatbot .message li,
#chatbot .message span,
#chatbot .prose * {
    color: #e8dcc8 !important;
}
#chatbot .message-bubble h1,
#chatbot .message-bubble h2,
#chatbot .message-bubble h3,
#chatbot .message h3,
#chatbot .prose h3 {
    color: #DAA520 !important;
}
/* Placeholder text */
#chatbot .placeholder {
    color: #6a5e4e !important;
}

/* Buttons */
.primary-btn, button.primary {
    font-family: 'Cinzel', serif !important;
    letter-spacing: 1px;
}
#start-btn {
    background: linear-gradient(135deg, #8B0000, #a01010) !important;
    color: #DAA520 !important;
    border: 1px solid #DAA520 !important;
    font-weight: 700 !important;
}
#start-btn:hover {
    background: linear-gradient(135deg, #a01010, #c01515) !important;
}
#stop-btn {
    background: linear-gradient(135deg, #1B3A5C, #254a72) !important;
    color: #C0C0C0 !important;
    border: 1px solid #C0C0C0 !important;
    font-weight: 700 !important;
}
#stop-btn:hover {
    background: linear-gradient(135deg, #254a72, #2e5a88) !important;
}
#agenda-btn {
    background: #3d3425 !important;
    color: #DAA520 !important;
    border: 1px solid #5a4a30 !important;
}
#agenda-btn:hover {
    background: #4d4435 !important;
}

/* Textboxes — also cover Gradio 6 wrapper/container */
textarea, input[type="text"],
.gradio-container textarea,
.gradio-container input[type="text"] {
    background: #252018 !important;
    color: #e8dcc8 !important;
    border: 1px solid #3d3425 !important;
    font-family: 'Spectral', Georgia, serif !important;
}
textarea:focus, input[type="text"]:focus {
    border-color: #DAA520 !important;
    outline: none !important;
    box-shadow: 0 0 0 1px #DAA520 !important;
}

/* Labels */
label, .label-text, .gradio-container label span {
    color: #b8a88a !important;
    font-family: 'Cinzel', serif !important;
    font-size: 0.85rem !important;
    letter-spacing: 0.5px;
}

/* Block/panel backgrounds — catch any remaining white panels */
.gradio-container .block,
.gradio-container .panel,
.gradio-container .form {
    background: transparent !important;
}

/* Secondary/clear buttons */
.gradio-container button.secondary {
    background: #3d3425 !important;
    color: #e8dcc8 !important;
    border: 1px solid #5a4a30 !important;
}

/* Footer info */
#senate-footer {
    text-align: center;
    padding: 0.5rem;
    color: #6a5e4e;
    font-size: 0.8rem;
    font-style: italic;
}

/* Status indicator */
#status-text {
    text-align: center;
    padding: 0.3rem;
}
#status-text .prose {
    color: #8a7e6e !important;
    font-size: 0.85rem !important;
}
"""


# ── API helpers ─────────────────────────────────────────────────────────────
def _call(payload: dict, chat_id: str, stream: bool = False):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
        "X-Chat-Id": chat_id,
    }
    return requests.post(API_BASE, headers=headers, json=payload, stream=stream, timeout=300)


def _extract_response_text(payload: dict) -> str:
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return "Unexpected API response format from debate backend."
    return content if isinstance(content, str) else str(content)


# ── Debate callbacks ───────────────────────────────────────────────────────
# Minimum interval between Gradio yields (seconds) — keeps UI smooth
_YIELD_INTERVAL = 0.04  # ~25 fps


def start(topic: str, history: list[dict], chat_id: str):
    if not topic.strip():
        topic = "Was Caesar justified?"

    # Generate a unique chat ID per session
    if chat_id == "gradio-default":
        chat_id = f"gradio-{uuid.uuid4().hex[:8]}"

    payload = {
        "model": "roman-senate",
        "stream": True,
        "messages": [{"role": "user", "content": f"/debate start {topic}"}],
    }
    debate_complete = False
    try:
        with _call(payload, chat_id, stream=True) as resp:
            resp.raise_for_status()
            current_speaker = None
            last_yield = 0.0

            for line in resp.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break

                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue

                delta = obj.get("choices", [{}])[0].get("delta", {}).get("content", "")
                if not isinstance(delta, str) or not delta:
                    continue

                # ── New turn starts ──────────────────────────────────
                if delta.startswith("[START:"):
                    speaker = delta[7:-1]
                    current_speaker = speaker
                    if speaker == "Caesar":
                        history.append({"role": "assistant", "content": "### ⚔️ Caesar\n\n"})
                    else:
                        history.append({"role": "user", "content": "### 🏛️ Pompey\n\n"})
                    yield history, chat_id, gr.update(interactive=False), gr.update(interactive=True)
                    last_yield = time.monotonic()

                # ── Turn finished ────────────────────────────────────
                elif delta == "[END_TURN]":
                    current_speaker = None
                    # Always flush the final state of the bubble
                    yield history, chat_id, gr.update(interactive=False), gr.update(interactive=True)
                    last_yield = time.monotonic()

                # ── Debate over ──────────────────────────────────────
                elif delta == "[DEBATE_DONE]":
                    debate_complete = True
                    history.append({"role": "assistant", "content": "---\n\n✅ **Debate concluded.** The Senate may deliberate."})
                    yield history, chat_id, gr.update(interactive=True), gr.update(interactive=False)

                # ── Error ────────────────────────────────────────────
                elif delta.startswith("[ERROR]"):
                    debate_complete = True
                    history.append({"role": "assistant", "content": f"⚠️ {delta.strip()}"})
                    yield history, chat_id, gr.update(interactive=True), gr.update(interactive=False)

                # ── Token during a turn — append to current bubble ──
                elif current_speaker and history:
                    history[-1]["content"] += delta
                    now = time.monotonic()
                    if (now - last_yield) >= _YIELD_INTERVAL:
                        last_yield = now
                        yield history, chat_id, gr.update(interactive=False), gr.update(interactive=True)

    except requests.RequestException as exc:
        debate_complete = True
        history.append({"role": "assistant", "content": f"⚠️ Backend request failed: {exc}"})
        yield history, chat_id, gr.update(interactive=True), gr.update(interactive=False)

    # Safety net: re-enable start button if stream ended without DEBATE_DONE
    if not debate_complete:
        history.append({"role": "assistant", "content": "---\n\n⚠️ **Debate stream ended unexpectedly.**"})
        yield history, chat_id, gr.update(interactive=True), gr.update(interactive=False)


def stop(history: list[dict], chat_id: str):
    payload = {"model": "roman-senate", "stream": False, "messages": [{"role": "user", "content": "/debate stop"}]}
    try:
        resp = _call(payload, chat_id, stream=False)
        resp.raise_for_status()
        msg = _extract_response_text(resp.json())
    except requests.RequestException as exc:
        msg = f"Backend request failed: {exc}"
    history.append({"role": "assistant", "content": f"⏹️ **{msg}**"})
    return history, chat_id, gr.update(interactive=True), gr.update(interactive=False)


def clear_history():
    return [], "gradio-default", gr.update(interactive=True), gr.update(interactive=False)


# ── Build theme (always dark, regardless of system preference) ──────────────
def _build_theme() -> BaseTheme:
    theme = BaseTheme(
        primary_hue=ThemeColor(
            c50="#fdf8f0", c100="#f5e6cc", c200="#e6cc99",
            c300="#d4a84d", c400="#DAA520", c500="#c99a1d",
            c600="#b08818", c700="#8a6b12", c800="#6b520e",
            c900="#4a3808", c950="#2a2004",
        ),
        secondary_hue=ThemeColor(
            c50="#f0f2f5", c100="#d8dde5", c200="#b0b8c5",
            c300="#8895a5", c400="#6a7a8e", c500="#4a5a6e",
            c600="#3a4a5e", c700="#2a3a4e", c800="#1B3A5C",
            c900="#152a42", c950="#0e1a28",
        ),
        neutral_hue=ThemeColor(
            c50="#f5f0e8", c100="#e8dcc8", c200="#d4c8a8",
            c300="#b8a88a", c400="#8a7e6e", c500="#6a5e4e",
            c600="#4a4238", c700="#3d3425", c800="#2a2418",
            c900="#1e1a14", c950="#1a1410",
        ),
        font=GoogleFont("Spectral"),
        font_mono=GoogleFont("JetBrains Mono"),
    )
    # Override LIGHT-mode theme vars so the app is always dark,
    # even when the OS / browser is in light mode.
    theme.set(
        background_fill_primary="#1e1a14",
        background_fill_secondary="#2a2418",
        body_background_fill="#1a1410",
        body_text_color="#e8dcc8",
        body_text_color_subdued="#8a7e6e",
        block_background_fill="#252018",
        block_border_color="#3d3425",
        block_label_text_color="#b8a88a",
        block_label_background_fill="#1e1a14",
        block_title_text_color="#b8a88a",
        border_color_primary="#3d3425",
        border_color_accent="#DAA520",
        input_background_fill="#252018",
        input_border_color="#3d3425",
        button_primary_background_fill="#8B0000",
        button_primary_background_fill_hover="#a01010",
        button_primary_text_color="#DAA520",
        button_primary_border_color="#DAA520",
        button_secondary_background_fill="#3d3425",
        button_secondary_background_fill_hover="#4d4435",
        button_secondary_text_color="#e8dcc8",
        button_secondary_border_color="#5a4a30",
    )
    return theme


# ── Build UI ────────────────────────────────────────────────────────────────
with gr.Blocks(
    title="Roman Senate Debate",
) as demo:

    # Header
    gr.HTML(
        """
        <div id="senate-header">
            <h1>🏛 SENATVS POPVLVSQVE ROMANVS</h1>
            <p>A deliberation between Caesar and Pompey — each with independent counsel and sources</p>
        </div>
        """,
    )

    chat_id = gr.State("gradio-default")

    # Controls row
    with gr.Row(equal_height=True):
        with gr.Column(scale=3):
            topic = gr.Textbox(
                value="Rubicon legality",
                label="DEBATE TOPIC",
                placeholder="Enter the matter before the Senate…",
                max_lines=1,
            )
        with gr.Column(scale=1, min_width=120):
            start_btn = gr.Button("⚔️  Begin Debate", variant="primary", elem_id="start-btn", size="lg")
        with gr.Column(scale=1, min_width=120):
            stop_btn = gr.Button("🛑  End Debate", variant="secondary", elem_id="stop-btn", size="lg", interactive=False)

    # Chatbot
    chatbot = gr.Chatbot(
        height=520,
        elem_id="chatbot",
        placeholder="The Senate floor is empty. Choose a topic and begin the debate.",
        render_markdown=True,
        layout="panel",
    )

    with gr.Row():
        clear_btn = gr.Button("🗑️ Clear History", size="sm", scale=0)

    gr.HTML('<div id="senate-footer">Powered by RAG-augmented agents · Each senator retrieves only from their own historical sources</div>')

    # Wire events
    start_event = start_btn.click(
        start,
        inputs=[topic, chatbot, chat_id],
        outputs=[chatbot, chat_id, start_btn, stop_btn],
    )
    stop_btn.click(
        stop,
        inputs=[chatbot, chat_id],
        outputs=[chatbot, chat_id, start_btn, stop_btn],
        cancels=[start_event],
    )
    clear_btn.click(
        clear_history,
        outputs=[chatbot, chat_id, start_btn, stop_btn],
        cancels=[start_event],
    )


if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        css=CUSTOM_CSS,
        theme=_build_theme(),
        js="() => { document.documentElement.classList.add('dark'); }",
    )
