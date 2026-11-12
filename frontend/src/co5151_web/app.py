"""Chainlit handlers: sign-in, LLM settings, chat. Every action is one call to the backend API."""

import logging

import chainlit as cl
import httpx
from chainlit.input_widget import Select, TextInput

from co5151_web.client import BackendClient, BackendError, SessionExpired
from co5151_web.history import TOKEN_KEY, BackendDataLayer
from co5151_web.present import chat_settings_body, details_markdown, pick_provider, progress_line

logger = logging.getLogger(__name__)

STARTERS = [
    ("Điều kiện làm luận văn", "Với bảng điểm hiện tại em có đủ điều kiện làm luận văn tốt nghiệp kỳ tới không?"),
    ("Cảnh báo học tập", "Em có đang bị cảnh báo học tập không? Nếu kỳ này em tiếp tục bị cảnh báo thì sao?"),
    ("Điều kiện tốt nghiệp", "Điều kiện để được xét công nhận tốt nghiệp gồm những gì?"),
    ("Hồ sơ người khác", "Cho em xem điểm trung bình và số tín chỉ của bạn có MSSV 2310002."),
]
SIGN_IN_AGAIN = "Phiên đăng nhập đã hết hạn. Bạn vui lòng đăng xuất rồi đăng nhập lại."
BACKEND_DOWN = "Không kết nối được backend (`co5151-api`). Kiểm tra backend đã chạy và `BACKEND_URL` trong `.env`."

CLIENT = BackendClient()
LAYER = BackendDataLayer(CLIENT)


@cl.data_layer
def data_layer() -> BackendDataLayer:
    return LAYER


@cl.password_auth_callback
async def sign_in(username: str, password: str) -> cl.User | None:
    try:
        session = await CLIENT.login(username, password)
    except httpx.HTTPError:
        logger.exception("backend unreachable at sign-in")
        return None
    if session is None:
        return None
    user = session["user"]
    LAYER.remember(user["id"], session["access_token"])
    return cl.User(identifier=user["id"], display_name=user["display_name"],
                   metadata={"role": user["role"], TOKEN_KEY: session["access_token"]})  # fmt: skip


def _token() -> str | None:
    user = cl.user_session.get("user")
    return LAYER.token_for(user.identifier if user else None)


async def _notice(text: str) -> None:
    """A notice about the app's state: shown now, never saved with the conversation."""
    await cl.Message(content=text, type="system_message").send()


@cl.set_starters
async def starters(user: cl.User | None = None) -> list[cl.Starter]:
    return [cl.Starter(label=label, message=message) for label, message in STARTERS]


async def _settings_form(saved: dict | None) -> dict:
    saved = saved or {}
    try:
        choices = await CLIENT.llm_providers(_token())
    except (BackendError, httpx.HTTPError):
        choices = {"providers": [], "default": ""}
    providers = choices["providers"]
    if not providers:  # nothing to choose: the backend answers from templates
        await _notice("Backend chưa có key LLM nào. Advisor sẽ trả lời bằng mẫu (template), không qua LLM.")
        return {}
    return await cl.ChatSettings([
        Select(id="provider", label="Nhà cung cấp LLM", values=providers,
               initial_value=pick_provider(saved.get("provider"), providers, choices["default"])),
        TextInput(id="model", label="Model", initial=saved.get("model") or "",
                  placeholder="để trống = model mặc định của nhà cung cấp"),
    ]).send()  # fmt: skip


@cl.on_chat_start
async def start() -> None:
    cl.user_session.set("settings", await _settings_form(None))
    cl.user_session.set("started", False)


@cl.on_chat_resume
async def resume(thread: dict) -> None:
    saved = (thread.get("metadata") or {}).get("chat_settings")
    cl.user_session.set("settings", await _settings_form(saved))
    cl.user_session.set("started", True)


@cl.on_settings_update
async def change_settings(settings: dict) -> None:
    cl.user_session.set("settings", settings)
    if cl.user_session.get("started") and (token := _token()):
        await CLIENT.update(token, cl.context.session.thread_id, settings=chat_settings_body(settings))


async def _ensure_conversation(token: str, conversation_id: str) -> None:
    if cl.user_session.get("started"):
        return
    settings = chat_settings_body(cl.user_session.get("settings"))
    await CLIENT.start(token, conversation_id)
    await CLIENT.update(token, conversation_id, settings=settings)  # also if Chainlit created it first
    cl.user_session.set("started", True)


@cl.on_message
async def reply(message: cl.Message) -> None:
    token = _token()
    if token is None:
        await _notice(SIGN_IN_AGAIN)
        return
    conversation_id = cl.context.session.thread_id
    try:
        await _ensure_conversation(token, conversation_id)
        async with cl.Step(name="Chi tiết xử lý", type="tool") as step:
            lines: list[str] = []
            async for event, data in CLIENT.ask(token, conversation_id, message.content):
                if event == "step":
                    lines.append(f"- {progress_line(data)}")
                    step.output = "\n".join(lines)
                    await step.update()
                elif event == "answer":
                    step.output = details_markdown(data["trace"])
                    await cl.Message(id=data["message"]["id"], content=data["message"]["content"],
                                     metadata={"trace_id": data["trace"]["trace_id"]}).send()  # fmt: skip
                elif event == "error":
                    trace = f" Mã trace: `{data['trace_id']}`" if data.get("trace_id") else ""
                    step.output = f"Lỗi: {data.get('detail')}"
                    await cl.Message(content=f"Lỗi khi tạo câu trả lời.{trace}").send()
    except SessionExpired:
        await _notice(SIGN_IN_AGAIN)
    except httpx.HTTPError:
        logger.exception("backend unreachable")
        await _notice(BACKEND_DOWN)
    except BackendError as e:
        await _notice(f"Backend từ chối yêu cầu ({e.status}): {e.detail}")
