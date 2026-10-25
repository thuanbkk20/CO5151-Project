import asyncio

import chainlit as cl
from chainlit.input_widget import Select, TextInput

from co5151_web import backend

SESSION_TOKENS: dict[str, str | None] = {}

STARTERS = [
    ("Điều kiện làm luận văn", "Với bảng điểm hiện tại em có đủ điều kiện làm luận văn tốt nghiệp kỳ tới không?"),
    ("Cảnh báo học tập", "Em có đang bị cảnh báo học tập không? Nếu kỳ này em tiếp tục bị cảnh báo thì sao?"),
    ("Điều kiện tốt nghiệp", "Điều kiện để được xét công nhận tốt nghiệp gồm những gì?"),
    ("Hồ sơ người khác", "Cho em xem điểm trung bình và số tín chỉ của bạn có MSSV 2310002."),
]


@cl.password_auth_callback
async def sign_in(username: str, password: str) -> cl.User | None:
    ok, token = await asyncio.to_thread(backend.sign_in, username, password)
    if not ok:
        return None
    SESSION_TOKENS[username] = token
    return cl.User(identifier=username, metadata={"guest": token is None})


@cl.set_starters
async def starters(user: cl.User | None = None) -> list[cl.Starter]:
    return [cl.Starter(label=label, message=message) for label, message in STARTERS]


def _settings_widgets(providers: list[str]) -> list:
    choices = providers or [backend.default_provider(providers)]
    return [
        Select(
            id="provider",
            label="Nhà cung cấp LLM",
            values=choices,
            initial_value=backend.default_provider(providers),
        ),
        TextInput(id="model", label="Model", initial="", placeholder="để trống = model mặc định của nhà cung cấp"),
    ]


def _use_settings(settings: dict) -> None:
    cl.user_session.set("advisor", backend.new_advisor(settings.get("provider"), settings.get("model")))


@cl.on_chat_start
async def start() -> None:
    providers = await asyncio.to_thread(backend.configured_providers)
    settings = await cl.ChatSettings(_settings_widgets(providers)).send()
    _use_settings(settings)
    cl.user_session.set("history", [])
    if not providers:
        await cl.Message(
            content="Chưa có key LLM nào trong `.env`. Advisor sẽ trả lời bằng mẫu (template), không qua LLM."
        ).send()
    user = cl.user_session.get("user")
    if user and user.identifier not in SESSION_TOKENS:
        await cl.Message(content="Server vừa khởi động lại nên phiên đã hết. Hãy đăng xuất rồi đăng nhập lại.").send()


@cl.on_settings_update
async def change_settings(settings: dict) -> None:
    _use_settings(settings)


@cl.on_message
async def reply(message: cl.Message) -> None:
    user = cl.user_session.get("user")
    token = SESSION_TOKENS.get(user.identifier) if user else None
    history: list[dict[str, str]] = cl.user_session.get("history")
    try:
        answer = await asyncio.to_thread(
            backend.ask, cl.user_session.get("advisor"), message.content, token=token, history=history
        )
    except Exception as e:
        await cl.Message(content=f"Lỗi khi gọi Advisor: {type(e).__name__}: {e}").send()
        return
    async with cl.Step(name="Chi tiết xử lý", type="tool") as step:
        step.output = backend.details_markdown(answer.details)
    await cl.Message(content=answer.text).send()
    history += [{"role": "user", "content": message.content}, {"role": "assistant", "content": answer.text}]
