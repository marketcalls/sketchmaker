from openai import OpenAI
from flask import current_app
from flask_login import current_user
import fal_client
import anthropic
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from groq import Groq

class APIKeyError(Exception):
    """Exception raised when required API keys are missing"""
    pass

class BaseAIClient:
    """Base class for AI clients"""
    def __init__(self, api_key):
        if not api_key:
            raise APIKeyError(f"{self.__class__.__name__} API key is required")
        self.api_key = api_key

class OpenAIClient(BaseAIClient):
    def __init__(self, api_key):
        super().__init__(api_key)
        self.client = OpenAI(api_key=api_key)

    def generate_completion(self, system_content, user_content, model, temperature=0.7, max_tokens=500):
        response = self.client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content}
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=0.9,
            frequency_penalty=0.2,
            presence_penalty=0.2,
            response_format={"type": "text"}
        )
        return response.choices[0].message.content.strip()

class AnthropicClient(BaseAIClient):
    def __init__(self, api_key):
        super().__init__(api_key)
        self.client = anthropic.Anthropic(api_key=api_key)

    def generate_completion(self, system_content, user_content, model, temperature=0.7, max_tokens=500):
        try:
            message = self.client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_content,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": user_content
                            }
                        ]
                    }
                ]
            )
            # Extract just the text from the response
            if isinstance(message.content, list) and len(message.content) > 0:
                for content in message.content:
                    if isinstance(content, dict) and content.get('type') == 'text':
                        return content.get('text', '').strip()
            return str(message.content[0].text) if message.content else ''
        except anthropic.AuthenticationError as e:
            raise APIKeyError("Invalid Anthropic API key. Contact administrator.")
        except Exception as e:
            raise APIKeyError(f"Error generating completion with Anthropic: {str(e)}")

class GeminiClient(BaseAIClient):
    def __init__(self, api_key):
        super().__init__(api_key)
        genai.configure(api_key=api_key)

    def generate_completion(self, system_content, user_content, model, temperature=0.7, max_tokens=500):
        try:
            generation_config = {
                "temperature": temperature,
                "top_p": 0.9,
                "top_k": 40,
                "max_output_tokens": max_tokens,
            }

            model = genai.GenerativeModel(
                model_name=model,
                generation_config=generation_config,
                system_instruction=system_content,
            )

            chat = model.start_chat(history=[])
            response = chat.send_message(user_content)
            return response.text
        except google_exceptions.InvalidArgument as e:
            if "API key not valid" in str(e):
                raise APIKeyError("Invalid Google Gemini API key. Contact administrator.")
            raise APIKeyError(f"Error with Google Gemini API: {str(e)}")
        except Exception as e:
            raise APIKeyError(f"Error generating completion with Google Gemini: {str(e)}")

class GroqClient(BaseAIClient):
    def __init__(self, api_key):
        super().__init__(api_key)
        self.client = Groq(api_key=api_key)

    def generate_completion(self, system_content, user_content, model, temperature=0.7, max_tokens=500):
        try:
            completion = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": user_content}
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=1,
                stream=False,
                stop=None
            )
            return completion.choices[0].message.content.strip()
        except Exception as e:
            error_message = str(e).lower()
            if "authentication" in error_message or "api key" in error_message:
                raise APIKeyError("Invalid Groq API key. Contact administrator.")
            raise APIKeyError(f"Error generating completion with Groq: {str(e)}")

def get_ai_client():
    """Get the appropriate AI client based on system configuration"""
    from models import APISettings, APIProvider
    
    # Get system API settings
    api_settings = APISettings.get_settings()
    if not api_settings.has_required_keys():
        raise APIKeyError("System API keys not configured by administrators")
    
    # Use default provider or first available
    if api_settings.default_provider_id:
        provider = APIProvider.query.get(api_settings.default_provider_id)
    else:
        available_providers = api_settings.get_available_providers()
        if not available_providers:
            raise APIKeyError("No AI providers configured")
        provider = available_providers[0]
    
    if not provider:
        raise APIKeyError("No valid AI provider found")

    api_key = api_settings.get_provider_key(provider.name)
    if not api_key:
        raise APIKeyError(f"{provider.name} API key not configured")

    if provider.name == "OpenAI":
        return OpenAIClient(api_key)
    elif provider.name == "Anthropic":
        return AnthropicClient(api_key)
    elif provider.name == "Google Gemini":
        return GeminiClient(api_key)
    elif provider.name == "Groq":
        return GroqClient(api_key)
    else:
        raise ValueError(f"Unsupported AI provider: {provider.name}")

def get_selected_model():
    """Get the system's default AI model"""
    from models import APISettings, AIModel
    
    api_settings = APISettings.get_settings()
    
    # Use default model if configured
    if api_settings.default_model_id:
        model = AIModel.query.get(api_settings.default_model_id)
        if model:
            return model.name
    
    # Otherwise use first available model from default provider
    if api_settings.default_provider_id:
        models = AIModel.query.filter_by(
            provider_id=api_settings.default_provider_id,
            is_active=True
        ).first()
        if models:
            return models.name
    
    # Fallback to any available model
    available_providers = api_settings.get_available_providers()
    if available_providers:
        model = AIModel.query.filter_by(
            provider_id=available_providers[0].id,
            is_active=True
        ).first()
        if model:
            return model.name
    
    raise APIKeyError("No AI model available")

def init_fal_client():
    """Initialize FAL client with system API key"""
    from models import APISettings
    
    api_settings = APISettings.get_settings()
    fal_key = api_settings.get_fal_key()
    
    if not fal_key:
        raise APIKeyError("FAL API key not configured by administrators")
    
    try:
        client = fal_client.SyncClient(key=fal_key)
        return client
    except Exception as e:
        print(f"Error initializing FAL client: {str(e)}")
        if "authentication failed" in str(e).lower():
            raise APIKeyError("FAL API key authentication failed. Contact administrator.")
        raise APIKeyError(f"Error initializing FAL client: {str(e)}")

def test_fal_client(client):
    """Test FAL client with a simple request"""
    try:
        def on_queue_update(update):
            if isinstance(update, fal_client.InProgress):
                for log in update.logs:
                    print(f"FAL log: {log['message']}")

        result = client.subscribe(
            "fal-ai/flux/dev",
            arguments={
                "prompt": "test prompt",
                "image_size": {
                    "width": 512,
                    "height": 512
                },
                "num_images": 1,
                "enable_safety_checker": True,
                "num_inference_steps": 28,
                "guidance_scale": 3.5,
                "seed": 2345
            },
            with_logs=True,
            on_queue_update=on_queue_update
        )
        print("FAL client tested successfully")
        print(f"Test result: {result}")
        return True
    except Exception as e:
        print(f"Error testing FAL client: {str(e)}")
        raise APIKeyError(f"Error testing FAL client: {str(e)}")
