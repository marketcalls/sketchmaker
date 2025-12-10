"""
Unified AI Client using LiteLLM
Supports: OpenAI, Anthropic, Google Gemini, Groq, xAI (Grok), Cerebras, OpenRouter
"""
import litellm
from litellm import completion
from flask import current_app
import fal_client
import os

# Drop unsupported parameters automatically (e.g., temperature for GPT-5 models)
litellm.drop_params = True

class APIKeyError(Exception):
    """Exception raised when required API keys are missing"""
    pass

class LiteLLMClient:
    """
    Unified client for all LLM providers via LiteLLM.

    Supported Providers and their prefixes:
    - OpenAI: openai/ (gpt-5, gpt-4o, o3, etc.)
    - Anthropic: anthropic/ (claude-opus-4-5, claude-sonnet-4-5, etc.)
    - Google Gemini: gemini/ (gemini-3-pro, gemini-2.5-flash, etc.)
    - Groq: groq/ (llama-3.3-70b, compound-beta, gpt-oss-120b, etc.)
    - xAI (Grok): xai/ (grok-3, grok-2, etc.)
    - Cerebras: cerebras/ (llama-3.3-70b, qwen3-32b, etc.)
    - OpenRouter: openrouter/ (any model via openrouter)
    """

    # Provider name to LiteLLM prefix mapping
    PROVIDER_PREFIXES = {
        'OpenAI': 'openai',
        'Anthropic': 'anthropic',
        'Google Gemini': 'gemini',
        'Groq': 'groq',
        'xAI': 'xai',
        'Cerebras': 'cerebras',
        'OpenRouter': 'openrouter'
    }

    # Environment variable names for each provider
    PROVIDER_ENV_KEYS = {
        'OpenAI': 'OPENAI_API_KEY',
        'Anthropic': 'ANTHROPIC_API_KEY',
        'Google Gemini': 'GEMINI_API_KEY',
        'Groq': 'GROQ_API_KEY',
        'xAI': 'XAI_API_KEY',
        'Cerebras': 'CEREBRAS_API_KEY',
        'OpenRouter': 'OPENROUTER_API_KEY'
    }

    def __init__(self, api_key, provider_name):
        """
        Initialize the LiteLLM client.

        Args:
            api_key: The API key for the provider
            provider_name: Name of the provider (e.g., 'OpenAI', 'Anthropic')
        """
        if not api_key:
            raise APIKeyError(f"{provider_name} API key is required")

        self.api_key = api_key
        self.provider_name = provider_name
        self.prefix = self.PROVIDER_PREFIXES.get(provider_name, '')

        # Set environment variable for LiteLLM to use
        env_key = self.PROVIDER_ENV_KEYS.get(provider_name)
        if env_key:
            os.environ[env_key] = api_key

    # Models that use reasoning tokens and need reasoning_effort parameter
    # OpenAI reasoning models
    OPENAI_REASONING_MODELS = [
        'gpt-5', 'gpt-5-mini', 'gpt-5-nano', 'gpt-5-pro', 'gpt-5.1',
        'o1', 'o1-mini', 'o1-preview', 'o3', 'o3-mini', 'o3-pro', 'o4-mini'
    ]
    # Groq reasoning models (uses 'none', 'default', 'low', 'medium', 'high')
    GROQ_REASONING_MODELS = ['gpt-oss-120b', 'gpt-oss-20b']
    # Cerebras reasoning models
    CEREBRAS_REASONING_MODELS = ['gpt-oss-120b', 'qwen-3-32b']
    # Combined for detection
    REASONING_MODELS = OPENAI_REASONING_MODELS + GROQ_REASONING_MODELS + CEREBRAS_REASONING_MODELS

    def generate_completion(self, system_content, user_content, model,
                          temperature=0.7, max_tokens=500):
        """
        Generate a completion using LiteLLM's unified API.

        Args:
            system_content: System prompt
            user_content: User message
            model: Model name (with or without provider prefix)
            temperature: Temperature for generation (0.0 - 1.0)
            max_tokens: Maximum tokens to generate

        Returns:
            Generated text response
        """
        try:
            # Build full model name with provider prefix
            # Always add prefix unless model already starts with our provider prefix
            if self.prefix:
                # Check if model already has our provider prefix
                if model.startswith(f"{self.prefix}/"):
                    full_model = model
                else:
                    # Always add provider prefix (handles cases like "openai/gpt-oss-120b" on Groq)
                    full_model = f"{self.prefix}/{model}"
            else:
                full_model = model

            # Increase max_tokens for reasoning models (they use tokens for internal reasoning)
            model_base = model.split('/')[-1].lower()  # Get base model name
            is_reasoning_model = any(rm in model_base for rm in self.REASONING_MODELS)
            extra_params = {}
            if is_reasoning_model:
                # Different providers support different reasoning_effort values:
                # - OpenAI: 'minimal', 'low', 'medium', 'high' (NO 'none')
                # - Groq: 'none', 'default', 'low', 'medium', 'high' (NO 'minimal')
                # - Cerebras: 'low', 'medium', 'high' (check their docs)
                if self.provider_name == 'Groq':
                    extra_params['reasoning_effort'] = 'low'  # Groq doesn't support 'minimal'
                elif self.provider_name == 'OpenAI':
                    extra_params['reasoning_effort'] = 'minimal'  # OpenAI supports 'minimal'
                elif self.provider_name == 'Cerebras':
                    extra_params['reasoning_effort'] = 'low'  # Cerebras uses low/medium/high
                else:
                    extra_params['reasoning_effort'] = 'low'  # Safe default for other providers
                print(f"[DEBUG] Reasoning model detected, reasoning_effort={extra_params['reasoning_effort']}")

            # Build messages
            messages = []
            if system_content:
                messages.append({"role": "system", "content": system_content})
            messages.append({"role": "user", "content": user_content})

            # Call LiteLLM completion
            response = completion(
                model=full_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                api_key=self.api_key,
                **extra_params  # Include reasoning_effort for reasoning models
            )

            # Debug: log the full response structure
            print(f"[DEBUG] LiteLLM response: {response}")

            content = response.choices[0].message.content
            if content is None:
                # Some models return content in a different field or use reasoning
                if hasattr(response.choices[0].message, 'reasoning_content'):
                    content = response.choices[0].message.reasoning_content or ""
                else:
                    content = ""

            return content.strip()

        except Exception as e:
            error_message = str(e).lower()
            # Log the full error for debugging
            print(f"[LiteLLM Error] Provider: {self.provider_name}, Model: {full_model}, Error: {str(e)}")
            if "authentication" in error_message or "api key" in error_message or "invalid" in error_message or "401" in error_message:
                raise APIKeyError(f"Invalid {self.provider_name} API key. Contact administrator.")
            if "not found" in error_message or "does not exist" in error_message or "404" in error_message:
                raise APIKeyError(f"Model '{full_model}' not found on {self.provider_name}. Check model name.")
            raise APIKeyError(f"Error generating completion with {self.provider_name}: {str(e)}")


