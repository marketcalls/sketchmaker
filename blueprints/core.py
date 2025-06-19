from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from models import db, User, APIProvider, AIModel, APISettings, SystemSettings
from datetime import datetime
from extensions import limiter, get_rate_limit_string

core_bp = Blueprint('core', __name__)

@core_bp.route('/')
@limiter.limit(get_rate_limit_string())
def index():
    return render_template('index.html', current_year=datetime.now().year)

@core_bp.route('/pricing')
@limiter.limit(get_rate_limit_string())
def pricing():
    system_settings = SystemSettings.get_settings()
    return render_template('pricing.html', system_settings=system_settings)

@core_bp.route('/dashboard')
@limiter.limit(get_rate_limit_string())
@login_required
def dashboard():
    # Get user's subscription info
    subscription = current_user.get_subscription()
    
    # Check if credits need to be reset
    if subscription and subscription.should_reset_credits():
        subscription.reset_monthly_credits()
    
    # Get system API settings to check if centralized keys are configured
    api_settings = APISettings.get_settings()
    system_settings = SystemSettings.get_settings()
    
    return render_template('dashboard.html', 
                         subscription=subscription,
                         api_settings=api_settings,
                         system_settings=system_settings)

@core_bp.route('/subscription')
@limiter.limit(get_rate_limit_string())
@login_required
def subscription():
    # Get user's subscription info
    subscription = current_user.get_subscription()
    
    # Check if credits need to be reset
    if subscription and subscription.should_reset_credits():
        subscription.reset_monthly_credits()
    
    return render_template('subscription.html', subscription=subscription)

@core_bp.route('/settings')
@limiter.limit(get_rate_limit_string())
@login_required
def settings():
    # Get API settings and available providers
    api_settings = APISettings.get_settings()
    available_providers = api_settings.get_available_providers()
    system_settings = SystemSettings.get_settings()
    
    # Get all providers and models for display
    providers = APIProvider.query.filter_by(is_active=True).all()
    models = AIModel.query.filter_by(is_active=True).all()
    
    # Get user's subscription info
    subscription = current_user.get_subscription()
    
    # Check if credits need to be reset
    if subscription and subscription.should_reset_credits():
        subscription.reset_monthly_credits()
    
    return render_template('settings.html', 
                         api_settings=api_settings,
                         available_providers=available_providers,
                         providers=providers,
                         models=models,
                         subscription=subscription,
                         system_settings=system_settings)

@core_bp.route('/privacy')
@limiter.limit(get_rate_limit_string())
def privacy_policy():
    """Privacy Policy page"""
    return render_template('privacy.html', current_year=datetime.now().year)

@core_bp.route('/terms')
@limiter.limit(get_rate_limit_string())
def terms_conditions():
    """Terms and Conditions page"""
    return render_template('terms.html', current_year=datetime.now().year)

@core_bp.route('/faq')
@limiter.limit(get_rate_limit_string())
def faq():
    """FAQ page"""
    return render_template('faq.html')

@core_bp.route('/refund-policy')
@limiter.limit(get_rate_limit_string())
def refund_policy():
    """Refund Policy page"""
    return render_template('refund.html', current_year=datetime.now().year)

@core_bp.route('/about')
@limiter.limit(get_rate_limit_string())
def about():
    """About Us page"""
    return render_template('about.html', current_year=datetime.now().year)

@core_bp.route('/sitemap.xml')
@limiter.limit(get_rate_limit_string())
def sitemap():
    """Generate sitemap.xml for SEO"""
    from flask import make_response
    
    sitemap_xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url>
        <loc>{}</loc>
        <lastmod>{}</lastmod>
        <changefreq>weekly</changefreq>
        <priority>1.0</priority>
    </url>
    <url>
        <loc>{}</loc>
        <lastmod>{}</lastmod>
        <changefreq>monthly</changefreq>
        <priority>0.9</priority>
    </url>
    <url>
        <loc>{}</loc>
        <lastmod>{}</lastmod>
        <changefreq>monthly</changefreq>
        <priority>0.8</priority>
    </url>
    <url>
        <loc>{}</loc>
        <lastmod>{}</lastmod>
        <changefreq>monthly</changefreq>
        <priority>0.7</priority>
    </url>
    <url>
        <loc>{}</loc>
        <lastmod>{}</lastmod>
        <changefreq>monthly</changefreq>
        <priority>0.6</priority>
    </url>
    <url>
        <loc>{}</loc>
        <lastmod>{}</lastmod>
        <changefreq>monthly</changefreq>
        <priority>0.6</priority>
    </url>
    <url>
        <loc>{}</loc>
        <lastmod>{}</lastmod>
        <changefreq>monthly</changefreq>
        <priority>0.5</priority>
    </url>
    <url>
        <loc>{}</loc>
        <lastmod>{}</lastmod>
        <changefreq>monthly</changefreq>
        <priority>0.5</priority>
    </url>
    <url>
        <loc>{}</loc>
        <lastmod>{}</lastmod>
        <changefreq>monthly</changefreq>
        <priority>0.5</priority>
    </url>
    <url>
        <loc>{}</loc>
        <lastmod>{}</lastmod>
        <changefreq>yearly</changefreq>
        <priority>0.3</priority>
    </url>
    <url>
        <loc>{}</loc>
        <lastmod>{}</lastmod>
        <changefreq>yearly</changefreq>
        <priority>0.3</priority>
    </url>
</urlset>""".format(
        request.host_url,
        datetime.now().strftime('%Y-%m-%d'),
        request.host_url + 'pricing',
        datetime.now().strftime('%Y-%m-%d'),
        request.host_url + 'about',
        datetime.now().strftime('%Y-%m-%d'),
        request.host_url + 'faq',
        datetime.now().strftime('%Y-%m-%d'),
        request.host_url + 'privacy',
        datetime.now().strftime('%Y-%m-%d'),
        request.host_url + 'terms',
        datetime.now().strftime('%Y-%m-%d'),
        request.host_url + 'refund-policy',
        datetime.now().strftime('%Y-%m-%d'),
        request.host_url + 'auth/login',
        datetime.now().strftime('%Y-%m-%d'),
        request.host_url + 'auth/register',
        datetime.now().strftime('%Y-%m-%d'),
        request.host_url + 'privacy',
        datetime.now().strftime('%Y-%m-%d'),
        request.host_url + 'terms',
        datetime.now().strftime('%Y-%m-%d')
    )
    
    response = make_response(sitemap_xml)
    response.headers['Content-Type'] = 'application/xml'
    return response

@core_bp.route('/robots.txt')
@limiter.limit(get_rate_limit_string())
def robots():
    """Generate robots.txt for SEO"""
    from flask import make_response
    
    robots_txt = """User-agent: *
Allow: /
Allow: /pricing
Allow: /about
Allow: /faq
Allow: /privacy
Allow: /terms
Allow: /refund-policy
Allow: /auth/login
Allow: /auth/register

Disallow: /admin/
Disallow: /dashboard/
Disallow: /settings/
Disallow: /api/
Disallow: /generate/
Disallow: /gallery/private/
Disallow: /training/

Sitemap: {}sitemap.xml""".format(request.host_url)
    
    response = make_response(robots_txt)
    response.headers['Content-Type'] = 'text/plain'
    return response

