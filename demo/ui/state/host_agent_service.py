import os
import json
import traceback
import sys
import httpx

from typing import Tuple, Any
from service.client.client import ConversationClient
from service.types import (
    Conversation,
    Event,
    CreateConversationRequest,
    ListConversationRequest,
    SendMessageRequest,
    ListMessageRequest,
    PendingMessageRequest,
    ListTaskRequest,
    RegisterAgentRequest,
    ListAgentRequest,
    GetEventRequest,
    SendMessageWithFileRequest
)
from .state import (
    AppState,
    SessionTask,
    StateMessage,
    StateConversation,
    StateTask,
    StateEvent
)
import asyncio
import threading
from common.types import Artifact, Message, Task, Part

server_url = "http://localhost:12000"

async def ListConversations() -> list[Conversation]:
  client = ConversationClient(server_url)
  try:
    response = await client.list_conversation(ListConversationRequest())
    return response.result
  except Exception as e:
    print("Failed to list conversations: ", e)
async def SendMessageWithFile(message: Message, file_path: str) -> str | None:
  client = ConversationClient(server_url)
  try:
    print(f"[DEBUG] SendMessageWithFile: Input message metadata: {message.metadata}")
    print(f"[DEBUG] SendMessageWithFile: file_path: {file_path}")
    
    # Create a copy of the message with file path metadata
    message_with_file = message.model_copy(deep=True)
    if not message_with_file.metadata:
        message_with_file.metadata = {}
    message_with_file.metadata['file_path'] = file_path
    
    print(f"[DEBUG] SendMessageWithFile: Final message metadata: {message_with_file.metadata}")
    
    response = await client.send_message_with_file(SendMessageWithFileRequest(params=message_with_file), file_path)
    return response.result.message_id if response.result else None
  except Exception as e:
    print("Failed to send message with file:", e)
    return None

async def SendMessage(message: Message) -> str | None:
  client = ConversationClient(server_url)
  try:
    response = await client.send_message(SendMessageRequest(params=message))
    return response.result
  except Exception as e:
    print("Failed to send message: ", e)

async def CreateConversation() -> Conversation:
    client = ConversationClient(server_url)
    try:
        print("[DEBUG] Calling create_conversation()...")
        response = await client.create_conversation(CreateConversationRequest())
        print("CreateConversation response:", response)
        return response.result
    except Exception as e:
        print("Failed to create conversation", e)
        return None

async def ListRemoteAgents():
  client = ConversationClient(server_url)
  try:
    response = await client.list_agents(ListAgentRequest())
    return response.result
  except Exception as e:
    print("Failed to read agents", e)

async def AddRemoteAgent(path: str):
  client = ConversationClient(server_url)
  try:
    await client.register_agent(RegisterAgentRequest(params=path))
  except Exception as e:
    print("Failed to register the agent", e)

async def GetEvents() -> list[Event]:
  client = ConversationClient(server_url)
  try:
    response = await client.get_events(GetEventRequest())
    return response.result
  except Exception as e:
    print("Failed to get events", e)

async def GetProcessingMessages():
  client = ConversationClient(server_url)
  try:
    response = await client.get_pending_messages(PendingMessageRequest())
    return dict(response.result)
  except Exception as e:
    print("Error getting pending messages", e)

def GetMessageAliases():
  return {}

async def GetTasks():
  client = ConversationClient(server_url)
  try:
    response = await client.list_tasks(ListTaskRequest())
    return response.result
  except Exception as e:
    print("Failed to list tasks ", e)

async def ListMessages(conversation_id: str) -> list[Message]:
  client = ConversationClient(server_url)
  try:
    response = await client.list_messages(ListMessageRequest(params=conversation_id))
    return response.result
  except Exception as e:
    print("Failed to list messages ", e)

