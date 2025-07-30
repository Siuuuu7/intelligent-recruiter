import os
import httpx
import logging
import base64
from typing import Any, AsyncIterable, Annotated, Literal, TYPE_CHECKING

from dotenv import load_dotenv

from pydantic import BaseModel

from semantic_kernel.agents import ChatCompletionAgent, ChatHistoryAgentThread
from semantic_kernel.connectors.ai.open_ai import (
    AzureChatCompletion,
    AzureChatPromptExecutionSettings
)
from semantic_kernel.contents import (
    FunctionCallContent, FunctionResultContent, StreamingChatMessageContent, StreamingTextContent,
    ChatMessageContent, TextContent
)
from semantic_kernel.functions.kernel_arguments import KernelArguments
from semantic_kernel.functions import kernel_function

if TYPE_CHECKING:
    from semantic_kernel.contents import ChatMessageContent

logger = logging.getLogger(__name__)

load_dotenv()

class ResponseFormat(BaseModel):
    """A Response Format model to direct how the model should respond."""
    status: Literal["input_required", "completed", "error"] = "input_required"
    message: str

# endregion

# region Semantic Kernel Agent

class HRAgent:
    """Wraps Semantic Kernel-based agents to handle HR related tasks including resume analysis."""

    agent: ChatCompletionAgent
    thread: ChatHistoryAgentThread = None
    SUPPORTED_CONTENT_TYPES = ["text", "text/plain", "application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]

    def __init__(self):

        # currency_exchange_agent = ChatCompletionAgent(
        #     service=AzureChatCompletion(
        #         api_key=os.getenv("AZURE_OPENAI_TOKEN"),
        #         endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        #         deployment_name='gpt-4o',
        #     ),
        #     name="CurrencyExchangeAgent",
        #     instructions=(
        #         "You specialize in handling currency-related requests from travelers. "
        #         "This includes providing current exchange rates, converting amounts between different currencies, "
        #         "explaining fees or charges related to currency exchange, and giving advice on the best practices for exchanging currency. "
        #         "Your goal is to assist travelers promptly and accurately with all currency-related questions."
        #     ),
        #     plugins=[CurrencyPlugin()],
        # )

        # Define an ActivityPlannerAgent to handle activity-related tasks
        rating_agent = ChatCompletionAgent(
            service=AzureChatCompletion(
                api_key=os.getenv("AZURE_OPENAI_TOKEN"),
                endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
                deployment_name='gpt-4o',
            ),
            name="RatingAgent",
            instructions=(
                "Rate a candidate for AI Scientist of SAP. Focus on the expertise and diversity background."
            ),
        )

        # Define the main TravelManagerAgent to delegate tasks to the appropriate agents
        self.agent = ChatCompletionAgent(
            service=AzureChatCompletion(
                api_key=os.getenv("AZURE_OPENAI_TOKEN"),
                endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
                deployment_name='gpt-4o',
                api_version="2025-03-01-preview",  # Ensure we use a version that supports file uploads
            ),
            name="HRAgent",
            instructions=(
                "Your role is to carefully analyze candidate resumes and provide detailed ratings. "
                "When analyzing a resume, evaluate the following criteria:\n"
                "1. Technical Skills & Expertise (30%): Assess relevant technical skills, programming languages, frameworks, and domain knowledge\n"
                "2. Experience & Career Progression (25%): Evaluate work experience, career growth, and project complexity\n"
                "3. Education & Certifications (20%): Consider educational background, relevant degrees, and professional certifications\n"
                "4. Diversity & Background (15%): Assess diverse perspectives, international experience, and unique backgrounds\n"
                "5. Communication & Leadership (10%): Evaluate leadership roles, team collaboration, and communication skills\n\n"
                "Provide a structured rating with:\n"
                "- Overall Score (1-10)\n"
                "- Individual category scores\n"
                "- Key strengths and areas for improvement\n"
                "- Recommendation (Strong Hire/Hire/Maybe/No Hire)\n"
                "- Brief justification for the rating"
            ),
            plugins=[rating_agent],
            arguments=KernelArguments(
                settings=AzureChatPromptExecutionSettings(
                    response_format=ResponseFormat,
                )
            ),
        )


    async def invoke(self, user_input: str, session_id: str, file_path: str = None) -> dict[str, Any]:
        """Handle synchronous tasks (like tasks/send).
        
        Args:
            user_input (str): User input message.
            session_id (str): Unique identifier for the session.
            file_path (str, optional): Path to uploaded file (resume).

        Returns:
            dict: A dictionary containing the content, task completion status, and user input requirement.
        """
        await self._ensure_thread_exists(session_id)

        # HR agent now only processes text - file processing handled by server
        response = await self.agent.get_response(
            messages=user_input,
            thread=self.thread,
        )
        return self._get_agent_response(response.content)

    async def stream(self, user_input: str, session_id: str, file_path: str = None) -> AsyncIterable[dict[str, Any]]:
        """For streaming tasks (like tasks/sendSubscribe), we yield partial progress using SK agent's invoke_stream.

        Args:
            user_input (str): User input message.
            session_id (str): Unique identifier for the session.
            file_path (str, optional): Path to uploaded file (resume).

        Yields:
            dict: A dictionary containing the content, task completion status, and user input requirement.
        """
        await self._ensure_thread_exists(session_id)
        
        # HR agent now only processes text - file processing handled by server
        messages_input = user_input
        
        chunks: list[StreamingChatMessageContent] = []

        # For the sample, to avoid too many messages, only show one "in-progress" message for each task
        tool_call_in_progress = False
        message_in_progress = False
        async for response_chunk in self.agent.invoke_stream(
            messages=messages_input, thread=self.thread,
        ):
            if any(isinstance(item, (FunctionCallContent, FunctionResultContent)) for item in response_chunk.items):
                if not tool_call_in_progress:
                    yield {
                        "is_task_complete": False,
                        "require_user_input": False,
                        "content": "Processing the trip plan (with plugins)...",
                    }
                    tool_call_in_progress = True
            elif any(isinstance(item, StreamingTextContent) for item in response_chunk.items):
                if not message_in_progress:
                    yield {
                        "is_task_complete": False,
                        "require_user_input": False,
                        "content": "Rating the candidate",
                    }
                    message_in_progress = True

                chunks.append(response_chunk.message)

        full_message = sum(chunks[1:], chunks[0])
        yield self._get_agent_response(full_message)

    def _get_agent_response(self, message: "ChatMessageContent") -> dict[str, Any]:
        """Extracts the structured response from the agent's message content.
        
        Args:
            message (ChatMessageContent): The message content from the agent.

        Returns:
            dict: A dictionary containing the content, task completion status, and user input requirement.
        """
        structured_response = ResponseFormat.model_validate_json(message.content)

        default_response = {
            "is_task_complete": False,
            "require_user_input": True,
            "content": "We are unable to process your request at the moment. Please try again.",
        }

        if isinstance(structured_response, ResponseFormat):
            response_map = {
                "input_required": {"is_task_complete": False, "require_user_input": True},
                "error": {"is_task_complete": False, "require_user_input": True},
                "completed": {"is_task_complete": True, "require_user_input": False},
            }

            response = response_map.get(structured_response.status)
            if response:
                return {**response, "content": structured_response.message}

        return default_response
    
    def _get_file_info(self, file_path: str) -> dict[str, str]:
        """Get file information for uploaded files.
        
        Args:
            file_path (str): Path to the uploaded file.
            
        Returns:
            dict: File information including name and type.
        """
        return {
            "name": os.path.basename(file_path),
            "path": file_path
        }
    
    def _get_mime_type(self, file_path: str) -> str:
        """Get MIME type for uploaded files.
        
        Args:
            file_path (str): Path to the uploaded file.
            
        Returns:
            str: MIME type of the file.
        """
        file_ext = os.path.splitext(file_path)[1].lower()
        mime_types = {
            '.pdf': 'application/pdf',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.doc': 'application/msword',
            '.txt': 'text/plain'
        }
        return mime_types.get(file_ext, 'application/octet-stream')
    
    async def _ensure_thread_exists(self, session_id: str) -> None:
        """Ensure the thread exists for the given session ID.
        
        Args:
            session_id (str): Unique identifier for the session.
        """
        # Replace check with self.thread.id when 
        # https://github.com/microsoft/semantic-kernel/issues/11535 is fixed
        if self.thread is None or getattr(self, "thread_id", None) != session_id:
            if self.thread:
                await self.thread.delete()
            self.thread = ChatHistoryAgentThread()
            self.thread_id = session_id
# endregion