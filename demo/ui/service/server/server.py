import asyncio
import base64
import threading
import os
import uuid
from typing import Any
from fastapi import APIRouter
from fastapi import Request, Response
from common.types import Message, Task, FilePart, FileContent
from .in_memory_manager import InMemoryFakeAgentManager
from .application_manager import ApplicationManager
from .adk_host_manager import ADKHostManager, get_message_id
from service.types import (
    Conversation,
    Event,
    CreateConversationResponse,
    ListConversationResponse,
    SendMessageResponse,
    MessageInfo,
    ListMessageResponse,
    PendingMessageResponse,
    ListTaskResponse,
    RegisterAgentResponse,
    ListAgentResponse,
    GetEventResponse,
    SendMessageWithFileResponse
)

class ConversationServer:
  """ConversationServer is the backend to serve the agent interactions in the UI

  This defines the interface that is used by the Mesop system to interact with
  agents and provide details about the executions.
  """
  def __init__(self, router: APIRouter):
    agent_manager = os.environ.get("A2A_HOST", "ADK")
    self.manager: ApplicationManager
    
    # Get API key from environment
    api_key = os.environ.get("GOOGLE_API_KEY", "")
    uses_vertex_ai = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").upper() == "TRUE"
    
    if agent_manager.upper() == "ADK":
      self.manager = ADKHostManager(api_key=api_key, uses_vertex_ai=uses_vertex_ai)
    else:
      self.manager = InMemoryFakeAgentManager()
    self._file_cache = {} # dict[str, FilePart] maps file id to message data
    self._message_to_cache = {} # dict[str, str] maps message id to cache id

    router.add_api_route(
        "/conversation/create",
        self._create_conversation,
        methods=["POST"])
    router.add_api_route(
        "/conversation/list",
        self._list_conversation,
        methods=["POST"])
    router.add_api_route(
        "/message/send",
        self._send_message,
        methods=["POST"])
    router.add_api_route(
        "/message/send_with_file",
        self._send_message_with_file,
        methods=["POST"])

    router.add_api_route(
        "/events/get",
        self._get_events,
        methods=["POST"])
    router.add_api_route(
        "/message/list",
        self._list_messages,
        methods=["POST"])
    router.add_api_route(
        "/message/pending",
        self._pending_messages,
        methods=["POST"])
    router.add_api_route(
        "/task/list",
        self._list_tasks,
        methods=["POST"])
    router.add_api_route(
        "/agent/register",
        self._register_agent,
        methods=["POST"])
    router.add_api_route(
        "/agent/list",
        self._list_agents,
        methods=["POST"])
    router.add_api_route(
        "/message/file/{file_id}",
        self._files,
        methods=["GET"])
    router.add_api_route(
        "/api_key/update",
        self._update_api_key,
        methods=["POST"])

  # Update API key in manager
  def update_api_key(self, api_key: str):
    if isinstance(self.manager, ADKHostManager):
      self.manager.update_api_key(api_key)

  async def _create_conversation(self):
    c = self.manager.create_conversation()
    return CreateConversationResponse(result=c).model_dump()
  async def _send_message_with_file(self, request: Request):
    print(f"[DEBUG] Server: _send_message_with_file called")
    
    # Check content type to determine how to parse the request
    content_type = request.headers.get("content-type", "")
    print(f"[DEBUG] Server: Request content-type: {content_type}")
    
    message = None
    
    try:
      if "multipart/form-data" in content_type:
        # Handle multipart form data (actual file upload)
        print(f"[DEBUG] Server: Parsing multipart form data")
        form = await request.form()
        
        if 'message' in form:
          import json
          message_data = json.loads(form['message'])
          print(f"[DEBUG] Server: message_data from form: {message_data}")
          message = Message(**message_data['params'])
          
          # Handle uploaded file if present
          if 'file' in form:
            uploaded_file = form['file']
            print(f"[DEBUG] Server: Received file: {uploaded_file.filename}")
            
            # Extract text from uploaded file and include it in the message
            file_text = self._extract_text_from_uploaded_file(uploaded_file)
            if file_text:
              # Append extracted text to the message content
              original_text = message.parts[0].text if message.parts else ""
              enhanced_text = f"""{original_text}

--- UPLOADED FILE CONTENT ({uploaded_file.filename}) ---
{file_text}
--- END OF FILE CONTENT ---

Please analyze the above resume content and provide a detailed rating."""
              
              # Update the message with enhanced text
              from common.types import TextPart
              message.parts = [TextPart(text=enhanced_text)]
              print(f"[DEBUG] Server: Enhanced message with {len(file_text)} characters of extracted text")
        else:
          print(f"[DEBUG] Server: No 'message' field in form data")
          return {"error": "No message field in form data"}
          
      else:
        # Handle JSON format (regular message with file metadata)
        print(f"[DEBUG] Server: Parsing JSON data")
        try:
          message_data = await request.json()
          print(f"[DEBUG] Server: message_data from JSON: {message_data}")
          message = Message(**message_data['params'])
        except UnicodeDecodeError as unicode_error:
          print(f"[DEBUG] Server: Unicode decode error - request may contain binary data: {unicode_error}")
          return {"error": "Invalid request format - contains binary data"}
        except json.JSONDecodeError as json_error:
          print(f"[DEBUG] Server: JSON decode error: {json_error}")
          return {"error": "Invalid JSON format"}
          
    except Exception as e:
      print(f"[DEBUG] Server: Exception in request parsing: {e}")
      return {"error": f"Failed to parse request: {str(e)}"}
    
    if not message:
      print(f"[DEBUG] Server: Failed to create message object")
      return {"error": "Failed to create message object"}
    
    print(f"[DEBUG] Server: Final message object: {message}")
    print(f"[DEBUG] Server: Message metadata: {message.metadata}")
    message = self.manager.sanitize_message(message)

    # 储存 message 到会话里
    conversation_id = message.metadata.get("conversation_id")
    if conversation_id:
      conv = self.manager.get_conversation(conversation_id)
      if conv:
        conv.messages.append(message)

    # 处理可能的文件（你可以在此处理文件缓存逻辑）
    t = threading.Thread(target=lambda: asyncio.run(self.manager.process_message(message)))
    t.start()

    return SendMessageWithFileResponse(result=MessageInfo(
      message_id=message.metadata.get('message_id'),
      conversation_id=conversation_id,
    ))

  async def _send_message(self, request: Request):
    message_data = await request.json()
    message = Message(**message_data['params'])
    message = self.manager.sanitize_message(message)
    conversation_id = message.metadata.get("conversation_id")
    if conversation_id:
        conv = self.manager.get_conversation(conversation_id)
        if conv:
            conv.messages.append(message)  # Save user message
    
    t = threading.Thread(target=lambda: asyncio.run(self.manager.process_message(message)))
    t.start()
    return SendMessageResponse(result=MessageInfo(
        message_id=message.metadata['message_id'],
        conversation_id=message.metadata['conversation_id'] if 'conversation_id' in message.metadata else '',
    ))

  async def _list_messages(self, request: Request):
    message_data = await request.json()
    conversation_id = message_data['params']
    conversation = self.manager.get_conversation(conversation_id)
    if conversation:
      return ListMessageResponse(result=self.cache_content(
          conversation.messages))
    return ListMessageResponse(result=[])

  def cache_content(self, messages: list[Message]):
    rval = []
    for m in messages:
      message_id = get_message_id(m)
      if not message_id:
        rval.append(m)
        continue
      new_parts = []
      for i, part in enumerate(m.parts):
        if part.type != 'file':
          new_parts.append(part)
          continue
        message_part_id = f"{message_id}:{i}"
        if message_part_id in self._message_to_cache:
          cache_id = self._message_to_cache[message_part_id]
        else:
          cache_id = str(uuid.uuid4())
          self._message_to_cache[message_part_id] = cache_id
        # Replace the part data with a url reference
        new_parts.append(FilePart(
            file=FileContent(
                mimeType=part.file.mimeType,
                uri=f"/message/file/{cache_id}",
            )
        ))
        if cache_id not in self._file_cache:
          self._file_cache[cache_id] = part
      m.parts = new_parts
      rval.append(m)
    return rval

  async def _pending_messages(self):
    return PendingMessageResponse(result=self.manager.get_pending_messages())

  def _list_conversation(self):
    return ListConversationResponse(result=self.manager.conversations)

  def _get_events(self):
    return GetEventResponse(result=self.manager.events)

  def _list_tasks(self):
    return ListTaskResponse(result=self.manager.tasks)

  async def _register_agent(self, request: Request):
    message_data = await request.json()
    url = message_data['params']
    self.manager.register_agent(url)
    return RegisterAgentResponse()

  async def _list_agents(self):
    return ListAgentResponse(result=self.manager.agents)

  def _files(self, file_id):
    if file_id not in self._file_cache:
      raise Exception("file not found")
    part = self._file_cache[file_id]
    if "image" in part.file.mimeType:
      return Response(
          content=base64.b64decode(part.file.bytes),
          media_type=part.file.mimeType)
    return Response(content=part.file.bytes, media_type=part.file.mimeType)
  
  async def _update_api_key(self, request: Request):
    """Update the API key"""
    try:
        data = await request.json()
        api_key = data.get("api_key", "")
        
        if api_key:
            # Update in the manager
            self.update_api_key(api_key)
            return {"status": "success"}
        return {"status": "error", "message": "No API key provided"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

  def _extract_text_from_uploaded_file(self, uploaded_file):
    """Extract text content from uploaded files.
    
    Args:
        uploaded_file: FastAPI UploadFile object
        
    Returns:
        str: Extracted text content or None if extraction fails
    """
    try:
      filename = uploaded_file.filename
      file_content = uploaded_file.file.read()
      
      # Reset file pointer for potential future reads
      uploaded_file.file.seek(0)
      
      # Determine file type from filename
      if filename.lower().endswith('.pdf'):
        return self._extract_pdf_text(file_content)
      elif filename.lower().endswith(('.txt', '.text')):
        return file_content.decode('utf-8')
      elif filename.lower().endswith(('.doc', '.docx')):
        return self._extract_word_text(file_content)
      else:
        print(f"[DEBUG] Server: Unsupported file type: {filename}")
        return None
        
    except Exception as e:
      print(f"[ERROR] Server: Failed to extract text from file: {e}")
      return None
  
  def _extract_pdf_text(self, file_content):
    """Extract text from PDF file content.
    
    Args:
        file_content (bytes): PDF file content
        
    Returns:
        str: Extracted text or None if extraction fails
    """
    try:
      # Try using PyPDF2 first
      try:
        import PyPDF2
        import io
        
        pdf_file = io.BytesIO(file_content)
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        text_content = ""
        
        for page in pdf_reader.pages:
          text_content += page.extract_text() + "\n"
          
        return text_content.strip()
        
      except ImportError:
        print("[DEBUG] Server: PyPDF2 not available for PDF extraction")
        return "PDF text extraction requires PyPDF2 library. Please install it with: pip install PyPDF2"
        
    except Exception as e:
      print(f"[ERROR] Server: Failed to extract PDF text: {e}")
      return None
  
  def _extract_word_text(self, file_content):
    """Extract text from Word document file content.
    
    Args:
        file_content (bytes): Word document file content
        
    Returns:
        str: Extracted text or None if extraction fails
    """
    try:
      import docx
      import io
      
      doc_file = io.BytesIO(file_content)
      doc = docx.Document(doc_file)
      text_content = ""
      
      for paragraph in doc.paragraphs:
        text_content += paragraph.text + "\n"
        
      return text_content.strip()
      
    except ImportError:
      print("[DEBUG] Server: python-docx not available for Word document extraction")
      return "Word document text extraction requires python-docx library. Please install it with: pip install python-docx"
    except Exception as e:
      print(f"[ERROR] Server: Failed to extract Word document text: {e}")
      return None
