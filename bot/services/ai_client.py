"""
AI Client Service - OpenAI-compatible API client.
Works with NanoGPT, OpenAI, Ollama, LM Studio, and other compatible endpoints.
"""

import asyncio
import base64
import io
from typing import Optional, List, Dict, Any

import aiohttp
from PIL import Image
import PyPDF2

from bot.utils.logging import get_logger

logger = get_logger(__name__)


class AIClient:
    """
    OpenAI-compatible API client for chat completions.
    Supports text and vision models.
    """
    
    def __init__(self, api_key: str, base_url: str = "https://api.nano-gpt.com/v1", model: str = "gpt-4o-mini"):
        """
        Initialize the AI client.
        
        Args:
            api_key: API key for authentication
            base_url: Base URL for the API (defaults to NanoGPT)
            model: Model name to use for completions
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.model = model
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create the aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
            )
        return self._session
    
    async def close(self):
        """Close the client session."""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def generate_response(
        self,
        system_prompt: str,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        image: Optional[Image.Image] = None,
        max_tokens: int = 2048,
        temperature: float = 0.7
    ) -> str:
        """
        Generate a chat completion response.
        
        Args:
            system_prompt: The system prompt defining the bot's personality
            user_message: The user's message
            conversation_history: Optional list of previous messages
            image: Optional PIL Image for vision models
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            
        Returns:
            The generated response text
        """
        messages = [{"role": "system", "content": system_prompt}]
        
        # Add conversation history if provided
        if conversation_history:
            messages.extend(conversation_history)
        
        # Build user message content
        if image:
            # Vision request with image
            user_content = await self._build_vision_content(user_message, image)
        else:
            user_content = user_message
        
        messages.append({"role": "user", "content": user_content})
        
        try:
            session = await self._get_session()
            
            payload = {
                "model": self.model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature
            }
            
            async with session.post(
                f"{self.base_url}/chat/completions",
                json=payload
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"API error {response.status}: {error_text}")
                    return f"API error: {response.status}"
                
                data = await response.json()
                
                if "choices" in data and len(data["choices"]) > 0:
                    return data["choices"][0]["message"]["content"]
                else:
                    logger.warning("Empty response from API")
                    return ""
                    
        except aiohttp.ClientError as e:
            logger.error(f"HTTP error in AI request: {e}")
            return f"Connection error: {e}"
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return f"Error: {e}"
    
    async def _build_vision_content(self, text: str, image: Image.Image) -> List[Dict[str, Any]]:
        """Build content array for vision request."""
        # Convert image to base64
        buffer = io.BytesIO()
        
        # Convert to RGB if necessary
        if image.mode not in ['RGB', 'L']:
            image = image.convert('RGB')
        
        image.save(buffer, format='JPEG', quality=85)
        image_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        
        return [
            {"type": "text", "text": text},
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{image_b64}"
                }
            }
        ]


async def download_image(url: str) -> Optional[Image.Image]:
    """
    Download and process an image from a URL.
    
    Args:
        url: The URL to download from
        
    Returns:
        PIL Image or None if download failed
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    image_data = await response.read()
                    image = Image.open(io.BytesIO(image_data))
                    if image.mode not in ['RGB', 'L']:
                        image = image.convert('RGB')
                    return image
    except Exception as e:
        logger.error(f"Error downloading image: {e}")
    return None


async def download_pdf(url: str) -> Optional[str]:
    """
    Download and extract text from a PDF.
    
    Args:
        url: The URL to download from
        
    Returns:
        Extracted text or None if download/extraction failed
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    pdf_data = await response.read()
                    text = ""
                    try:
                        pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_data))
                        for page in pdf_reader.pages:
                            text += page.extract_text() or ""
                    except PyPDF2.errors.PdfReadError:
                        return "[Error reading PDF content]"
                    
                    # Truncate if too long
                    max_length = 3000
                    if len(text) > max_length:
                        text = text[:max_length] + "\n[...PDF truncated...]"
                    return text
    except Exception as e:
        logger.error(f"Error processing PDF: {e}")
    return None
