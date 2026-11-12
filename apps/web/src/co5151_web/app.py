import asyncio
import logging

import chainlit as cl
from chainlit.data import get_data_layer
from chainlit.input_widget import Select, TextInput

from co5151_chat_store import Turn, new_trace_id
from co5151_web import backend, history

logger = logging.getLogger(__name__)

# Student Record access tokens by user, kept on the server only. Lost on restart and short-lived: see _student_token.
SESSION_TOKENS: dict[str, str] = {}

STARTERS = [
    ("Điều kiện làm luận văn", "Với bảng điểm hiện tại em có đủ điều kiện làm luận văn tốt nghiệp kỳ tới không?"),
    ("Cảnh báo học tập", "Em có đang bị cảnh báo học tập không? Nếu kỳ này em tiếp tục bị cảnh báo thì sao?"),
    ("Điều kiện tốt nghiệp", "Điều kiện để được xét công nhận tốt nghiệp gồm những gì?"),
    ("Hồ sơ người khác", "Cho em xem điểm trung bình và số tín chỉ của bạn có MSSV 2310002."),
]

# Chat history per user (sidebar, resume) when CHAT_DATABASE_URL is not `off`
STORE = history.open_store()
if STORE is not None:

    @cl.data_layer
    def chat_history_layer() -> history.ChatHistoryDataLayer:
        return history.ChatHistoryDataLayer(STORE)


@cl.password_auth_callback
async def sign_in(username: str, password: str) -> cl.User | None:
    ok, token = await asyncio.to_thread(backend.sign_in, username, password)
    if not ok:
        return None
    if token is None:
        return cl.User(identifier=history.guest_identifier(), display_name="Khách", metadata={"guest": True})
    SESSION_TOKENS[username] = token
    return cl.User(identifier=username, metadata={"guest": False})


def _student_token(user: cl.User | None) -> str | None:
    """The user's Student Record token, re-issued when missing (server restart) or about to expire."""
    if user is None or (user.metadata or {}).get("guest") or user.identifier.startswith("khach-"):
        return None
    token = SESSION_TOKENS.get(user.identifier)
    if not backend.token_is_fresh(token):
        token = backend.refresh_token(user.identifier)
        if token is None:
            SESSION_TOKENS.pop(user.identifier, None)
            return None
        SESSION_TOKENS[user.identifier] = token
    return token


@cl.set_starters
async def starters(user: cl.User | None = None) -> list[cl.Starter]:
    return [cl.Starter(label=label, message=message) for label, message in STARTERS]


def _settings_widgets(providers: list[str], saved: dict | None = None) -> list:
    saved = saved or {}
    choices = providers or [backend.default_provider(providers)]
    provider = saved.get("provider") if saved.get("provider") in choices else backend.default_provider(providers)
    return [
        Select(id="provider", label="Nhà cung cấp LLM", values=choices, initial_value=provider),
        TextInput(
            id="model",
            label="Model",
            initial=saved.get("model") or "",
            placeholder="để trống = model mặc định của nhà cung cấp",
        ),
    ]


def _use_settings(settings: dict) -> None:
    cl.user_session.set("advisor", backend.new_advisor(settings.get("provider"), settings.get("model")))


async def _notice(text: str) -> None:
    """A notice about the app's state: shown now, never saved with the conversation nor sent to the Advisor."""
    await cl.Message(content=text, type="system_message").send()


async def _prepare(saved_settings: dict | None, chat: list[dict[str, str]], *, resumed: bool) -> None:
    providers = await asyncio.to_thread(backend.configured_providers)
    settings = await cl.ChatSettings(_settings_widgets(providers, saved_settings)).send()
    _use_settings(settings)
    cl.user_session.set("history", chat)
    if not providers and not resumed:  # a resumed conversation already shows it
        await _notice("Chưa có key LLM nào trong `.env`. Advisor sẽ trả lời bằng mẫu (template), không qua LLM.")


@cl.on_chat_start
async def start() -> None:
    await _prepare(None, [], resumed=False)


@cl.on_chat_resume
async def resume(thread: dict) -> None:
    """Reopen a saved conversation: same LLM settings, and the Advisor sees the earlier turns as history."""
    await _prepare(cl.context.session.chat_settings, history.chat_history(thread), resumed=True)


@cl.on_settings_update
async def change_settings(settings: dict) -> None:
    _use_settings(settings)


async def _record(turn: Turn) -> None:
    """Save the trace of one turn. A storage failure is logged and never breaks the chat."""
    layer = get_data_layer()
    if not isinstance(layer, history.ChatHistoryDataLayer):
        return
    try:
        await layer.record_turn(turn)
    except Exception:
        logger.exception("could not save trace %s", turn.trace_id)


@cl.on_message
async def reply(message: cl.Message) -> None:
    user = cl.user_session.get("user")
    token = await asyncio.to_thread(_student_token, user)
    chat: list[dict[str, str]] = cl.user_session.get("history")
    conversation_id = cl.context.session.thread_id
    trace_id = new_trace_id()
    try:
        answer = await asyncio.to_thread(
            backend.ask, cl.user_session.get("advisor"), message.content, token=token, history=chat, trace_id=trace_id
        )
    except Exception as e:
        logger.exception("trace=%s failed", trace_id)
        await cl.Message(
            content=f"Lỗi khi gọi Advisor: {type(e).__name__}. Mã trace: `{trace_id}`", metadata={"trace_id": trace_id}
        ).send()
        error = f"{type(e).__name__}: {e}"
        await _record(Turn(trace_id=trace_id, conversation_id=conversation_id, user_message_id=message.id, error=error))
        return
    async with cl.Step(name="Chi tiết xử lý", type="tool", metadata={"trace_id": trace_id}) as step:
        step.output = backend.details_markdown(answer.details)
    sent = await cl.Message(content=answer.text, metadata={"trace_id": trace_id}).send()
    chat += [{"role": "user", "content": message.content}, {"role": "assistant", "content": answer.text}]
    await _record(
        backend.to_turn(
            answer.details, conversation_id=conversation_id, user_message_id=message.id, answer_message_id=sent.id
        )
    )
