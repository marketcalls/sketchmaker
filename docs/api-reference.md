# 🔌 SketchMaker AI API Reference

## 📋 API Overview

The SketchMaker AI REST API provides programmatic access to all image generation, user management, and system administration features. Built with Flask, it follows RESTful conventions and returns JSON responses.

## 🔐 Authentication

### **Session-Based Authentication**
All API endpoints require user authentication through Flask-Login sessions.

```python
# Login to establish session
POST /auth/login
{
    "email": "user@example.com",
    "password": "password"
}
```

### **CSRF Protection**
All POST, PUT, DELETE requests require CSRF tokens.

```javascript
// Include CSRF token in headers
headers: {
    'Content-Type': 'application/json',
    'X-CSRFToken': csrf_token
}
```

## 🎨 Image Generation API

### **Generate Image**

**Endpoint**: `POST /generate/image`

**Description**: Generate images using AI models with customizable parameters.

**Request Body**:
```json
{
    "prompt": "A beautiful sunset over mountains",
    "model": "fal-ai/flux-pro/v1.1",
    "image_size": {"width": 1024, "height": 1024},
    "art_style": "realistic",
    "negative_prompt": "blurry, low quality",
    "num_inference_steps": 50,
    "guidance_scale": 7.5,
    "seed": 12345
}
```

**Response**:
```json
{
    "success": true,
    "images": [
        {
            "image_url": "/static/images/generated_123.png",
            "filename": "generated_123.png",
            "format": "PNG",
            "dimensions": {"width": 1024, "height": 1024}
        }
    ],
    "prompt": "Enhanced prompt used for generation",
    "credits_used": 1,
    "credits_remaining": 99,
    "generation_time": 23.5
}
```

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `prompt` | string | Yes | Text description of desired image |
| `model` | string | No | AI model to use (default: auto-select) |
| `image_size` | object | No | Width/height or predefined size |
| `art_style` | string | No | Style preset (modern, classic, etc.) |
| `negative_prompt` | string | No | What to avoid in generation |
| `num_inference_steps` | integer | No | Quality vs speed (20-100) |
| `guidance_scale` | float | No | Prompt adherence (1-20) |
| `seed` | integer | No | Random seed for reproducibility |

**Supported Models**:
```json
[
    "fal-ai/flux-pro/v1.1",
    "fal-ai/flux-pro/v1.1-ultra",
    "fal-ai/flux/dev",
    "fal-ai/flux-lora",
    "fal-ai/flux-realism",
    "openai/dall-e-3",
    "openai/dall-e-2"
]
```

**Error Responses**:
```json
{
    "error": "Insufficient credits",
    "details": "You need 1 credit but only have 0 remaining",
    "type": "insufficient_credits",
    "credits_remaining": 0
}
```

### **Generate Prompt Enhancement**

**Endpoint**: `POST /generate/prompt`

**Description**: Enhance user prompts using AI for better image generation results.

**Request Body**:
```json
{
    "topic": "cat sitting",
    "model": "anthropic/claude-3-sonnet",
    "art_style": "realistic",
    "color_scheme": "warm",
    "lighting_mood": "natural",
    "subject_focus": "close-up",
    "background_style": "blurred",
    "effects_filters": "none"
}
```

**Response**:
```json
{
    "prompt": "A magnificent orange tabby cat sitting gracefully on a vintage wooden windowsill, warm sunlight streaming through lace curtains creating soft shadows, shallow depth of field with beautifully blurred background, natural lighting, professional photography style, high detail, realistic textures",
    "original_topic": "cat sitting",
    "enhancement_applied": true,
    "estimated_quality": "high"
}
```

## 📁 Gallery Management API

### **List Images**

**Endpoint**: `GET /api/gallery`

**Description**: Retrieve user's generated images with filtering and pagination.

**Query Parameters**:
```
GET /api/gallery?page=1&limit=20&style=modern&format=png&date_from=2025-01-01
```

**Response**:
```json
{
    "images": [
        {
            "id": 123,
            "filename": "generated_123.png",
            "prompt": "Beautiful landscape",
            "image_url": "/static/images/generated_123.png",
            "thumbnail_url": "/static/images/thumb_generated_123.png",
            "created_at": "2025-06-18T10:30:00Z",
            "art_style": "realistic",
            "dimensions": {"width": 1024, "height": 1024},
            "file_size": 1245678,
            "format": "PNG",
            "model_used": "fal-ai/flux-pro/v1.1"
        }
    ],
    "pagination": {
        "page": 1,
        "limit": 20,
        "total": 150,
        "pages": 8,
        "has_next": true,
        "has_prev": false
    }
}
```

