import os
import json
import asyncio
from typing import Dict, List, Optional, Union
import aiohttp
import base64
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class LLMConfig:
    """Configuration for LLM calls"""
    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_tokens: int = 1000
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    response_format: Optional[dict] = None

class LLMClient:
    """Client for making LLM API calls"""

    def __init__(self, config: Optional[LLMConfig] = None):
        """Initialize LLM client with optional config"""
        self.config = config or LLMConfig()
        # Get API key from environment variable
        self.api_key = os.environ.get("INWORLD_API_KEY")
        if not self.api_key:
            raise ValueError("INWORLD_API_KEY environment variable is not set")
        self.base_url = "https://api.inworld.ai/llm/v1alpha/completions:completeChat"
        
        # Import PromptManager here to avoid circular imports
        from .prompt_manager import PromptManager
        self.prompt_manager = PromptManager()

    def _convert_messages(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Convert OpenAI message format to Inworld format"""
        return [
            {
                "role": "MESSAGE_ROLE_USER" if msg["role"] == "user" else "MESSAGE_ROLE_SYSTEM",
                "content": msg["content"]
            }
            for msg in messages
        ]

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        config: Optional[LLMConfig] = None
    ) -> str:
        """
        Make a chat completion API call
        
        Args:
            messages: List of message dicts with role and content
            config: Optional config override for this call
        
        Returns:
            Generated response text
        """
        cfg = config or self.config
        max_retries = 3
        last_exception = None

        for attempt in range(max_retries):
            try:
                # Prepare the request payload
                payload = {
                    "serving_id": {
                        "user_id": "user-test",
                        "model_id": {
                            "model": cfg.model,
                            "service_provider": "SERVICE_PROVIDER_OPENAI"
                        }
                    },
                    "messages": self._convert_messages(messages),
                    "text_generation_config": {
                        "max_tokens": cfg.max_tokens,
                        "stream": False
                    }
                }

                # Add response format if specified
                if cfg.response_format:
                    payload["response_format"] = "RESPONSE_FORMAT_JSON"
                    logger.debug("Requesting JSON response format")

                logger.debug(f"Sending request to Inworld API with payload: {payload}")

                # Make the API request
                async with aiohttp.ClientSession() as session:
                    headers = {
                        "Authorization": f"Basic {self.api_key}",
                        "Content-Type": "application/json"
                    }

                    async with session.post(self.base_url, json=payload, headers=headers) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            # Retry on 5xx or 429; raise immediately on other 4xx
                            if response.status >= 500 or response.status == 429:
                                raise aiohttp.ClientResponseError(
                                    response.request_info, response.history,
                                    status=response.status, message=error_text
                                )
                            logger.error(f"Inworld API error response: {error_text}")
                            raise Exception(f"Inworld API error: {error_text}")

                        result = await response.json()
                        logger.debug(f"Raw Inworld API response: {result}")

                        # Extract response text from the nested structure
                        response_text = result["result"]["choices"][0]["message"]["content"]
                        logger.debug(f"Extracted response text: {response_text}")

                        # If JSON format was requested, validate the response
                        if cfg.response_format:
                            json.loads(response_text)
                            logger.debug("Successfully validated response as JSON")

                        return response_text

            except (json.JSONDecodeError, aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_exception = e
                if attempt < max_retries - 1:
                    delay = 2 ** attempt  # 1s, 2s
                    logger.warning(f"LLM request failed (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                    continue
                logger.error(f"LLM request failed after {max_retries} attempts: {e}", exc_info=True)
                raise Exception(f"Error calling Inworld API: {e}")

            except Exception as e:
                logger.error(f"Error in chat_completion: {e}", exc_info=True)
                raise Exception(f"Error calling Inworld API: {e}")

    async def chat_with_prompt(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        config: Optional[LLMConfig] = None
    ) -> str:
        """
        Simplified method to make a chat completion with just prompts
        
        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt
            config: Optional config override
            
        Returns:
            Generated response text
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        return await self.chat_completion(messages, config)
    
    async def chat_with_template(
        self,
        user_template: str,
        user_context: Dict[str, any],
        system_template: Optional[str] = None,
        system_context: Optional[Dict[str, any]] = None,
        config: Optional[LLMConfig] = None
    ) -> str:
        """
        Make a chat completion using Jinja2 templates
        
        Args:
            user_template: Name of the user prompt template file
            user_context: Context variables for the user template
            system_template: Optional name of the system prompt template file
            system_context: Optional context variables for the system template
            config: Optional config override
            
        Returns:
            Generated response text
        """
        messages = []
        
        # Add system message if template is provided
        if system_template:
            system_prompt = self.prompt_manager.render_template(
                system_template, 
                **(system_context or {})
            )
            messages.append({"role": "system", "content": system_prompt})
        
        # Add user message
        user_prompt = self.prompt_manager.render_template(
            user_template,
            **user_context
        )
        messages.append({"role": "user", "content": user_prompt})
        
        return await self.chat_completion(messages, config)
