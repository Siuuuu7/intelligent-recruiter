import mesop as me

import uuid
import httpx  # << NEW: import for sending HTTP requests
import tempfile
import os

from state.host_agent_service import SendMessageWithFile, pick_agent_using_chatgpt
from state.state import AppState, StateMessage
from state.host_agent_service import (
    SendMessage,
    ListConversations,
)
from .chat_bubble import chat_bubble
from .form_render import is_form, render_form, form_sent
from common.types import Message, TextPart


@me.stateclass
class PageState:
    """Local Page State"""

    conversation_id: str = ""
    message_content: str = ""


def on_blur(e: me.InputBlurEvent):
    """Input handler for text field blur."""
    state = me.state(PageState)
    state.message_content = e.value


async def send_message(message: str, message_id: str = ""):
    """Sends the user message to the backend for processing."""
    state = me.state(PageState)
    app_state = me.state(AppState)
    # settings_state = me.state(SettingsState) # Not currently used

    # --- 1. Find the relevant conversation state (local is usually sufficient) ---
    # Use the local app_state.conversations as the primary source for UI logic
    conversation_state = next(
        (
            conv
            for conv in app_state.conversations
            if conv.conversation_id == state.conversation_id
        ),
        None,
    )

    if not conversation_state:
        # As a fallback, check the server list in case the local state is lagging
        server_conversations = await ListConversations()
        server_conv_data = next(
            (
                c
                for c in server_conversations
                if c.conversation_id == state.conversation_id
            ),
            None,
        )
        if server_conv_data:
            print(
                f"[WARN] Conversation {state.conversation_id} found on server but not in local app_state. Using server data."
            )
            # You might want to update local app_state here if needed, or just use server_conv_data attributes
            conv_id_to_use = server_conv_data.conversation_id
            conv_name_to_use = getattr(server_conv_data, "name", "Unknown Conversation")
            # Try to get remote_agent_url if available from server data too
            remote_agent_url = getattr(server_conv_data, "remote_agent_url", None)
        else:
            print(
                f"[ERROR] Conversation {state.conversation_id} not found locally or on server. Cannot send message."
            )
            return
    else:
        # Use data from the found local conversation state
        conv_id_to_use = conversation_state.conversation_id
        conv_name_to_use = conversation_state.conversation_name
        remote_agent_url = getattr(conversation_state, "remote_agent_url", None)

    # --- 2. Append User Message Locally (Immediate UI Feedback) ---
    user_state_message = StateMessage(
        message_id=message_id,  # Use the UUID generated before calling send_message
        role="user",
        content=[(message, "text/plain")],
        metadata={"conversation_id": conv_id_to_use},  # Essential for UI filtering
    )
    if not app_state.messages:
        app_state.messages = []
    # Add only if it doesn't exist (prevents duplicates on rapid clicks/enters)
    if not any(msg.message_id == message_id for msg in app_state.messages):
        app_state.messages.append(user_state_message)
        # Also update the message_ids list in the local conversation object
        if conversation_state and message_id not in conversation_state.message_ids:
            conversation_state.message_ids.append(message_id)

    # --- 3. Prepare Metadata for Backend ---
    request_metadata = {
        "conversation_id": conv_id_to_use,
        "conversation_name": conv_name_to_use,
        # Add any other relevant context if needed
    }

    # --- 4. Determine Target Agent and Add to Metadata (if needed) ---
    if not remote_agent_url:
        print(
            f"[DEBUG] No remote_agent_url set for conversation {conv_id_to_use}. Attempting to pick one."
        )
        try:
            # Assuming pick_agent_using_chatgpt is async
            suggested_agent = await pick_agent_using_chatgpt(message)
            if suggested_agent:
                remote_agent_url = suggested_agent
                print(f"[DEBUG] ChatGPT suggested agent: {remote_agent_url}")
                # Store it back into the local conversation state for persistence within the session
                if conversation_state:
                    conversation_state.remote_agent_url = remote_agent_url
                # IMPORTANT: Add the chosen URL to metadata for the backend
                request_metadata["remote_agent_url"] = remote_agent_url
            else:
                print(
                    "[INFO] No specific agent picked by router. Backend will use default."
                )
        except Exception as e:
            print(f"[ERROR] Failed to pick agent using ChatGPT: {e}")
            # Proceed without a specific agent URL
    else:
        # If an agent URL was already known locally, pass it to the backend
        print(f"[DEBUG] Using existing remote_agent_url: {remote_agent_url}")
        request_metadata["remote_agent_url"] = remote_agent_url

    # --- 5. Check for uploaded files and add to metadata ---
    file_path = None
    print(f"[DEBUG] send_message: app_state object id: {id(app_state)}")
    print(
        f"[DEBUG] Checking for uploaded files. hasattr(app_state, 'conversation_files'): {hasattr(app_state, 'conversation_files')}"
    )
    if hasattr(app_state, "conversation_files"):
        print(f"[DEBUG] app_state.conversation_files: {app_state.conversation_files}")
        print(f"[DEBUG] conv_id_to_use: {conv_id_to_use}")
        print(
            f"[DEBUG] conv_id_to_use in conversation_files: {conv_id_to_use in app_state.conversation_files}"
        )

    # First try app_state method
    if (
        hasattr(app_state, "conversation_files")
        and conv_id_to_use in app_state.conversation_files
    ):
        file_path = app_state.conversation_files[conv_id_to_use]
        print(
            f"[DEBUG] Found uploaded file for conversation {conv_id_to_use}: {file_path}"
        )
    else:
        print(
            f"[DEBUG] No uploaded file found in app_state for conversation {conv_id_to_use}"
        )
        # Fallback: check global uploaded_files dict
        print(f"[DEBUG] Checking global uploaded_files dict: {uploaded_files}")
        for key, path in uploaded_files.items():
            if conv_id_to_use in key:
                file_path = path
                print(f"[DEBUG] Found file in global dict with key {key}: {file_path}")
                break

    if file_path and os.path.exists(file_path):
        request_metadata["file_path"] = file_path
        print(f"[DEBUG] Added file_path to metadata: {file_path}")
    else:
        print(
            f"[DEBUG] File path exists check failed. file_path: {file_path}, exists: {os.path.exists(file_path) if file_path else 'N/A'}"
        )

    # --- 6. Create the Message Payload for the Backend ---
    backend_request = Message(
        # Let backend assign the canonical ID via sanitize_message
        role="user",
        parts=[TextPart(text=message)],
        metadata=request_metadata,
    )

    # --- 7. Send the Request to the Backend ---
    print(f"[DEBUG] Final check before sending to backend:")
    print(f"[DEBUG] file_path: {file_path}")
    print(
        f"[DEBUG] file_path exists: {os.path.exists(file_path) if file_path else 'N/A'}"
    )
    print(f"[DEBUG] backend_request.metadata: {backend_request.metadata}")

    try:
        if file_path and os.path.exists(file_path):
            print(
                f"Sending message content to backend via SendMessageWithFile for conversation {conv_id_to_use}."
            )
            await SendMessageWithFile(backend_request, file_path)
            print(
                f"SendMessageWithFile call completed for conversation {conv_id_to_use}."
            )
        else:
            print(
                f"Sending message content to backend via SendMessage for conversation {conv_id_to_use}."
            )
            await SendMessage(backend_request)
            print(f"SendMessage call completed for conversation {conv_id_to_use}.")
    except Exception as e:
        print(f"[ERROR] Failed to send message via SendMessage: {e}")
        # Optionally, update UI to show an error state?

    # NOTE: No handling of the AI response here. That will happen when the
    # async_poller calls UpdateAppState, which fetches the updated message
    # list (including the AI response added by the backend) from the server