# Legacy client classes for backward compatibility (if needed)
# These now use LiteLLM under the hood

class OpenAIClient(LiteLLMClient):
    """OpenAI client using LiteLLM"""
    def __init__(self, api_key):
        super().__init__(api_key, 'OpenAI')

class AnthropicClient(LiteLLMClient):
    """Anthropic client using LiteLLM"""
    def __init__(self, api_key):
        super().__init__(api_key, 'Anthropic')

class GeminiClient(LiteLLMClient):
    """Google Gemini client using LiteLLM"""
    def __init__(self, api_key):
        super().__init__(api_key, 'Google Gemini')

class GroqClient(LiteLLMClient):
    """Groq client using LiteLLM"""
    def __init__(self, api_key):
        super().__init__(api_key, 'Groq')

class XAIClient(LiteLLMClient):
    """xAI (Grok) client using LiteLLM"""
    def __init__(self, api_key):
        super().__init__(api_key, 'xAI')

class CerebrasClient(LiteLLMClient):
    """Cerebras client using LiteLLM"""
    def __init__(self, api_key):
        super().__init__(api_key, 'Cerebras')

class OpenRouterClient(LiteLLMClient):
    """OpenRouter client using LiteLLM"""
    def __init__(self, api_key):
        super().__init__(api_key, 'OpenRouter')


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

    # Use unified LiteLLM client for all providers
    return LiteLLMClient(api_key, provider.name)


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