### **Download Image**

**Endpoint**: `GET /download/<image_id>/<format>`

**Description**: Download images in specified format.

**Example**:
```
GET /download/123/png
GET /download/123/jpeg
GET /download/123/webp
```

**Response**: Binary image file with appropriate headers.

## 🏋️ LoRA Training API

### **Upload Training Images**

**Endpoint**: `POST /api/training/upload`

**Description**: Upload images for custom LoRA model training.

**Request**: Multipart form data
```
Content-Type: multipart/form-data

files[]: [image files]
csrf_token: [csrf_token]
```

**Response**:
```json
{
    "status": "success",
    "images_data_url": "data:application/zip;base64,iVBORw0KGgoAAAANSU...",
    "image_count": 12,
    "total_size": "15.2MB"
}
```

### **Start Training**

**Endpoint**: `POST /api/training/start`

**Description**: Begin LoRA model training with uploaded images.

**Request Body**:
```json
{
    "images_data_url": "data:application/zip;base64,iVBORw0KGgoAAAANSU...",
    "trigger_word": "mylogo",
    "steps": 500,
    "create_masks": true
}
```

**Response**:
```json
{
    "status": "training_started",
    "training_id": "training_12345",
    "estimated_time": "20-30 minutes",
    "webhook_url": "/api/training/status/12345"
}
```

### **Training Status**

**Endpoint**: `GET /api/training/status/<training_id>`

**Description**: Check training progress and retrieve results.

**Response** (In Progress):
```json
{
    "status": "training",
    "progress": 45,
    "current_step": 225,
    "total_steps": 500,
    "estimated_remaining": "12 minutes",
    "logs": [
        "Step 225/500: Loss 0.0123",
        "Progress: 45% complete"
    ]
}
```

**Response** (Complete):
```json
{
    "status": "completed",
    "model_url": "/static/training_files/1/model_12345.safetensors",
    "config_url": "/static/training_files/1/config_12345.json",
    "trigger_word": "mylogo",
    "training_time": "18 minutes",
    "final_loss": 0.0089
}
```

## 👥 User Management API

### **User Profile**

**Endpoint**: `GET /api/user/profile`

**Response**:
```json
{
    "id": 123,
    "username": "john_doe",
    "email": "john@example.com",
    "role": "user",
    "created_at": "2025-01-15T09:00:00Z",
    "subscription": {
        "plan": "Pro",
        "credits_remaining": 450,
        "credits_used_this_month": 50,
        "next_reset": "2025-07-01T00:00:00Z",
        "is_active": true
    },
    "preferences": {
        "default_style": "modern",
        "preferred_format": "png",
        "email_notifications": true
    }
}
```

### **Usage Statistics**

**Endpoint**: `GET /api/user/usage`

**Query Parameters**:
```
GET /api/user/usage?period=month&year=2025&month=6
```

**Response**:
```json
{
    "period": "2025-06",
    "total_images": 47,
    "credits_used": 52,
    "credits_allocated": 500,
    "usage_by_model": {
        "fal-ai/flux-pro/v1.1": 25,
        "openai/dall-e-3": 15,
        "fal-ai/flux-realism": 7
    },
    "usage_by_style": {
        "realistic": 20,
        "modern": 15,
        "abstract": 12
    },
    "daily_usage": [
        {"date": "2025-06-01", "images": 3, "credits": 3},
        {"date": "2025-06-02", "images": 5, "credits": 6}
    ]
}
```

## 🔧 Admin API

### **System Status**

**Endpoint**: `GET /admin/api/status`

**Description**: Get comprehensive system health information.

**Response**:
```json
{
    "system": {
        "status": "healthy",
        "uptime": "7 days, 14:32:15",
        "version": "1.0.0.0",
        "build_date": "2025-06-18",
        "environment": "production"
    },
    "database": {
        "status": "connected",
        "total_users": 1247,
        "total_images": 15693,
        "storage_used": "25.7 GB"
    },
    "ai_providers": [
        {
            "name": "OpenAI",
            "status": "active",
            "response_time": "1.2s",
            "success_rate": "99.8%"
        },
        {
            "name": "Anthropic",
            "status": "active",
            "response_time": "0.8s",
            "success_rate": "99.9%"
        }
    ],
    "scheduler": {
        "status": "running",
        "active_jobs": 3,
        "next_credit_reset": "2025-07-01T00:00:00Z"
    }
}
```

### **User Management**

**Endpoint**: `GET /admin/api/users`

**Description**: List and filter users (admin only).

**Query Parameters**:
```
GET /admin/api/users?page=1&limit=50&role=user&status=active&search=john
```