async def send_message_enter(e: me.InputEnterEvent):
    """Send message on Enter key."""
    app_state = me.state(AppState)
    page_state = me.state(PageState)

    user_input = e.value.strip()
    if not user_input:
        return

    message_id = str(uuid.uuid4())
    app_state.background_tasks[message_id] = ""

    await send_message(user_input, message_id)
    yield


async def send_message_button(e: me.ClickEvent):
    """Send message on Send button."""
    app_state = me.state(AppState)
    page_state = me.state(PageState)

    user_input = (
        page_state.message_content.strip()
    )  # 如果你绑定的是 on_blur，得提前 blur 一次
    if not user_input:
        return

    message_id = str(uuid.uuid4())
    app_state.background_tasks[message_id] = ""

    await send_message(user_input, message_id)
    yield


uploaded_files = {}  # 临时缓存上传的文件，key 是 session/thread/message_id


def handle_upload(e: me.UploadEvent):
    """Handle file upload event."""
    print(f"[UPLOAD] Received file: {e.file.name}")
    page_state = me.state(PageState)
    app_state = me.state(AppState)
    print(f"[UPLOAD] page_state.conversation_id: {page_state.conversation_id}")
    print(f"[UPLOAD] app_state object id: {id(app_state)}")

    # Use conversation_id + filename as a more stable key
    file_key = f"{page_state.conversation_id}_{e.file.name}"

    temp_dir = tempfile.mkdtemp()
    file_path = os.path.join(temp_dir, f"{file_key}_{e.file.name}")
    try:
        with open(file_path, "wb") as f:
            f.write(e.file.getvalue())  # Use getvalue() method for file content

        # Store with conversation-based key for lookup later
        uploaded_files[file_key] = file_path

        # Also store with a special marker to indicate a file was uploaded for this conversation
        if not hasattr(app_state, "conversation_files"):
            app_state.conversation_files = {}
        app_state.conversation_files[page_state.conversation_id] = file_path
        print(
            f"[DEBUG] Set app_state.conversation_files[{page_state.conversation_id}] = {file_path}"
        )
        print(
            f"[DEBUG] app_state.conversation_files after upload: {app_state.conversation_files}"
        )

        message_id = str(uuid.uuid4())
        app_state.messages.append(
            StateMessage(
                message_id=message_id,
                role="user",
                content=[(f"[Uploaded file: {e.file.name}]", "text/plain")],
                metadata={
                    "conversation_id": page_state.conversation_id,
                    "file_upload": True,
                },
            )
        )
        print(f"[UPLOAD] File saved successfully: {file_path}")
    except Exception as ex:
        print(f"[ERROR] Failed to save uploaded file: {ex}")


