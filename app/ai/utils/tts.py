"""
Text-to-Speech client using Inworld's TTS API.
This module provides a class for generating speech from text with phoneme substitution support.
"""

import requests
import json
import base64
import os
import logging
import re
from pathlib import Path

import aiohttp

logger = logging.getLogger(__name__)

class TTSClient:
    """
    Client for Inworld's text-to-speech service.
    
    This class provides methods to convert text to speech using Inworld's TTS API
    with support for phoneme substitution for proper pronunciation.
    """
    
    # Phoneme substitution dictionary - word to IPA phoneme mapping
    PHONEME_SUBSTITUTIONS = {
        "cale": "/keɪl/",
        "pasta": "/ˈpæstə/"
    }
    
    def __init__(self, api_key=None):
        """
        Initialize the TTS client.
        
        Args:
            api_key (str, optional): The Inworld API key. If not provided, it will
                                     attempt to load from INWORLD_API_KEY environment variable.
        
        Raises:
            ValueError: If API key is not provided and not found in environment variables.
        """
        self.api_key = api_key or os.environ.get("INWORLD_API_KEY")
        
        if not self.api_key:
            raise ValueError(
                "API key is required. Either pass it to the constructor or "
                "set the INWORLD_API_KEY environment variable."
            )
        
        # API endpoints
        self.url = 'https://api.inworld.ai/tts/v1/voice'
        self.streaming_url = 'https://api.inworld.ai/tts/v1/voice:stream'

        # Make sure the Authorization header is properly formatted
        # The API key might already include "Basic " prefix or might need it added
        auth_value = self.api_key
        if not auth_value.startswith("Basic "):
            auth_value = f"Basic {auth_value}"

        self.headers = {
            'Authorization': auth_value,
            'Content-Type': 'application/json'
        }

        # Persistent aiohttp session for streaming requests (lazy-initialized)
        self._session = None

        logger.debug(f"Initialized TTSClient with API URL: {self.url}")
    
    def _preprocess_text_with_phonemes(self, text):
        """
        Preprocess text by substituting words with their IPA phoneme representations.
        
        Args:
            text (str): The original text to preprocess.
            
        Returns:
            str: Text with phoneme substitutions applied.
        """
        processed_text = text
        
        for word, phoneme in self.PHONEME_SUBSTITUTIONS.items():
            # Use word boundaries to match whole words only (case-insensitive)
            pattern = r'\b' + re.escape(word) + r'\b'
            processed_text = re.sub(pattern, phoneme, processed_text, flags=re.IGNORECASE)
        
        if processed_text != text:
            logger.debug(f"Applied phoneme substitutions. Original: '{text}' -> Processed: '{processed_text}'")
        
        return processed_text
    
    def generate_speech(self, text, voice_id="Dennis", output_file=None, model_id="inworld-tts-1-max", 
                       audio_encoding="LINEAR16", temperature=1.1, timestamp_type=None, 
                       sample_rate_hertz=22050, speaking_rate=1.0, pitch=0.0, voice_name=None):
        """
        Generate speech from text and save it to an audio file.
        
        Args:
            text (str): The text to convert to speech. Maximum 2,000 characters.
            voice_id (str, optional): The ID of the voice to use. Defaults to "Dennis".
            output_file (str, optional): Path to save the audio file. If not provided,
                                        a temporary file will be created.
            model_id (str, optional): The model to use. Options: "inworld-tts-1" or "inworld-tts-1-max". 
                                     Defaults to "inworld-tts-1-max".
            audio_encoding (str, optional): Audio format. Options: "LINEAR16", "MP3", "OGG_OPUS", 
                                           "ALAW", "MULAW". Defaults to "LINEAR16".
            temperature (float, optional): Randomness degree (0-2). Defaults to 1.1.
            timestamp_type (str, optional): Timestamp alignment type. Options: "WORD", "CHARACTER", 
                                           or None. Defaults to None.
            sample_rate_hertz (int, optional): Sample rate (8000-48000). Defaults to 22050.
            speaking_rate (float, optional): Speaking speed (0.5-1.5). Defaults to 1.0.
            pitch (float, optional): Pitch modification (-5.0 to 5.0). Defaults to 0.0.
            voice_name (str, optional): DEPRECATED. Use voice_id instead. Maintained for backward compatibility.
        
        Returns:
            str: The path to the generated audio file.
            
        Raises:
            Exception: If the API request fails.
        """
        # Apply phoneme substitutions to the text
        processed_text = self._preprocess_text_with_phonemes(text)
        
        # Handle backward compatibility for voice_name parameter
        if voice_name is not None:
            voice_id = voice_name
            logger.warning("voice_name parameter is deprecated. Use voice_id instead.")
        
        logger.debug(f"Generating speech for text: '{processed_text[:50]}...' with voice: {voice_id}")
        
        # Build the payload according to the new API format
        payload = {
            'text': processed_text,
            'voiceId': voice_id,
            'modelId': model_id,
            'audioConfig': {
                'audioEncoding': audio_encoding,
                'sampleRateHertz': sample_rate_hertz,
                'speakingRate': speaking_rate,
                'pitch': pitch
            },
            'temperature': temperature
        }
        
        # Add timestamp type if specified
        if timestamp_type:
            payload['timestampType'] = timestamp_type
        
        try:
            logger.debug(f"Making API request to {self.url}")
            
            response = requests.post(
                self.url,
                headers=self.headers,
                json=payload,  # Use json parameter instead of data for cleaner serialization
                timeout=30
            )
            
            logger.debug(f"API response status code: {response.status_code}")
            
            # Check if the response is successful
            if response.status_code != 200:
                logger.error(f"API error: {response.status_code} - {response.text}")
                raise Exception(f"API returned error: {response.status_code} - {response.text}")
            
            # Create a file path if not provided
            if not output_file:
                # Create a temporary file name with the first few words of the text
                text_preview = processed_text[:20].replace(" ", "_").replace("/", "_")
                # Set file extension based on audio encoding
                extension = "wav" if audio_encoding == "LINEAR16" else audio_encoding.lower()
                if extension == "ogg_opus":
                    extension = "ogg"
                output_file = f"tts_{text_preview}.{extension}"
            
            # Ensure the directory exists
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Parse the JSON response
            try:
                response_data = response.json()
                
                # Extract audio content from the new API response format
                if 'audioContent' in response_data:
                    logger.debug("Found audioContent in response")
                    audio_base64 = response_data['audioContent']
                    
                    # Decode the base64 audio data
                    audio_data = base64.b64decode(audio_base64)
                    
                    # Write to file
                    with open(output_file, 'wb') as f:
                        f.write(audio_data)
                    
                    logger.debug(f"Successfully saved audio to: {output_file}")
                    
                    # Log timestamp information if available
                    if 'timestampInfo' in response_data:
                        timestamp_info = response_data['timestampInfo']
                        if 'wordAlignment' in timestamp_info:
                            word_count = len(timestamp_info['wordAlignment'].get('words', []))
                            logger.debug(f"Word alignment data available for {word_count} words")
                        if 'characterAlignment' in timestamp_info:
                            char_count = len(timestamp_info['characterAlignment'].get('characters', []))
                            logger.debug(f"Character alignment data available for {char_count} characters")
                    
                    return output_file
                else:
                    logger.error("No audioContent found in response")
                    raise Exception("Response missing audioContent field")
                    
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON response: {e}")
                # Save raw response as fallback
                with open(output_file, 'wb') as f:
                    f.write(response.content)
                logger.debug(f"Saved raw response after JSON parse error: {output_file}")
                return output_file
            except Exception as e:
                logger.error(f"Error processing response: {e}")
                # Save raw response as fallback
                with open(output_file, 'wb') as f:
                    f.write(response.content)
                logger.debug(f"Saved raw response after processing error: {output_file}")
                return output_file
            
        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP request error: {str(e)}")
            raise Exception(f"Failed to make API request: {str(e)}")
        except Exception as e:
            logger.error(f"Error generating speech: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            raise Exception(f"Failed to generate speech: {str(e)}")
    
    async def _get_session(self):
        """Get or create the persistent aiohttp session."""
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(keepalive_timeout=30)
            self._session = aiohttp.ClientSession(connector=connector)
        return self._session

    async def generate_speech_streaming(self, text, voice_id="Dennis",
                                         model_id="inworld-tts-1-max",
                                         voice_name=None):
        """
        Async generator that streams MP3 audio chunks from the Inworld TTS API.

        The streaming endpoint returns newline-delimited JSON. Each line contains
        a JSON object with ``result.audioContent`` (base64-encoded MP3 data).

        Yields base64-encoded audio content strings (one per NDJSON line that
        contains audio data).
        """
        processed_text = self._preprocess_text_with_phonemes(text)

        if voice_name is not None:
            voice_id = voice_name

        payload = {
            "text": processed_text,
            "voiceId": voice_id,
            "modelId": model_id,
            "audioConfig": {
                "audioEncoding": "MP3",
            },
        }

        logger.debug(f"Streaming TTS request for: '{processed_text[:50]}...' voice={voice_id}")

        session = await self._get_session()
        async with session.post(
            self.streaming_url,
            headers=self.headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=60, sock_read=30),
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise Exception(f"Streaming TTS API error: {resp.status} - {body}")

            # Response is newline-delimited JSON
            buffer = ""
            async for raw_chunk in resp.content.iter_any():
                buffer += raw_chunk.decode("utf-8", errors="replace")
                lines = buffer.split("\n")
                buffer = lines.pop()  # keep incomplete trailing line

                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        result = data.get("result", data)
                        audio_content = result.get("audioContent")
                        if audio_content:
                            yield audio_content
                    except json.JSONDecodeError:
                        continue

            # Flush any remaining data left in the buffer (last line
            # without a trailing newline)
            if buffer.strip():
                try:
                    data = json.loads(buffer.strip())
                    result = data.get("result", data)
                    audio_content = result.get("audioContent")
                    if audio_content:
                        yield audio_content
                except json.JSONDecodeError:
                    pass

    async def close(self):
        """Close the persistent aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    def add_phoneme_substitution(self, word, phoneme):
        """
        Add a new word-to-phoneme substitution to the dictionary.
        
        Args:
            word (str): The word to substitute.
            phoneme (str): The IPA phoneme representation.
        """
        self.PHONEME_SUBSTITUTIONS[word] = phoneme
        logger.debug(f"Added phoneme substitution: '{word}' -> '{phoneme}'")
    
    def remove_phoneme_substitution(self, word):
        """
        Remove a word-to-phoneme substitution from the dictionary.
        
        Args:
            word (str): The word to remove from substitutions.
        """
        if word in self.PHONEME_SUBSTITUTIONS:
            del self.PHONEME_SUBSTITUTIONS[word]
            logger.debug(f"Removed phoneme substitution for: '{word}'")
        else:
            logger.warning(f"Word '{word}' not found in phoneme substitutions")
    
    def get_phoneme_substitutions(self):
        """
        Get a copy of the current phoneme substitution dictionary.
        
        Returns:
            dict: Copy of the phoneme substitution dictionary.
        """
        return self.PHONEME_SUBSTITUTIONS.copy()