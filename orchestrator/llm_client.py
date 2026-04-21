"""
LLM Client

Wrapper around the Anthropic API. Handles:
  - Constructing messages with system prompt + context + user message
  - Retries with exponential backoff
  - Logging requests/responses to agent history
  - Tool-use loop (for the Orchestrator agent)
"""

from __future__ import annotations

import os
import time
import logging
from typing import Any, Callable

try:
    import anthropic
except ImportError:
    anthropic = None  # type: ignore

from .config import Config
from .context_assembler import ContextAssembler
from .memory_manager import MemoryManager

logger = logging.getLogger("ai-factory.llm")


class LLMClient:
    """Calls the Anthropic API with assembled context."""

    def __init__(self, config: Config, context_assembler: ContextAssembler, memory: MemoryManager):
        self.config = config
        self.assembler = context_assembler
        self.memory = memory
        self._client = None

    @property
    def client(self):
        if self._client is None:
            if anthropic is None:
                raise ImportError(
                    "The 'anthropic' package is required. "
                    "Install it with: pip install anthropic"
                )
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise EnvironmentError(
                    "ANTHROPIC_API_KEY environment variable is not set"
                )
            self._client = anthropic.Anthropic(api_key=api_key)
        return self._client

    # ── Standard one-shot agent run ─────────────────────────────────────

    def run_agent(
        self,
        agent_id: str,
        user_message: str,
        project_id: str | None = None,
        tier: str = "L1",
        task_description: str = "",
        extra_context: str = "",
    ) -> str:
        """Send a message to an agent and get a response (no tool use)."""
        agent_cfg = self.config.agent_config(agent_id)

        base_prompt = agent_cfg.get("system_prompt", "You are a helpful agent.")
        context = self.assembler.assemble(
            agent_id=agent_id,
            project_id=project_id,
            task_description=task_description,
            tier=tier,
        )
        system_prompt = f"{base_prompt}\n\n{context}"
        if extra_context:
            system_prompt += f"\n\n{extra_context}"

        model_cfg = agent_cfg.get("model", {})
        model = model_cfg.get("name", self.config.model_default)
        max_tokens = model_cfg.get("max_tokens", self.config.max_tokens)
        temperature = model_cfg.get("temperature", self.config.temperature)

        retry_attempts = self.config.factory.get("api", {}).get("retry_attempts", 3)
        retry_delay = self.config.factory.get("api", {}).get("retry_delay_seconds", 2)

        response_text = ""
        for attempt in range(retry_attempts):
            try:
                logger.info(f"Calling {model} for {agent_id} (attempt {attempt + 1})")
                response = self.client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_message}],
                )
                response_text = response.content[0].text
                break
            except Exception as e:
                logger.warning(f"API call failed (attempt {attempt + 1}): {e}")
                if attempt < retry_attempts - 1:
                    time.sleep(retry_delay * (2 ** attempt))
                else:
                    raise

        self.memory.append_history(agent_id, "user", user_message)
        self.memory.append_history(agent_id, "assistant", response_text)

        return response_text

    # ── Tool-use loop (for the Orchestrator) ────────────────────────────

    def run_agent_with_tools(
        self,
        agent_id: str,
        user_message: str,
        tools: list[dict],
        tool_dispatcher: Callable[[str, dict], str],
        conversation_history: list[dict] | None = None,
        project_id: str | None = None,
        tier: str = "L1",
        max_iterations: int = 25,
        on_tool_call: Callable[[str, dict, str], None] | None = None,
    ) -> tuple[str, list[dict]]:
        """
        Run an agent that can call tools.

        Loops until the agent produces a final text response (no more tool calls)
        or until max_iterations is hit.

        Returns:
            (final_text_response, updated_conversation_history)
        """
        agent_cfg = self.config.agent_config(agent_id)

        base_prompt = agent_cfg.get("system_prompt", "You are a helpful agent.")
        context = self.assembler.assemble(
            agent_id=agent_id,
            project_id=project_id,
            tier=tier,
        )
        system_prompt = f"{base_prompt}\n\n{context}"

        model_cfg = agent_cfg.get("model", {})
        model = model_cfg.get("name", self.config.model_default)
        max_tokens = model_cfg.get("max_tokens", self.config.max_tokens)
        temperature = model_cfg.get("temperature", self.config.temperature)

        # Build the message history
        messages: list[dict] = list(conversation_history or [])
        if user_message:
            messages.append({"role": "user", "content": user_message})
            self.memory.append_history(agent_id, "user", user_message)

        final_text = ""

        for iteration in range(max_iterations):
            logger.info(
                f"Orchestrator iteration {iteration + 1}/{max_iterations} "
                f"(messages: {len(messages)})"
            )

            response = self.client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                tools=tools,
                messages=messages,
            )

            assistant_content = response.content
            messages.append({"role": "assistant", "content": assistant_content})

            text_parts = [
                block.text for block in assistant_content
                if block.type == "text"
            ]
            tool_uses = [
                block for block in assistant_content
                if block.type == "tool_use"
            ]

            if text_parts:
                final_text = "\n".join(text_parts)

            if not tool_uses:
                logger.info("Orchestrator: final response (no more tool calls)")
                break

            tool_results = []
            for tool_use in tool_uses:
                name = tool_use.name
                tool_input = tool_use.input
                logger.info(f"Tool call: {name}({tool_input})")
                result = tool_dispatcher(name, tool_input)
                logger.info(f"Tool result: {result[:200]}...")

                if on_tool_call:
                    try:
                        on_tool_call(name, tool_input, result)
                    except Exception as e:
                        logger.warning(f"on_tool_call callback raised: {e}")

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": result,
                })

            messages.append({"role": "user", "content": tool_results})

            if response.stop_reason != "tool_use":
                logger.info(f"Stopping loop: stop_reason={response.stop_reason}")
                break
        else:
            logger.warning(f"Hit max_iterations={max_iterations}, stopping")

        if final_text:
            self.memory.append_history(agent_id, "assistant", final_text)

        return final_text, messages

    # ── Utility ─────────────────────────────────────────────────────────

    def simple_completion(self, prompt: str, model: str | None = None) -> str:
        """One-shot completion without agent context."""
        model = model or self.config.model_default
        response = self.client.messages.create(
            model=model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