@me.component
def conversation():
    """Conversation component."""
    page_state = me.state(PageState)
    app_state = me.state(AppState)

    print(f"Current conversation ID: {page_state.conversation_id}")
    print(f"App state current conversation ID: {app_state.current_conversation_id}")
    print(f"Message count: {len(app_state.messages)}")

    # Log each message's conversation ID
    for msg in app_state.messages:
        msg_conv_id = None
        if hasattr(msg, "metadata") and isinstance(msg.metadata, dict):
            msg_conv_id = msg.metadata.get("conversation_id")
        print(f"Message ID: {msg.message_id}, Conv ID: {msg_conv_id}")

    if "conversation_id" in me.query_params:
        page_state.conversation_id = me.query_params["conversation_id"]
        app_state.current_conversation_id = page_state.conversation_id

    current_conversation_id = page_state.conversation_id

    with me.box(
        style=me.Style(
            display="flex",
            justify_content="space-between",
            flex_direction="column",
        )
    ):
        # 🛠 FIX: ONLY SHOW MESSAGES for current conversation
        for message in app_state.messages:
            # check metadata or fallback
            message_conversation_id = None
            if hasattr(message, "metadata") and isinstance(message.metadata, dict):
                message_conversation_id = message.metadata.get("conversation_id")

            # if no metadata, try to infer
            if not message_conversation_id:
                message_conversation_id = app_state.current_conversation_id  # fallback

            if message_conversation_id != current_conversation_id:
                continue  # skip unrelated messages!

            if is_form(message):
                render_form(message, app_state)
            elif form_sent(message, app_state):
                chat_bubble(
                    StateMessage(
                        message_id=message.message_id,
                        role=message.role,
                        content=[("Form submitted", "text/plain")],
                    ),
                    message.message_id,
                )
            else:
                chat_bubble(message, message.message_id)

        # input + send button...
        with me.box(
            style=me.Style(
                display="flex",
                flex_direction="row",
                gap=5,
                align_items="center",
                min_width=500,
                width="100%",
            )
        ):
            me.input(
                label="How can I help you?",
                on_blur=on_blur,
                on_enter=send_message_enter,
                style=me.Style(min_width="80vw"),
            )

            # Fixed: Use me.uploader instead of me.upload
            me.uploader(
                label="Upload File",
                accepted_file_types=[
                    ".pdf",
                    ".txt",
                    ".docx",
                    ".csv",
                ],  # Use accepted_file_types parameter
                on_upload=handle_upload,
                style=me.Style(width=150),
            )

            with me.content_button(
                type="flat",
                on_click=send_message_button,
            ):
                me.icon(icon="send")
