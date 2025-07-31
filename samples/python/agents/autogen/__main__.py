import logging

import click
from common.server import A2AServer
from common.types import AgentCapabilities, AgentCard, AgentSkill
from common.utils.push_notification_auth import PushNotificationSenderAuth
from dotenv import load_dotenv

from agents.autogen.task_manager import TaskManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()


@click.command()
@click.option("--host", default="localhost")
@click.option("--port", default=10018)
def main(host, port):
    """Starts the AutoGen Agent server using A2A."""
    # Build the agent card
    capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
    skill_candidate_rating = AgentSkill(
        id="autogen_rating_agent",
        name="AutoGen Candidate Rating System",
        description=(
            "Multi-agent candidate rating system for SAP AI Scientist positions. "
            "Uses Tech Rater, Inclusion Rater, and Reporter agents to provide "
            "comprehensive evaluation of technical expertise and diversity background."
        ),
        tags=["rating", "candidate", "multi-agent", "technical", "inclusion"],
        examples=[
            "Rate this candidate: John Walker; 3 years SRE at Apple, AI enthusiast, single dad.", 
            "Evaluate candidate: Maria Garcia; PhD in ML, 5 years at Google, active in women in tech.",
            "Assess this profile: Alex Chen; Full-stack developer, open source contributor, bilingual."
        ]
    )

    agent_card = AgentCard(
        name="AutoGen Candidate Rating Agent",
        description=(
            "Advanced multi-agent rating system for SAP AI Scientist candidates. "
            "Evaluates technical expertise and diversity/inclusion background using "
            "specialized Tech Rater, Inclusion Rater, and Reporter agents."
        ),
        url=f"http://{host}:{port}/",
        version="1.0.0",
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
        capabilities=capabilities,
        skills=[skill_candidate_rating],
    )

    # Prepare push notification system
    notification_sender_auth = PushNotificationSenderAuth()
    notification_sender_auth.generate_jwk()

    # Create the server
    task_manager = TaskManager(notification_sender_auth=notification_sender_auth)
    server = A2AServer(agent_card=agent_card, task_manager=task_manager, host=host, port=port)
    server.app.add_route("/.well-known/jwks.json", notification_sender_auth.handle_jwks_endpoint, methods=["GET"])

    logger.info(f"Starting the AutoGen candidate rating agent server on {host}:{port}")
    server.start()


if __name__ == "__main__":
    main()