async def UpdateAppState(state: AppState, conversation_id: str):
  """Update the app state."""
  try:
    print(f"[DEBUG] UpdateAppState called, conversation_id: {conversation_id}")
    print(f"[DEBUG] Before update, message count: {len(state.messages)}")
    
    if conversation_id:
      state.current_conversation_id = conversation_id
      
      # 保存本地的未同步消息（比如刚上传的文件或正在处理的消息）
      local_messages = []
      if state.messages:
        for msg in state.messages:
          should_preserve = False
          
          # 保留正在处理中的消息
          if msg.message_id in state.background_tasks:
            should_preserve = True
            print(f"[DEBUG] Preserving background task message: {msg.message_id}")
          
          # 保留文件上传消息（通过检查消息内容）
          if msg.content and len(msg.content) > 0:
            content_text = msg.content[0][0] if isinstance(msg.content[0][0], str) else ""
            if "[Uploaded file:" in content_text or "📎" in content_text:
              should_preserve = True
              print(f"[DEBUG] Preserving file upload message: {msg.message_id}")
          
          # 保留有 file_upload 标记的消息
          if (hasattr(msg, 'metadata') and 
              isinstance(msg.metadata, dict) and 
              msg.metadata.get('file_upload', False)):
            should_preserve = True
            print(f"[DEBUG] Preserving marked file upload message: {msg.message_id}")
          
          if should_preserve:
            local_messages.append(msg)
        
        print(f"[DEBUG] Found {len(local_messages)} local messages to preserve")
      
      messages = await ListMessages(conversation_id)
      if not messages:
        # 如果服务器没有消息，只保留本地未同步的消息
        state.messages = local_messages
        print(f"[DEBUG] No server messages, keeping {len(local_messages)} local messages")
      else:
        # 合并服务器消息和本地未同步消息
        server_messages = [convert_message_to_state(x) for x in messages]
        server_message_ids = {msg.message_id for msg in server_messages}
        
        # 只保留服务器还没有的本地消息
        unique_local_messages = [
          msg for msg in local_messages 
          if msg.message_id not in server_message_ids
        ]
        
        # 合并：服务器消息 + 本地独有消息
        state.messages = server_messages + unique_local_messages
        print(f"[DEBUG] Merged {len(server_messages)} server messages with {len(unique_local_messages)} unique local messages")
        
    conversations = await ListConversations()
    if not conversations:
      state.conversations = []
    else:
      state.conversations = [
          convert_conversation_to_state(x) for x in conversations
      ]

    state.task_list = []
    for task in await GetTasks():
      state.task_list.append(
          SessionTask(
              session_id=extract_conversation_id(task),
              task=convert_task_to_state(task)
          )
      )
    state.background_tasks = await GetProcessingMessages()
    state.message_aliases = GetMessageAliases()
    
    print(f"[DEBUG] After update, message count: {len(state.messages)}")
  except Exception as e:
    print("Failed to update state: ", e)
    traceback.print_exc(file=sys.stdout)
    
async def UpdateApiKey(api_key: str):
    """Update the API key"""
    import httpx
    
    try:
        # Set the environment variable
        os.environ["GOOGLE_API_KEY"] = api_key
        
        # Call the update API endpoint
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{server_url}/api_key/update",
                json={"api_key": api_key}
            )
            response.raise_for_status()
        return True
    except Exception as e:
        print("Failed to update API key: ", e)
        return False

def convert_message_to_state(message: Message) -> StateMessage:
  if not message:
    return StateMessage()
  
  return StateMessage(
      message_id = extract_message_id(message),
      role = message.role,
      content = extract_content(message.parts),
  )

def convert_conversation_to_state(conversation: Conversation) -> StateConversation:
  return StateConversation(
      conversation_id = conversation.conversation_id,
      conversation_name = conversation.name,
      is_active = conversation.is_active,
      message_ids = [extract_message_id(x) for x in conversation.messages],
  )

def convert_task_to_state(task: Task) -> StateTask:
  # Get the first message as the description
  message = task.history[0]
  last_message = task.history[-1]
  output = [extract_content(a.parts) for a in task.artifacts] if task.artifacts else []
  if last_message != message:
    output = [extract_content(last_message.parts)] + output
  return StateTask(
      task_id=task.id,
      session_id=task.sessionId,
      state=str(task.status.state),
      message=convert_message_to_state(message),
      artifacts=output,
  )

