import os
import time

import gradio as gr
from mcli import predict


URL = os.environ.get("URL")
if URL is None:
    raise ValueError("URL environment variable must be set")
if os.environ.get("MOSAICML_API_KEY") is None:
    raise ValueError("git environment variable must be set")


class Chat:
    default_system_prompt = "A conversation between a user and an LLM-based AI assistant. The assistant gives helpful and honest answers."
    system_format = "<|im_start|>system\n{}<|im_end|>\n"

    def __init__(self, system: str = None, user: str = None, assistant: str = None) -> None:
        if system is not None:
            self.set_system_prompt(system)
        else:
            self.reset_system_prompt()
        self.user = user if user else "<|im_start|>user\n{}<|im_end|>\n"
        self.assistant = assistant if assistant else "<|im_start|>assistant\n{}<|im_end|>\n"
        self.response_prefix = self.assistant.split("{}")[0]

    def set_system_prompt(self, system_prompt):
        # self.system = self.system_format.format(system_prompt)
        return system_prompt

    def reset_system_prompt(self):
        return self.set_system_prompt(self.default_system_prompt)

    def history_as_formatted_str(self, system, history) -> str:
        system = self.system_format.format(system)
        text = system + "".join(
            [
                "\n".join(
                    [
                        self.user.format(item[0]),
                        self.assistant.format(item[1]),
                    ]
                )
                for item in history[:-1]
            ]
        )
        text += self.user.format(history[-1][0])
        text += self.response_prefix
        # stopgap solution to too long sequences
        if len(text) > 4500:
            # delete from the middle between <|im_start|> and <|im_end|>
            # find the middle ones, then expand out
            start = text.find("<|im_start|>", 139)
            end = text.find("<|im_end|>", 139)
            while end < len(text) and len(text) > 4500:
                end = text.find("<|im_end|>", end + 1)
                text = text[:start] + text[end + 1 :]
        if len(text) > 4500:
            # the nice way didn't work, just truncate
            # deleting the beginning
            text = text[-4500:]

        return text

    def clear_history(self, history):
        return []

    def turn(self, user_input: str):
        self.user_turn(user_input)
        return self.bot_turn()

    def user_turn(self, user_input: str, history):
        history.append([user_input, ""])
        return user_input, history

    def bot_turn(self, system, history):
        conversation = self.history_as_formatted_str(system, history)
        assistant_response = call_inf_server(conversation)
        history[-1][-1] = assistant_response
        print(system)
        print(history)
        return "", history


def call_inf_server(prompt):
    try:
        response = predict(
            URL,
            {"inputs": [prompt], "temperature": 0.2, "top_p": 0.9, "output_len": 512},
            timeout=60,
        )
        # print(f'prompt: {prompt}')
        # print(f'len(prompt): {len(prompt)}')
        response = response["outputs"][0]
        # print(f'len(response): {len(response)}')
        # remove spl tokens from prompt
        spl_tokens = ["<|im_start|>", "<|im_end|>"]
        clean_prompt = prompt.replace(spl_tokens[0], "").replace(spl_tokens[1], "")
        return response[len(clean_prompt) :]  # remove the prompt
    except Exception as e:
        # assume it is our error
        # just wait and try one more time
        print(e)
        time.sleep(1)
        response = predict(
            URL,
            {"inputs": [prompt], "temperature": 0.2, "top_p": 0.9, "output_len": 512},
            timeout=60,
        )
        # print(response)
        response = response["outputs"][0]
        return response[len(prompt) :]  # remove the prompt


with gr.Blocks(
    theme=gr.themes.Soft(),
    css=".disclaimer {font-variant-caps: all-small-caps;}",
) as demo:
    gr.Markdown(
        """<h1><center>MosaicML MPT-30B-Chat</center></h1>

        This demo is of [MPT-30B-Chat](https://huggingface.co/mosaicml/mpt-30b-chat). It is based on [MPT-30B](https://huggingface.co/mosaicml/mpt-30b) fine-tuned on approximately 300,000 turns of high-quality conversations, and is powered by [MosaicML Inference](https://www.mosaicml.com/inference).

        If you're interested in [training](https://www.mosaicml.com/training) and [deploying](https://www.mosaicml.com/inference) your own MPT or LLMs, [sign up](https://forms.mosaicml.com/demo?utm_source=huggingface&utm_medium=referral&utm_campaign=mpt-30b) for MosaicML platform.

"""
    )
    conversation = Chat()
    chatbot = gr.Chatbot().style(height=500)
    with gr.Row():
        with gr.Column():
            msg = gr.Textbox(
                label="Chat Message Box",
                placeholder="Chat Message Box",
                show_label=False,
            ).style(container=False)
        with gr.Column():
            with gr.Row():
                submit = gr.Button("Submit")
                stop = gr.Button("Stop")
                clear = gr.Button("Clear")
    with gr.Row():
        with gr.Accordion("Advanced Options:", open=False):
            with gr.Row():
                with gr.Column(scale=2):
                    system = gr.Textbox(
                        label="System Prompt",
                        value=Chat.default_system_prompt,
                        show_label=False,
                    ).style(container=False)
                with gr.Column():
                    with gr.Row():
                        change = gr.Button("Change System Prompt")
                        reset = gr.Button("Reset System Prompt")
    with gr.Row():
        gr.Markdown(
            "Disclaimer: MPT-30B can produce factually incorrect output, and should not be relied on to produce "
            "factually accurate information. MPT-30B was trained on various public datasets; while great efforts "
            "have been taken to clean the pretraining data, it is possible that this model could generate lewd, "
            "biased, or otherwise offensive outputs.",
            elem_classes=["disclaimer"],
        )
    with gr.Row():
        gr.Markdown(
            "[Privacy policy](https://gist.github.com/samhavens/c29c68cdcd420a9aa0202d0839876dac)",
            elem_classes=["disclaimer"],
        )

    submit_event = msg.submit(
        fn=conversation.user_turn,
        inputs=[msg, chatbot],
        outputs=[msg, chatbot],
        queue=False,
    ).then(
        fn=conversation.bot_turn,
        inputs=[system, chatbot],
        outputs=[msg, chatbot],
        queue=True,
    )
    submit_click_event = submit.click(
        fn=conversation.user_turn,
        inputs=[msg, chatbot],
        outputs=[msg, chatbot],
        queue=False,
    ).then(
        fn=conversation.bot_turn,
        inputs=[system, chatbot],
        outputs=[msg, chatbot],
        queue=True,
    )
    stop.click(
        fn=None,
        inputs=None,
        outputs=None,
        cancels=[submit_event, submit_click_event],
        queue=False,
    )
    clear.click(lambda: None, None, chatbot, queue=False).then(
        fn=conversation.clear_history,
        inputs=[chatbot],
        outputs=[chatbot],
        queue=False,
    )
    change.click(
        fn=conversation.set_system_prompt,
        inputs=[system],
        outputs=[system],
        queue=False,
    )
    reset.click(
        fn=conversation.reset_system_prompt,
        inputs=[],
        outputs=[system],
        queue=False,
    )


demo.queue(max_size=18, concurrency_count=8).launch(debug=True)
