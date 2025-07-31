import json
import os
from collections.abc import AsyncIterable
from typing import Any, Literal

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.ui import Console
from autogen_agentchat.teams import Swarm
from autogen_agentchat.conditions import TextMentionTermination
from autogen_ext.models.openai import AzureOpenAIChatCompletionClient

JD_TECH = '''SAP AI Scientist; Key Technical Responsibilities

LLM Application Development: Design, develop, and optimize large language model applications for enterprise use cases; research and implement state-of-the-art NLP techniques including fine-tuning, prompt engineering, and retrieval-augmented generation (RAG)
Full-Stack Development: Build end-to-end AI-powered applications from concept to production deployment; develop robust APIs, microservices, and intuitive user interfaces using modern web technologies
Research & Innovation: Conduct applied research to solve complex business problems using AI/ML techniques; publish findings and file patents for innovative solutions
System Integration: Collaborate with product teams to integrate LLM capabilities into SAP's business applications; implement scalable data pipelines and model serving infrastructure

Technical Qualifications

Education: PhD or Master's degree in Computer Science, AI/ML, Mathematics, or related field
LLM Expertise: Deep understanding of transformer architectures, attention mechanisms, and modern NLP techniques
Programming: Proficiency in Python, with experience in PyTorch/TensorFlow, Hugging Face, and LangChain
Full-Stack Skills: Strong skills in web development (JavaScript/TypeScript, React/Vue.js, Node.js) and cloud platforms (AWS/Azure/GCP)
Data Systems: Experience with SQL/NoSQL databases, vector databases for embedding storage
DevOps: Familiarity with containerization (Docker/Kubernetes), CI/CD pipelines, and MLOps practices
Fast Learning Ability: Demonstrated capacity to quickly master new technologies, frameworks, and research domains'''

JD_INCLUSION = '''SAP AI Scientist; Key Inclusion Responsibilities

Foster Diverse Perspectives: Actively promote and support diverse viewpoints in team discussions, research directions, and solution development
Mentorship & Development: Guide junior team members from various backgrounds, ensuring equal growth opportunities and knowledge sharing
Bias-Aware AI Development: Identify, assess, and mitigate potential biases in AI systems and algorithms throughout the development lifecycle
Accessible Design: Consider accessibility and usability for diverse user groups when designing AI applications and interfaces
Cross-Cultural Collaboration: Facilitate effective communication and collaboration across different cultural contexts within global teams

Inclusion Qualifications

Cultural Competency: Demonstrated awareness and respect for different cultural backgrounds, working styles, and communication preferences
Inclusive Leadership: Experience creating psychologically safe environments where all team members feel valued and heard
Bias Recognition: Understanding of various types of bias (algorithmic, cognitive, cultural) and proven ability to implement mitigation strategies
Communication Skills: Excellent verbal and written communication in both English and Chinese, with ability to adapt communication style for diverse audiences
Collaborative Mindset: Track record of successful cross-functional teamwork and building bridges across different groups and perspectives'''

DEFAULT_API_VERSION = "2025-03-01-preview"
MODEL = "gpt-4o"
load_dotenv()


class ResponseFormat(BaseModel):
    """Respond to the user in this format."""

    status: Literal['input_required', 'completed', 'error'] = 'input_required'
    message: str