def convert_event_to_state(event: Event) -> StateEvent:
  return StateEvent(
      conversation_id=extract_message_conversation(event.content),
      actor=event.actor,
      role=event.content.role,
      id=event.id,
      content=extract_content(event.content.parts),
  )

def extract_content(message_parts: list[Part]) -> list[Tuple[str | dict[str, Any], str]]:
  parts = []
  if not message_parts:
    return []
  for p in message_parts:
    if p.type == 'text':
      parts.append((p.text, 'text/plain'))
    elif p.type == 'file':
      if p.file.bytes:
        parts.append((p.file.bytes, p.file.mimeType))
      else:
        parts.append((p.file.uri, p.file.mimeType))
    elif p.type == 'data':
      try:
        jsonData = json.dumps(p.data)
        if 'type' in p.data and p.data['type'] == 'form':
          parts.append((p.data, 'form'))
        else:
          parts.append((jsonData, 'application/json'))
      except Exception as e:
        print("Failed to dump data", e)
        parts.append(('<data>', 'text/plain'))
  return parts

def extract_message_id(message: Message) -> str:
  if message.metadata and 'message_id' in message.metadata:
    return message.metadata['message_id']
  return ""

def extract_message_conversation(message: Task) -> str:
  if message.metadata and 'conversation_id' in message.metadata:
    return message.metadata['conversation_id']
  return ""

def extract_conversation_id(task: Task) -> str:
  if task.sessionId:
    return task.sessionId
  # Tries to find the first conversation id for the message in the task.
  if (
      task.status.message and
      task.status.message.metadata and
      'conversation_id' in task.status.message.metadata):
    return task.status.message.metadata['conversation_id']
  # Now check if maybe the task has conversation id in metadata.
  if (task.metadata and 'conversation_id' in task.metadata):
    return task.metadata['conversation_id']
  # Now check if any artifacts contain a conversation id.
  if not task.artifacts:
    return ""
  for a in task.artifacts:
    if a.metadata and 'conversation_id' in a.metadata:
      return a.metadata['conversation_id']
  return ""

async def pick_agent_using_chatgpt(user_message: str) -> str | None:
    # Azure OpenAI configuration
    api_key = os.environ.get("AZURE_OPENAI_TOKEN")
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    deployment_name = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")
    api_version = "2025-03-01-preview"
    
    if not api_key:
        print("[DEBUG] No AZURE_OPENAI_TOKEN found.")
        return None
    
    if not endpoint:
        print("[DEBUG] No AZURE_OPENAI_ENDPOINT found.")
        return None

    remote_agents = await ListRemoteAgents()
    if not remote_agents:
        print("[DEBUG] No remote agents available.")
        return None

    agent_descriptions = "\n".join(
        f"- {agent.name}: {agent.description} ({agent.url})"
        for agent in remote_agents
    )

    prompt = f"""You are an intelligent router between users and specialized agents.

Here are the available agents:
{agent_descriptions}

The user's request is:
\"\"\"{user_message}\"\"\"

Pick the best agent that can handle this request.
ONLY reply with the agent's base_url. Nothing else.
"""

    headers = {
        "api-key": api_key,
        "Content-Type": "application/json",
    }

    body = {
        "messages": [
            {"role": "system", "content": "You are an agent router."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.0
    }

    # Construct Azure OpenAI URL
    azure_url = f"{endpoint.rstrip('/')}/openai/deployments/{deployment_name}/chat/completions?api-version={api_version}"

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                azure_url,
                headers=headers,
                json=body
            )
            response.raise_for_status()
            data = response.json()
            text_response = data["choices"][0]["message"]["content"]
            text_response = text_response.strip()

            print(f"[DEBUG] Azure OpenAI suggested agent: {text_response}")
            return text_response
    except Exception as e:
        print(f"[DEBUG] Failed to call Azure OpenAI: {e}")
        return None
