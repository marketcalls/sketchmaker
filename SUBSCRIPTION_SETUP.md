# Subscription System Setup Guide

This guide covers the complete setup and management of Sketchmaker's subscription system with personalized credit resets.

## Table of Contents
1. [Quick Setup](#quick-setup)
2. [API Key Management](#api-key-management)
3. [System Architecture](#system-architecture)
4. [Subscription Plans](#subscription-plans)
5. [Credit Reset System](#credit-reset-system)
6. [Admin Management](#admin-management)
7. [User Experience](#user-experience)
8. [Troubleshooting](#troubleshooting)

## Quick Setup

### 1. Install Dependencies
Ensure APScheduler is installed:
```bash
pip install -r requirements.txt
```

### 2. Initialize Subscription System
Run the automated setup script:
```bash
python setup_subscriptions.py
```

This script will:
- Create all necessary database tables
- Initialize default subscription plans (Free, Premium, Pro)
- Assign free plans to existing users
- Display setup summary

### 3. Start the Application
```bash
python app.py
```

The subscription system will automatically:
- Start the APScheduler background service
- Schedule credit resets for all active subscriptions
- Begin monitoring and processing scheduled jobs

## API Key Management

### Centralized Control
Sketchmaker uses centralized API key management for security and cost control:

- **Admin-only access**: Only administrators can configure API keys
- **Cost control**: Prevents users from using their own API keys and incurring costs
- **Simplified user experience**: Users consume credits without managing keys
- **Security**: API keys are encrypted and stored centrally

### Required Configuration
Administrators must configure via **Admin → API Key Management**:

| Service | Purpose | Required |
|---------|---------|----------|
| **FAL API** | Image generation | ✅ Required |
| **AI Provider** | Prompt enhancement | ✅ At least one |
| OpenAI | GPT models | Optional |
| Anthropic | Claude models | Optional |
| Google Gemini | Gemini models | Optional |
| Groq | High-speed inference | Optional |

### Setup Process
1. Login as admin/superadmin
2. Navigate to **Admin → API Key Management**
3. Configure FAL API key (required for image generation)
4. Configure at least one AI provider for prompt enhancement
5. Test API keys to ensure they work
6. Set default provider and model (optional)

### User Experience
- Users see API status on their settings page (read-only)
- No API key configuration required from users
- Clear messaging when services are unavailable
- Contact admin for service issues

## System Architecture

### APScheduler Integration
```
Flask App
├── Background Scheduler (APScheduler)
│   ├── Individual user credit reset jobs
│   ├── Automatic job scheduling for new subscriptions
│   └── Persistent job storage across app restarts
├── Subscription Models
│   ├── SubscriptionPlanModel (plan definitions)
│   ├── UserSubscription (user-plan assignments)
│   └── UsageHistory (credit usage tracking)
└── Admin Interface
    ├── Subscription management
    ├── Job monitoring
    └── Usage reports
```

### Database Schema
```sql
-- Subscription Plans
subscription_plans (
    id, name, display_name, monthly_credits,
    description, features, is_active
)

-- User Subscriptions
user_subscriptions (
    id, user_id, plan_id, credits_remaining,
    credits_used_this_month, subscription_start,
    last_credit_reset, is_active, assigned_by_id
)

-- Usage History
usage_history (
    id, user_id, subscription_id, action,
    credits_used, metadata, created_at
)
```

## Subscription Plans

### Default Plans

| Plan | Credits/Month | Target Users | Features |
|------|---------------|--------------|----------|
| **Free** | 10 | New users, light usage | Basic models, standard resolution |
| **Premium** | 100 | Regular users | All models, high resolution, LoRA training |
| **Pro** | 1000 | Power users, businesses | Ultra-high resolution, API access, priority support |

### Plan Management
```bash
# Access admin panel
Admin → Manage Subscriptions → Manage Plans

# Available actions:
- Create new plans
- Edit existing plans (credits, features, descriptions)
- Activate/deactivate plans
- View plan usage statistics
```

## Credit Reset System

### How Personalized Resets Work

**Traditional System (First-of-Month)**:
- User A joins Jan 5th → Gets 5 days of usage
- User B joins Jan 25th → Gets 25 days of usage
- Both reset Feb 1st → Unfair allocation

**Sketchmaker System (Personalized)**:
- User A joins Jan 5th → Credits reset 5th of each month
- User B joins Jan 25th → Credits reset 25th of each month
- Fair: Everyone gets full 30-day cycles

### Technical Implementation

#### Scheduling Logic
```python
def get_next_reset_date(self):
    """Calculate next reset based on subscription start date"""
    # If subscribed Jan 15th, next reset is Feb 15th
    # Handles edge cases like Jan 31st → Feb 28th
    # Returns exact datetime for APScheduler
```

#### Job Management
```python
# Automatic scheduling when plan assigned
subscription_scheduler.schedule_user_reset(new_subscription.id)

# Job naming convention
job_id = f"credit_reset_{subscription_id}"

# Persistent across app restarts
scheduler.add_job(
    func=reset_user_credits,
    trigger=DateTrigger(run_date=next_reset_date),
    id=job_id,
    replace_existing=True
)
```

### Reset Process
1. **Scheduled Trigger**: APScheduler fires at exact reset time
2. **Credit Reset**: `credits_remaining = plan.monthly_credits`
3. **Usage Reset**: `credits_used_this_month = 0`
4. **Logging**: Record reset in UsageHistory
5. **Reschedule**: Schedule next month's reset
6. **Error Handling**: Rollback on failure, retry logic

## Admin Management

### Subscription Management Interface

#### Main Dashboard (`/admin/subscriptions/`)
- View all users and their subscription status
- Quick actions: Assign plans, modify credits, view usage
- Statistics: Total users, active subscriptions, plan distribution

#### Plan Management (`/admin/subscriptions/plans`)
- Create and edit subscription plans
- Configure credits, features, and descriptions
- Activate/deactivate plans

#### Scheduled Jobs (`/admin/subscriptions/scheduled-jobs`)
- Monitor all upcoming credit resets
- View exact reset dates and times for each user
- Force manual credit reset if needed
- Real-time job status monitoring

#### Usage Reports (`/admin/subscriptions/reports`)
- Plan distribution analytics
- Top users by credit usage
- Monthly usage trends
- Export capabilities

### Common Admin Tasks

#### Assign Subscription Plan
```bash
1. Go to Admin → Manage Subscriptions
2. Find user in the table
3. Click "Change Plan"
4. Select plan and add optional notes
5. Click "Assign Plan"
# User is automatically scheduled for personalized resets
```

#### Modify User Credits
```bash
1. Click "Modify Credits" for any user
2. Choose "Add Credits" or "Set Credits To"
3. Enter amount
4. Click "Update Credits"
# Action is logged in usage history
```

#### Monitor Reset Schedule
```bash
1. Go to Admin → Manage Subscriptions → Scheduled Jobs
2. View upcoming resets with exact dates/times
3. Force manual reset if needed
4. Monitor scheduler health
```

## User Experience

### Dashboard Display
Users see comprehensive subscription information:

```html
┌─────────────────────────────────┐
│ Your Subscription               │
├─────────────────────────────────┤
│ Current Plan: Premium Plan      │
│ Credits Remaining: 75           │
│ ████████░░ 25/100 used         │
│                                 │
│ Plan Features:                  │
│ ✓ 100 images per month         │
│ ✓ Access to all models         │
│ ✓ High resolution              │
│                                 │
│ Next reset: February 15, 2025   │
│ Days until reset: 12            │
└─────────────────────────────────┘
```

### Credit Usage Flow
1. **Check Credits**: Dashboard shows remaining balance
2. **Generate Image**: 1 credit deducted on success
3. **Real-time Update**: Credit count updates immediately
4. **Limit Enforcement**: Generation blocked when credits exhausted
5. **Clear Messaging**: "Contact admin to upgrade your plan"

### Reset Notifications
- Dashboard countdown: "Days until reset: 12"
- Exact date display: "Next reset: February 15, 2025"
- Fair system messaging: Credits reset based on subscription date

## Troubleshooting

### Common Issues

#### Scheduler Not Starting
```bash
# Check logs for errors
tail -f app.log | grep scheduler

# Verify APScheduler is installed
pip show APScheduler

# Restart application
python app.py
```

#### Credits Not Resetting
```bash
# Check scheduled jobs
Admin → Manage Subscriptions → Scheduled Jobs

# Force manual reset
Click "Force Reset" for affected user

# Check logs
tail -f app.log | grep credit_reset
```

#### Missing Subscriptions
```bash
# Re-run setup script
python setup_subscriptions.py

# Check user has active subscription
Admin → Manage Subscriptions → View user status

# Manually assign plan if needed
```

### Monitoring Commands

#### Check Scheduler Status
```python
# In Flask shell
from services.scheduler import subscription_scheduler

# Get all scheduled jobs
jobs = subscription_scheduler.get_scheduled_jobs()
print(f"Active jobs: {len(jobs)}")

# Check specific user
subscription_scheduler.schedule_user_reset(user_subscription_id)
```

#### Database Queries
```sql
-- Check subscription status
SELECT u.username, sp.display_name, us.credits_remaining, us.subscription_start 
FROM users u 
JOIN user_subscriptions us ON u.id = us.user_id 
JOIN subscription_plans sp ON us.plan_id = sp.id 
WHERE us.is_active = true;

-- Check usage history
SELECT uh.created_at, uh.action, uh.credits_used, uh.metadata 
FROM usage_history uh 
WHERE uh.user_id = ? 
ORDER BY uh.created_at DESC;
```

### Performance Considerations

#### Scheduler Optimization
- Jobs are coalesced to prevent duplicate execution
- Maximum 1 instance per job to prevent overlaps
- 1-hour misfire grace time for system maintenance
- Automatic job rescheduling after execution

#### Database Performance
- Indexes on user_id, subscription_id, created_at
- Periodic cleanup of old usage history
- Efficient queries for dashboard display

## Security Notes

### Access Control
- Only admins can manage subscriptions
- Superadmins can create/modify plans
- Users can only view their own subscription data
- All actions logged for audit trails

### Data Protection
- API keys remain user-controlled
- Usage data includes metadata but not sensitive information
- Subscription changes logged with admin attribution
- Credit modifications require admin authentication

## Conclusion

The APScheduler-based subscription system provides:

✅ **Zero-maintenance operation** - No cron jobs or external scheduling needed
✅ **Fair credit allocation** - Personalized reset dates for every user  
✅ **Complete admin control** - Full management via web interface
✅ **Transparent user experience** - Clear visibility into credits and reset dates
✅ **Robust error handling** - Automatic retry and rollback mechanisms
✅ **Comprehensive monitoring** - Real-time job status and usage analytics

The system is production-ready and scales automatically with your user base.