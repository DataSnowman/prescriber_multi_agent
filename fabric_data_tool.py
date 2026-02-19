"""
Fabric Data Agent Tool

Wraps the existing FabricDataAgentClient as an Agent Framework Executor
so it can be used as a tool node in a multi-agent workflow.
"""

import os
import sys

from agent_framework import (
    ChatMessage,
    Executor,
    WorkflowContext,
    handler,
)
from typing_extensions import Never

# Add the sibling project to the Python path so we can import the client
FABRIC_CLIENT_DIR = os.path.join(os.path.dirname(__file__), "..", "fabric_data_agent_client")
if FABRIC_CLIENT_DIR not in sys.path:
    sys.path.insert(0, FABRIC_CLIENT_DIR)

from fabric_data_agent_client import FabricDataAgentClient


class FabricDataTool(Executor):
    """
    Executor that queries a Microsoft Fabric Data Agent for prescriber/drug data.

    This wraps the FabricDataAgentClient you already built and exposes it
    as a node in an Agent Framework workflow.
    """

    client: FabricDataAgentClient

    def __init__(self, id: str = "fabric-data-tool"):
        tenant_id = os.getenv("TENANT_ID")
        data_agent_url = os.getenv("DATA_AGENT_URL")

        if not tenant_id or not data_agent_url:
            raise ValueError(
                "TENANT_ID and DATA_AGENT_URL must be set in environment or .env"
            )

        self.client = FabricDataAgentClient(
            tenant_id=tenant_id,
            data_agent_url=data_agent_url,
        )
        super().__init__(id=id)

    @handler
    async def query_data(self, question: str, ctx: WorkflowContext[Never, str]) -> None:
        """
        Send a natural-language question to the Fabric Data Agent and yield
        the response as workflow output.
        """
        print(f"[FabricDataTool] Querying: {question}")
        response = self.client.ask(question, thread_name="multi-agent-session")
        await ctx.yield_output(f"[Prescriber Data]\n{response}")
