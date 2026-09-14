# import os
# import logging
# import time
# from typing import Optional,List
# from dataclasses import dataclass
# from functools import lru_cache
# from openai import OpenAI, RateLimitError, APIError, APITimeoutError
# import tiktoken
#
# logger = logging.getLogger(__name__)
#
#
# @dataclass
# class EnhancementResult:
#     """Container for enhancement results with metadata."""
#     text: str
#     model: str
#     tokens_used: int
#     processing_time: float
#
#
# class RateLimiter:
#     """Simple rate limiter for API calls."""
#
#     def __init__(self, calls_per_minute: int = 60):
#         self.calls_per_minute = calls_per_minute
#         self.calls: List[float] = []
#
#     async def wait_if_needed(self):
#         now = time.time()
#         # Remove calls older than 1 minute
#         self.calls = [t for t in self.calls if now - t < 60]
#
#         if len(self.calls) >= self.calls_per_minute:
#             sleep_time = 60 - (now - self.calls[0])
#             if sleep_time > 0:
#                 time.sleep(sleep_time)
#
#         self.calls.append(time.time())
#
#
# class AIEnhancer:
#     """
#     A class to enhance OCR text using AI models like OpenAI's GPT.
#     Handles rate limiting, retries, and provides detailed metadata.
#     """
#
#     def __init__(
#             self,
#             api_key: str = None,
#             model: str = "gpt-3.5-turbo",
#             max_retries: int = 3,
#             timeout: int = 30,
#             max_tokens: int = 2000,
#             temperature: float = 0.3
#     ):
#         """
#         Initialize the AI Enhancer with configuration.
#
#         Args:
#             api_key: OpenAI API key. If not provided, will try to get from environment.
#             model: The model to use for text enhancement.
#             max_retries: Maximum number of retries for failed API calls.
#             timeout: Request timeout in seconds.
#             max_tokens: Maximum number of tokens to generate.
#             temperature: Controls randomness in the response.
#         """
#         self.api_key = api_key or os.getenv('OPENAI_API_KEY')
#         self.model = model
#         self.max_retries = max_retries
#         self.timeout = timeout
#         self.max_tokens = max_tokens
#         self.temperature = temperature
#
#         if not self.api_key:
#             raise ValueError("OpenAI API key is required. Set OPENAI_API_KEY environment variable.")
#
#         self.client = OpenAI(api_key=self.api_key)
#         self.rate_limiter = RateLimiter(calls_per_minute=60)
#         self.encoding = tiktoken.encoding_for_model(model)
#
#     def count_tokens(self, text: str) -> int:
#         """Count the number of tokens in a text string."""
#         return len(self.encoding.encode(text))
#
#     @lru_cache(maxsize=128)
#     def enhance_text(
#             self,
#             text: str,
#             language: str = 'english',
#             instructions: Optional[str] = None
#     ) -> EnhancementResult:
#         """
#         Enhance the given text using AI with retry logic and rate limiting.
#
#         Args:
#             text: The text to enhance
#             language: The language of the text
#             instructions: Custom instructions for the AI
#
#         Returns:
#             EnhancementResult containing enhanced text and metadata
#
#         Raises:
#             ValueError: If input text is empty or invalid
#             APIError: For persistent API errors after retries
#         """
#         start_time = time.time()
#
#         if not text or not isinstance(text, str) or not text.strip():
#             raise ValueError("Input text cannot be empty")
#
#         prompt = self._build_prompt(text, language, instructions)
#         prompt_tokens = self.count_tokens(prompt)
#
#         if prompt_tokens > 4000:  # Leave room for response
#             raise ValueError(f"Input text is too long ({prompt_tokens} tokens). Maximum is 4000 tokens.")
#
#         last_error = None
#         for attempt in range(self.max_retries + 1):
#             try:
#                 self.rate_limiter.wait_if_needed()
#
#                 response = self.client.chat.completions.create(
#                     model=self.model,
#                     messages=[
#                         {"role": "system", "content": "You are a helpful assistant that improves text quality."},
#                         {"role": "user", "content": prompt}
#                     ],
#                     temperature=self.temperature,
#                     max_tokens=self.max_tokens,
#                     timeout=self.timeout
#                 )
#
#                 enhanced_text = response.choices[0].message.content.strip()
#                 completion_tokens = response.usage.completion_tokens
#                 total_tokens = response.usage.total_tokens
#
#                 return EnhancementResult(
#                     text=enhanced_text,
#                     model=self.model,
#                     tokens_used=total_tokens,
#                     processing_time=time.time() - start_time
#                 )
#
#             except (RateLimitError, APITimeoutError) as e:
#                 wait_time = (2 ** attempt) + 1  # Exponential backoff
#                 logger.warning(
#                     f"Rate limited. Waiting {wait_time} seconds before retry {attempt + 1}/{self.max_retries}")
#                 time.sleep(wait_time)
#                 last_error = e
#             except APIError as e:
#                 logger.error(f"API error on attempt {attempt + 1}: {str(e)}")
#                 last_error = e
#                 break
#             except Exception as e:
#                 logger.error(f"Unexpected error: {str(e)}")
#                 last_error = e
#                 break
#
#         logger.error(f"Failed to enhance text after {self.max_retries} attempts")
#         if last_error:
#             raise last_error
#         raise APIError("Failed to process text enhancement request")
#
#     def _build_prompt(self, text: str, language: str, instructions: Optional[str] = None) -> str:
#         """Build the prompt for the AI model with proper instructions."""
#         prompt = f"""Please improve the following text that was extracted from an OCR system.
# The text is in {language}.
#
# Your tasks:
# 1. Correct any spelling and grammar mistakes
# 2. Fix any formatting issues
# 3. Make the text more readable and natural
# 4. Maintain the original meaning and style
# 5. Preserve any important formatting like dates, numbers, and proper nouns
#
# Important:
# - Only return the improved text, no explanations or notes
# - Preserve the original language and tone
# - Keep technical terms and proper nouns exactly as they are
# - Maintain any numerical values and units exactly as written
#
# Original text:"""
#
#         if instructions:
#             prompt += f"\n\nAdditional instructions: {instructions}"
#
#         prompt += f"\n\n{text}"
#         return prompt
#
#     async def enhance_text_async(
#             self,
#             text: str,
#             language: str = 'english',
#             instructions: Optional[str] = None
#     ) -> EnhancementResult:
#         """
#         Asynchronous version of enhance_text for use with async/await.
#         """
#         # Implementation would be similar to enhance_text but using async/await
#         # This is a placeholder for the async implementation
#         return self.enhance_text(text, language, instructions)
#
#
# class GrokEnhancer:
#     """
#     A class to enhance OCR text using Grok AI (X's AI model).
#     Note: This is a placeholder for when Grok's API becomes publicly available.
#     """
#
#     def __init__(self, api_key: str = None):
#         self.api_key = api_key or os.getenv('GROK_API_KEY')
#         if not self.api_key:
#             raise ValueError("Grok API key is required. Set GROK_API_KEY environment variable.")
#
#     def enhance_text(self, text: str, language: str = 'english') -> str:
#         # TODO: Implement once Grok API is available
#         return text