class AutogenAgent:
    """A currency conversion agent using AutoGen."""

    SUPPORTED_CONTENT_TYPES = ['text', 'text/plain']

    def __init__(self):
        self.client = self._get_client()
        self.agents = self._create_agents()
        self.team = self._create_team()
        self.tools = [self.get_exchange_rate]
        self.session_data: dict[str, Any] = {}

    def _get_client(self):
        return AzureOpenAIChatCompletionClient(
            model=MODEL,
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_key=os.getenv("AZURE_OPENAI_TOKEN"),
            azure_deployment=MODEL,
            api_version=DEFAULT_API_VERSION,
        )

    def _create_agents(self):
        tech_rater = AssistantAgent(
            'Tech Rater',
            model_client=self.client,
            handoffs=['Tech Rater'],
            description='Rate the technical expertise of the candidate.',
            system_message=f'''You are a technical recruiter for the following job position:{JD_TECH}; 
            Your task is to evaluate the technical expertise of candidates based on the resume as well as the interview talks and provide a rating from 1 to 10 as well as the reasons.
            Be aware that some candidates may exaggerate their technical skills, for example, a candidate may claim to be a "Full Stack Developer" without any specific projects or technologies to back that claim.
            ''',
        )
        inclusion_rater = AssistantAgent(
            'Inclusion Rater',
            model_client=self.client,
            handoffs=['Inclusion Rater'],
            description='Rate the inclusion and diversity background of the candidate.',
            system_message=f'''You are a diversity and inclusion recruiter for the following job position:{JD_INCLUSION}; 
            Your task is to evaluate the inclusion and diversity background of candidates based on the resume as well as the interview talks and provide a rating from 1 to 10 as well as the reasons.
            Some candidates may exaggerate their diversity background, for example, a candidate may claim to be a "Proud Ally" without any specific actions or contributions to support that claim. Be aware.
            ''',
        )
        reporter =  AssistantAgent(
            'Reporter',
            model_client=self.client,
            handoffs=['Reporter'],
            description = 'Report the final rating of the candidate.',
            system_message='''You are a reporter for the following job position: SAP AI Scientist;
            Your task is to summarize the ratings from the Tech Rater and Inclusion Rater, and provide a final report on the candidate.
            ''',
        )
        return [
            tech_rater,
            inclusion_rater,
            reporter,
        ]
    def _create_team(self):
        team = Swarm(
            name='HRAgentTeam',
            participants=self.agents,
            termination_condition=TextMentionTermination("TERMINATE")
,
        )
        return team

    def _format_response(self, response: str) -> dict[str, Any]:
        try:
            response_lines = response.strip().split('\n')
            json_content = None
            for line in response_lines:
                if '{"status":' in line or '"status":' in line:
                    try:
                        start = line.find('{')
                        end = line.rfind('}') + 1
                        content = line[start:end]
                        parsed = json.loads(content)
                        if 'status' in parsed and 'message' in parsed:
                            status = parsed['status']
                            message = parsed['message']
                            return {
                                'is_task_complete': status == 'completed',
                                'require_user_input': status == 'input_required',
                                'content': message,
                            }
                    except json.JSONDecodeError:
                        continue
            if 'i need more information' in response.lower():
                return {'is_task_complete': False, 'require_user_input': True, 'content': response}
            return {'is_task_complete': True, 'require_user_input': False, 'content': response}
        except Exception as e:
            return {'is_task_complete': False, 'require_user_input': True,
                    'content': f'Error processing response: {e}\nOriginal response: {response}'}

    async def invoke(self, query: str, sessionId: str) -> dict[str, Any]:
        if sessionId not in self.session_data:
            self.session_data[sessionId] = []
        # for assistant in self.agents:
        #     assistant.reset()
        self.team.reset()
        result = await self.team.run(query)
        response = result.messages[-1].content if hasattr(result, 'messages') else "I couldn't process your request."
        self.session_data[sessionId].append({'role': 'user', 'content': query})
        self.session_data[sessionId].append({'role': 'assistant', 'content': response})
        return self._format_response(response)

    async def stream(self, query: str, sessionId: str) -> AsyncIterable[dict[str, Any]]:
        if sessionId not in self.session_data:
            self.session_data[sessionId] = []
        self.session_data[sessionId].append({'role': 'user', 'content': query})
        # self.assistant.reset()
        self.team.reset()
        yield {'is_task_complete': False, 'require_user_input': False, 'content': 'Looking up the exchange rates...'}
        self.team.initiate_chat(self.assistant, message=query, clear_history=False)
        yield {'is_task_complete': False, 'require_user_input': False, 'content': 'Processing the exchange rates..'}
        chat_history = self.assistant.chat_messages[self.team.name]
        response = chat_history[-1]['content'] if chat_history else "I couldn't process your request."
        self.session_data[sessionId].append({'role': 'assistant', 'content': response})
        yield self._format_response(response)