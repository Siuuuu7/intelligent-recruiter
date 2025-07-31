import os
import logging
from typing import Any, AsyncIterable, Literal, TYPE_CHECKING

from dotenv import load_dotenv

from pydantic import BaseModel

from semantic_kernel.agents import ChatCompletionAgent, ChatHistoryAgentThread
from semantic_kernel.connectors.ai.open_ai import (
    AzureChatCompletion,
    AzureChatPromptExecutionSettings
)
from semantic_kernel.contents import (
    FunctionCallContent, FunctionResultContent, StreamingChatMessageContent, StreamingTextContent,
    ChatMessageContent
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

class BackgroundCheckPlugin:
    """Plugin containing background verification tools."""
    
    @kernel_function(
        description="Verify if a university is legitimate and accredited",
        name="verify_university"
    )
    def verify_university(self, university_name: str) -> str:
        """Verify university legitimacy - dummy implementation for testing."""
        # Dummy implementation - return True for known universities
        legitimate_universities = {
            "harvard university", "stanford university", "mit", "university of california",
            "tsinghua university", "peking university", "national university of singapore",
            "university of tokyo", "eth zurich", "university of cambridge", "university of oxford"
        }
        
        university_lower = university_name.lower()
        is_legitimate = any(known_uni in university_lower for known_uni in legitimate_universities)
        
        return f"University '{university_name}' verification: {'VERIFIED' if is_legitimate else 'NOT VERIFIED'}"
    
    @kernel_function(
        description="Verify if a company exists and is legitimate",
        name="verify_company"
    )
    def verify_company(self, company_name: str) -> str:
        """Verify company legitimacy - dummy implementation for testing."""
        # Dummy implementation - return True for known companies
        legitimate_companies = {
            "google", "microsoft", "apple", "amazon", "meta", "netflix", "tesla",
            "sap", "oracle", "ibm", "salesforce", "adobe", "nvidia", "intel",
            "alibaba", "tencent", "baidu", "bytedance"
        }
        
        company_lower = company_name.lower()
        is_legitimate = any(known_company in company_lower for known_company in legitimate_companies)
        
        return f"Company '{company_name}' verification: {'VERIFIED' if is_legitimate else 'NOT VERIFIED'}"
    
    @kernel_function(
        description="Verify if a project or achievement is legitimate",
        name="verify_project"
    )
    def verify_project(self, project_name: str) -> str:
        """Verify project legitimacy - dummy implementation for testing."""
        # Dummy implementation - flag suspicious projects
        suspicious_keywords = {
            "world champion", "nobel prize", "invented", "discovered", "revolutionary breakthrough",
            "patent pending", "proprietary algorithm", "ai breakthrough", "solved climate change"
        }
        
        project_lower = project_name.lower()
        is_suspicious = any(keyword in project_lower for keyword in suspicious_keywords)
        
        return f"Project '{project_name}' verification: {'NEEDS FURTHER REVIEW' if is_suspicious else 'PLAUSIBLE'}"


class BackgroundCheckAgent:
    """Background verification agent for candidate screening."""

    agent: ChatCompletionAgent
    thread: ChatHistoryAgentThread = None
    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

    def __init__(self):

        # Initialize the main background check agent
        self.agent = ChatCompletionAgent(
            service=AzureChatCompletion(
                api_key=os.getenv("AZURE_OPENAI_TOKEN"),
                endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
                deployment_name='gpt-4o',
                api_version="2025-03-01-preview",
            ),
            name="BackgroundCheckAgent",
            instructions=(
                "You are a background verification specialist responsible for validating candidate information. "
                "When analyzing a resume or candidate information, you must:\n\n"
                "1. VERIFY UNIVERSITIES: Use verify_university tool to check if educational institutions are legitimate and accredited\n"
                "2. VERIFY COMPANIES: Use verify_company tool to confirm employment history at legitimate organizations\n"
                "3. VERIFY PROJECTS: Use verify_project tool to assess the plausibility of claimed projects and achievements\n\n"
                "Your verification process should:\n"
                "- Extract all universities, companies, and significant projects mentioned\n"
                "- Use the appropriate verification tools for each item\n"
                "- Provide a comprehensive background check report\n"
                "- Flag any suspicious or unverifiable claims\n"
                "- Give an overall verification status: VERIFIED, PARTIALLY VERIFIED, or NOT VERIFIED\n\n"
                "Always use the verification tools before making conclusions."
            ),
            plugins=[BackgroundCheckPlugin()],
            arguments=KernelArguments(
                settings=AzureChatPromptExecutionSettings(
                    response_format=ResponseFormat,
                )
            ),
        )


    async def invoke(self, user_input: str, session_id: str) -> dict[str, Any]:
        """Handle synchronous background check tasks.
        
        Args:
            user_input (str): User input message containing candidate information (including extracted file content).
            session_id (str): Unique identifier for the session.

        Returns:
            dict: A dictionary containing the verification results, task completion status, and user input requirement.
        """
        await self._ensure_thread_exists(session_id)

        # Background check agent processes text input for verification
        response = await self.agent.get_response(
            messages=user_input,
            thread=self.thread,
        )
        return self._get_agent_response(response.content)

    async def stream(self, user_input: str, session_id: str) -> AsyncIterable[dict[str, Any]]:
        """For streaming background check tasks, yield partial progress.

        Args:
            user_input (str): User input message containing candidate information (including extracted file content).
            session_id (str): Unique identifier for the session.

        Yields:
            dict: A dictionary containing the verification progress, task completion status, and user input requirement.
        """
        await self._ensure_thread_exists(session_id)
        
        # Background check agent processes text input - file processing handled by server
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
                        "content": "Running background verification checks...",
                    }
                    tool_call_in_progress = True
            elif any(isinstance(item, StreamingTextContent) for item in response_chunk.items):
                if not message_in_progress:
                    yield {
                        "is_task_complete": False,
                        "require_user_input": False,
                        "content": "Analyzing candidate background information",
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
            "content": "Unable to complete background verification at the moment. Please try again.",
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