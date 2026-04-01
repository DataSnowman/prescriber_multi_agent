"""
Contact Lookup Tool

Uses an Azure AI Foundry LLM (ChatGPT) to look up publicly-known prescriber
contact information such as office address, phone number, specialty, and NPI.

The LLM is instructed to use only publicly available knowledge (e.g., NPI
Registry data, known clinic directories). When no information is found it
clearly states so and suggests the NPI Registry for verification.
"""

import os

from agent_framework import (
    Executor,
    WorkflowContext,
    handler,
)
from agent_framework.azure import AzureAIClient
from azure.identity.aio import DefaultAzureCredential

# System prompt that focuses the LLM on factual contact lookup
_CONTACT_SYSTEM_PROMPT = """\
You are a medical-provider contact information assistant.

When given a prescriber's name (and optionally a state or city):
1. Return any **publicly known** contact details you can find, including:
   - Full name and credentials (e.g., MD, DO, NP)
   - Specialty
   - Office phone number
   - Fax number (if known)
   - Office address
   - NPI number (National Provider Identifier)
2. If you are not confident about specific details, say so explicitly.
3. Always recommend verifying information via the NPI Registry:
   https://npiregistry.cms.hhs.gov/
4. Never fabricate phone numbers or addresses. If you don't know, say
   "Not found — please verify via the NPI Registry."
5. Format the output clearly with labeled fields.
"""


class ContactLookupTool(Executor):
    """
    Executor that looks up contact information for a prescriber by
    querying an LLM (ChatGPT via Azure AI Foundry) for publicly
    available provider data.
    """

    def __init__(self, id: str = "contact-lookup-tool"):
        super().__init__(id=id)

    @handler
    async def lookup_contact(self, name: str, ctx: WorkflowContext) -> None:
        """
        Look up contact details for the given prescriber name and yield
        the result.
        """
        print(f"[ContactLookupTool] Looking up: {name}")
        result = await self._lookup(name)
        await ctx.yield_output(f"[Contact Info]\n{result}")

    async def _lookup(self, name: str) -> str:
        """
        Query the LLM for publicly-known contact information about
        the prescriber.
        """
        endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT", "")
        model = os.getenv("FOUNDRY_MODEL_DEPLOYMENT_NAME", "")

        if not endpoint or not model:
            return (
                "Contact lookup unavailable — FOUNDRY_PROJECT_ENDPOINT and "
                "FOUNDRY_MODEL_DEPLOYMENT_NAME are not configured."
            )

        try:
            async with DefaultAzureCredential() as credential:
                agent = AzureAIClient(
                    project_endpoint=endpoint,
                    model_deployment_name=model,
                    credential=credential,
                ).as_agent(
                    name="ContactLookupAgent",
                    instructions=_CONTACT_SYSTEM_PROMPT,
                )

                from agent_framework import Message

                response = await agent.run(
                    [Message(role="user", text=(
                        f"Look up the contact information for prescriber: {name}"
                    ))]
                )
                return response.text or "No information returned."
        except Exception as exc:
            return (
                f"Error looking up contact info: {exc}\n"
                "Tip: Try the NPI Registry at https://npiregistry.cms.hhs.gov/"
            )