**Response**:
```json
{
    "users": [
        {
            "id": 123,
            "username": "john_doe",
            "email": "john@example.com",
            "role": "user",
            "status": "active",
            "created_at": "2025-01-15T09:00:00Z",
            "last_login": "2025-06-18T08:30:00Z",
            "subscription": {
                "plan": "Pro",
                "credits_remaining": 450
            },
            "total_images": 47,
            "total_credits_used": 152
        }
    ],
    "pagination": {
        "page": 1,
        "limit": 50,
        "total": 1247,
        "pages": 25
    }
}
```

### **Credit Management**

**Endpoint**: `POST /admin/api/users/<user_id>/credits`

**Description**: Modify user credits (admin only).

**Request Body**:
```json
{
    "action": "add",
    "amount": 100,
    "reason": "Promotional bonus"
}
```

**Response**:
```json
{
    "success": true,
    "user_id": 123,
    "old_credits": 50,
    "new_credits": 150,
    "action": "add",
    "amount": 100,
    "reason": "Promotional bonus",
    "updated_at": "2025-06-18T10:30:00Z"
}
```

## 📊 Analytics API

### **System Metrics**

**Endpoint**: `GET /admin/api/metrics`

**Description**: Get system-wide usage statistics.

**Query Parameters**:
```
GET /admin/api/metrics?period=week&start_date=2025-06-01&end_date=2025-06-18
```

**Response**:
```json
{
    "period": {
        "start": "2025-06-01",
        "end": "2025-06-18",
        "days": 18
    },
    "totals": {
        "images_generated": 2847,
        "credits_consumed": 3102,
        "active_users": 234,
        "new_registrations": 45
    },
    "daily_stats": [
        {
            "date": "2025-06-01",
            "images": 156,
            "credits": 167,
            "users": 89
        }
    ],
    "popular_models": [
        {"model": "fal-ai/flux-pro/v1.1", "usage": 45.2, "images": 1287},
        {"model": "openai/dall-e-3", "usage": 32.1, "images": 914}
    ],
    "popular_styles": [
        {"style": "realistic", "percentage": 38.5},
        {"style": "modern", "percentage": 24.7}
    ]
}
```

## 🔔 Webhook API

### **Configuration**

**Endpoint**: `POST /admin/api/webhooks`

**Description**: Configure webhook endpoints for real-time notifications.

**Request Body**:
```json
{
    "url": "https://your-app.com/webhooks/sketchmaker",
    "events": ["image.generated", "training.completed", "user.registered"],
    "secret": "your-webhook-secret"
}
```

### **Event Types**

| Event | Description | Payload |
|-------|-------------|---------|
| `image.generated` | Image generation completed | `{user_id, image_id, prompt, model}` |
| `training.completed` | LoRA training finished | `{user_id, training_id, model_url}` |
| `user.registered` | New user registration | `{user_id, username, email}` |
| `credits.low` | User credits below threshold | `{user_id, credits_remaining}` |
| `system.error` | System error occurred | `{error_type, message, timestamp}` |

## 📝 Rate Limits

| Endpoint Type | Rate Limit | Window |
|---------------|------------|---------|
| Image Generation | 20 requests | per minute |
| Prompt Enhancement | 100 requests | per minute |
| Gallery API | 1000 requests | per hour |
| Training API | 5 requests | per hour |
| Admin API | 1000 requests | per hour |

## 🚨 Error Handling

### **Error Response Format**
```json
{
    "error": "Error description",
    "details": "Detailed error message",
    "type": "error_type",
    "code": 400,
    "timestamp": "2025-06-18T10:30:00Z",
    "request_id": "req_12345"
}
```

### **Common Error Codes**

| Code | Type | Description |
|------|------|-------------|
| 400 | `invalid_request` | Malformed request |
| 401 | `unauthorized` | Authentication required |
| 403 | `forbidden` | Insufficient permissions |
| 404 | `not_found` | Resource not found |
| 409 | `conflict` | Resource conflict |
| 429 | `rate_limited` | Rate limit exceeded |
| 500 | `server_error` | Internal server error |
| 503 | `service_unavailable` | AI provider unavailable |

## 💡 Best Practices

### **Prompt Optimization**
- Use descriptive, specific language
- Include style and quality modifiers
- Leverage prompt enhancement API
- Test different models for best results

### **Error Handling**
- Implement exponential backoff for retries
- Handle rate limits gracefully
- Check credit balance before generation
- Validate inputs client-side

### **Performance**
- Cache frequently used images
- Use appropriate image sizes
- Implement client-side compression
- Monitor API response times

---

*This API reference covers SketchMaker AI v1.0.0.0. For the latest updates, check the release notes.*