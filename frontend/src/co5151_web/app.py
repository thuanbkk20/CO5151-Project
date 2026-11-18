"""Chainlit handlers: sign-in, LLM settings, chat. Every action is one call to the backend API."""

import asyncio
import logging
from typing import Any

import chainlit as cl
import httpx
from chainlit.input_widget import Select, TextInput

from co5151_web.client import BackendClient, BackendError, SessionExpired
from co5151_web.history import TOKEN_KEY, BackendDataLayer
from co5151_web.present import (
    STEP_NAME,
    chat_settings_body,
    pick_provider,
    progress_line,
    provision_markdown,
    source_label,
    starters_for,
    step_markdown,
    welcome_markdown,
)

logger = logging.getLogger(__name__)

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


@cl.set_chat_profiles
async def chat_profiles(user: cl.User | None = None, language: str | None = None) -> list[cl.ChatProfile]:
    """One profile per account, never a choice (Chainlit hides the picker for a single profile): it carries the
    welcome and the starters of the account's role, shown on an empty conversation."""
    role = (user.metadata or {}).get("role") if user else None
    name = user.display_name if user else None
    starters = [cl.Starter(label=label, message=question) for label, question in starters_for(role)]
    return [cl.ChatProfile(name="advisor", display_name="Cố vấn học vụ", icon="/public/favicon.svg",
                           markdown_description=welcome_markdown(role, name), starters=starters)]  # fmt: skip


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


SOURCE = "source"  # the action of a cited provision's button


async def _provision(token: str, provision_id: str) -> dict[str, Any] | None:
    """A cited provision, kept for the session so the button does not ask again; None when it cannot be read."""
    cache: dict[str, Any] = cl.user_session.get("provisions") or {}
    if provision_id not in cache:
        try:
            cache[provision_id] = await CLIENT.provision(token, provision_id)
        except (BackendError, httpx.HTTPError):
            logger.warning("provision %s could not be read", provision_id, exc_info=True)
            return None
        cl.user_session.set("provisions", cache)
    return cache[provision_id]


async def _source_actions(token: str, citations: list[str]) -> list[cl.Action]:
    """One button per provision the answer cites; the label needs the provision, read once per citation."""
    citations = list(dict.fromkeys(citations))
    provisions = await asyncio.gather(*(_provision(token, pid) for pid in citations))
    return [
        cl.Action(name=SOURCE, payload={"id": pid}, label=source_label(p) if p else pid, icon="book-open",
                  tooltip="Xem nguyên văn điều khoản")
        for pid, p in zip(citations, provisions, strict=True)
    ]  # fmt: skip


@cl.action_callback(SOURCE)
async def show_source(action: cl.Action) -> None:
    """The cited provision's source text in the side panel."""
    token = _token()
    if token is None:
        await _notice(SIGN_IN_AGAIN)
        return
    provision_id = str(action.payload.get("id", ""))
    provision = await _provision(token, provision_id)
    if provision is None:
        title, body = provision_id, "Không tải được điều khoản này (backend hoặc Regulation MCP không trả lời)."
    else:
        title, body = provision["title"], provision_markdown(provision)
    await cl.ElementSidebar.set_elements([cl.Text(name=provision_id, content=body)], key=provision_id)
    await cl.ElementSidebar.set_title(title)


@cl.on_message
async def reply(message: cl.Message) -> None:
    token = _token()
    if token is None:
        await _notice(SIGN_IN_AGAIN)
        return
    conversation_id = cl.context.session.thread_id
    try:
        await _ensure_conversation(token, conversation_id)
        async with cl.Step(name=STEP_NAME, type="tool") as step:
            lines: list[str] = []
            async for event, data in CLIENT.ask(token, conversation_id, message.content):
                if event == "step":
                    lines.append(progress_line(data))
                    step.output = step_markdown(lines)
                    await step.update()
                elif event == "answer":
                    step.output = step_markdown(lines, data["trace"])
                    sources = await _source_actions(token, data["trace"].get("citations") or [])
                    await cl.Message(id=data["message"]["id"], content=data["message"]["content"], actions=sources,
                                     metadata={"trace_id": data["trace"]["trace_id"]}).send()  # fmt: skip
                elif event == "error":
                    trace = f" Mã trace: `{data['trace_id']}`" if data.get("trace_id") else ""
                    step.output = step_markdown([*lines, f"Lỗi: {data.get('detail')}"])
                    await cl.Message(content=f"Lỗi khi tạo câu trả lời.{trace}").send()
    except SessionExpired:
        await _notice(SIGN_IN_AGAIN)
    except httpx.HTTPError:
        logger.exception("backend unreachable")
        await _notice(BACKEND_DOWN)
    except BackendError as e:
        await _notice(f"Backend từ chối yêu cầu ({e.status}): {e.detail}")
