# -*- coding: utf-8 -*-
"""
Ptah Studios Creative Booking Website
A full-stack Flask application for creative studio management.
Includes Public facing booking wizard, Portfolio showcase, 
and internal Admin Dashboard for project and client management.

UPDATED: 
- Integrated 'Customize Your Service' workflow.
- Dynamic duration calculation for custom bookings.
- Full Admin Dashboard features.
- Secured 'My Bookings' retrieval (Client-specific).
"""

import os
import re
import calendar
import secrets
import csv
import io
import hashlib
import json
from flask_babel import Babel, gettext as _
from datetime import datetime, time, timedelta, date
from functools import wraps
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, abort, session, current_app, make_response
from flask_sqlalchemy import SQLAlchemy
from dateutil.relativedelta import relativedelta
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, FloatField, DateField, TimeField, SubmitField, HiddenField, BooleanField
from wtforms.validators import DataRequired, Email, Length, Optional, ValidationError
from werkzeug.utils import secure_filename
from sqlalchemy import func, extract, desc, or_, and_

# ============================================
# Configuration & Setup
# ============================================

app = Flask(__name__)

# Security & Database Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'ptah-studios-secret-key-2025-secure-token')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///ptahstudios.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# File Upload Configuration
app.config['MAX_CONTENT_LENGTH'] = 250 * 1024 * 1024  
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads', 'img')
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'mp4', 'mov', 'webm'}

# Ensure necessary directories exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'portfolio'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'services'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'equipment'), exist_ok=True)

app.config['BABEL_DEFAULT_LOCALE'] = 'en'
app.config['BABEL_SUPPORTED_LOCALES'] = ['en', 'ar']


db = SQLAlchemy(app)

# ============================================
# Context Processors & Utilities
# ============================================


@app.context_processor
def inject_conf_var():
    return dict(get_locale=get_locale)


@app.context_processor
def inject_globals():
    """Injects common variables, auth details, and notifications into all templates."""
    context = {
        'datetime': datetime,
        'date': date,
        'timedelta': timedelta,
        'now': datetime.utcnow(),
        'unseen_leads_count': 0,
        'notification_count': 0,
        'activity_stream': [],
        'unseen_activity_count': 0,
        'current_user': None,
        'is_super_admin': False,
        'user_role': None
    }

    # 1. Unseen Leads
    try:
        if 'Lead' in globals():
            context['unseen_leads_count'] = Lead.query.filter_by(is_seen=False).count()
    except:
        pass

    # 2. User Data
    if 'user_id' in session:
        try:
            user = db.session.get(User, session['user_id'])
            if user:
                context['current_user'] = user
                context['is_super_admin'] = (user.role == 'super_admin')
                context['user_role'] = user.role

                # Notifications
                pending_bookings = Booking.query.filter_by(status='pending').count()
                new_inquiries = ContactInquiry.query.filter_by(status='new').count()
                context['notification_count'] = pending_bookings + new_inquiries + context['unseen_leads_count']
                
                # --- ACTIVITY STREAM LOGIC ---
                # Get last check time (default to very old date if None)
                last_check = user.last_activity_check or datetime(2000, 1, 1)
                
                if context['is_super_admin']:
                    context['activity_stream'] = ProjectActivity.query\
                        .filter(ProjectActivity.timestamp > last_check)\
                        .order_by(ProjectActivity.timestamp.desc())\
                        .limit(10).all()
                    
                    context['unseen_activity_count'] = ProjectActivity.query.filter(
                        ProjectActivity.timestamp > last_check
                    ).count()
                else:
                    # Employee: See only assigned project activities NEWER than last check
                    # (Ensure project_assignments table exists for this to work)
                    context['activity_stream'] = ProjectActivity.query\
                        .join(project_assignments, ProjectActivity.project_id == project_assignments.c.project_id)\
                        .filter(
                            project_assignments.c.user_id == user.id,
                            ProjectActivity.timestamp > last_check
                        )\
                        .order_by(ProjectActivity.timestamp.desc())\
                        .limit(10).all()
                    
                    context['unseen_activity_count'] = ProjectActivity.query\
                        .join(project_assignments, ProjectActivity.project_id == project_assignments.c.project_id)\
                        .filter(
                            project_assignments.c.user_id == user.id,
                            ProjectActivity.timestamp > last_check
                        ).count()
                
                # Debug Print to Console
                print(f"DEBUG: Unseen Activities = {context['unseen_activity_count']}")

        except Exception as e:
            current_app.logger.error(f"Context processor error: {e}")

    return context


def allowed_file(filename):
    """Check if uploaded file has an allowed extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def upload_image(file, subfolder='general'):
    """
    Handles image upload, secure renaming, and path generation.
    Returns the relative path for database storage.
    """
    if not file or not file.filename:
        return None
    
    if not allowed_file(file.filename):
        flash(f'Invalid file type: {file.filename}', 'error')
        return None
    
    # Generate secure, unique filename
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    original_filename = secure_filename(file.filename)
    ext = os.path.splitext(original_filename)[1]
    new_filename = f"{timestamp}_{secrets.token_hex(8)}{ext}"
    
    # Define save path
    save_dir = os.path.join(app.config['UPLOAD_FOLDER'], subfolder)
    os.makedirs(save_dir, exist_ok=True)
    
    try:
        file.save(os.path.join(save_dir, new_filename))
        return f"uploads/img/{subfolder}/{new_filename}"
    except Exception as e:
        current_app.logger.error(f"File upload failed: {str(e)}")
        return None

def generate_slug(title):
    """Generates a URL-friendly slug from a string."""
    if not title: return ""
    slug = title.lower().strip()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[-\s]+', '-', slug)
    return slug.strip('-')



    
# ============================================
# Auth Decorators
# ============================================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def get_locale():
    if 'lang' in session:
        return session['lang']
    return request.accept_languages.best_match(app.config['BABEL_SUPPORTED_LOCALES'])

babel = Babel(app, locale_selector=get_locale)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login', next=request.url))
        
        # Updated to use Session.get() instead of Query.get()
        user = db.session.get(User, session['user_id'])
        if not user or not user.is_admin:
            flash('Access denied. Administrator privileges required.', 'error')
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

# ============================================
# Database Models
# ============================================

project_assignments = db.Table('project_assignments',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('project_id', db.Integer, db.ForeignKey('projects.id'), primary_key=True)
)

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), default='employee')  # 'super_admin' or 'employee'
    is_admin = db.Column(db.Boolean, default=False)
    last_activity_check = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    def set_password(self, password): self.password_hash = hashlib.sha256(password.encode()).hexdigest()
    def check_password(self, password): return self.password_hash == hashlib.sha256(password.encode()).hexdigest()
    project_memberships = db.relationship('ProjectMembership', back_populates='user', cascade='all, delete-orphan')
    def set_password(self, password): self.password_hash = hashlib.sha256(password.encode()).hexdigest()
    def check_password(self, password): return self.password_hash == hashlib.sha256(password.encode()).hexdigest()

    def __repr__(self):
        return f'<User {self.email}>'
    
    @property
    def is_super_admin(self):
        return self.role == 'super_admin'


class ProjectMembership(db.Model):
    """Association object for User-Project relationship with roles."""
    __tablename__ = 'project_memberships'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    role = db.Column(db.String(20), default='Reviewer')  # Supervisor, Editor, Reviewer
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', back_populates='project_memberships')
    project = db.relationship('Project', back_populates='memberships')
    
    def __repr__(self):
        return f'<Membership {self.user.name} - {self.project.title} ({self.role})>'

        
    


class ProjectActivity(db.Model):
    """Log of significant changes within a project."""
    __tablename__ = 'project_activities'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    action = db.Column(db.String(255), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    project = db.relationship('Project', backref='activities')
    user = db.relationship('User')

    
class Service(db.Model):
    """Core services offered by the studio."""
    __tablename__ = 'services'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    name_ar = db.Column(db.String(100))
    slug = db.Column(db.String(100), unique=True, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    base_price = db.Column(db.Float, nullable=False, default=0.0)
    description = db.Column(db.Text) # Short summary
    details = db.Column(db.Text)     # NEW: Long detailed description
    details_ar = db.Column(db.Text)

    is_quotation_only = db.Column(db.Boolean, default=False) # NEW: If true, price is hidden/TBD
    hourly_rate = db.Column(db.Float, nullable=False, default=0.0) # Fallback/Base hourly rate
    
    features = db.Column(db.Text) 
    icon = db.Column(db.String(50), default='film')
    image_url = db.Column(db.String(500))
    display_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    pricing_tiers = db.relationship('ServicePricingTier', back_populates='service', cascade='all, delete-orphan') # NEW
    bookings = db.relationship('Booking', back_populates='service')
    add_ons = db.relationship('ServiceAddOn', back_populates='service', cascade='all, delete-orphan')


    def to_dict(self):
        tiers = {
            t.duration_hours: {
                'price': t.price, 
                'label': t.label,
                'label_ar': t.label_ar # NEW
            } for t in self.pricing_tiers
        }
        return {
            'id': self.id,
            'name': self.name,
            'name_ar': self.name_ar, # NEW
            'slug': self.slug,
            'hourly_rate': self.hourly_rate,
            'is_quotation_only': self.is_quotation_only,
            'details': self.details,
            'details_ar': self.details_ar, # NEW
            'tiers': tiers,
            'icon': self.icon
        }

class ServicePricingTier(db.Model):
    """Specific pricing for specific durations (e.g., 8 hours = 8000 LE)"""
    __tablename__ = 'service_pricing_tiers'
    id = db.Column(db.Integer, primary_key=True)
    service_id = db.Column(db.Integer, db.ForeignKey('services.id'), nullable=False)
    duration_hours = db.Column(db.Float, nullable=False) # e.g., 2.0, 4.0, 8.0
    price = db.Column(db.Float, nullable=False)          # e.g., 4000, 5500, 8000
    label = db.Column(db.String(50))                     # e.g., "Full Day", "Half Day"
    label_ar = db.Column(db.String(50))
    service = db.relationship('Service', back_populates='pricing_tiers')


class Studio(db.Model):
    """Physical studio spaces available for rent."""
    __tablename__ = 'studios'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    name_ar = db.Column(db.String(100))
    slug = db.Column(db.String(100), unique=True, nullable=True)
    display_order = db.Column(db.Integer, default=0)
    persons_capacity = db.Column(db.Integer, nullable=False, default=3)  # Changed from hourly_rate
    description = db.Column(db.Text)
    description_ar = db.Column(db.Text)
    specs = db.Column(db.Text) # JSON or text specs
    specs_ar = db.Column(db.Text)
    image_url = db.Column(db.String(500))
    is_active = db.Column(db.Boolean, default=True)
    
    bookings = db.relationship('Booking', back_populates='studio')


class ServiceAddOn(db.Model):
    """Equipment and extras available for booking."""
    __tablename__ = 'service_add_ons'
    id = db.Column(db.Integer, primary_key=True)
    service_id = db.Column(db.Integer, db.ForeignKey('services.id'), nullable=True)
    name = db.Column(db.String(100), nullable=False)
    name_ar = db.Column(db.String(100))
    last_maintenance_date = db.Column(db.Date, nullable=True)
    category = db.Column(db.String(50), default='general')
    purchase_date = db.Column(db.Date, nullable=True) 
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    image_url = db.Column(db.String(500))
    is_active = db.Column(db.Boolean, default=True)
    
    service = db.relationship('Service', back_populates='add_ons')

    @property
    def maintenance_status(self):
        """
        Calculates maintenance status based on the last maintenance date (or purchase date).
        Does NOT automatically reset. Requires manual intervention.
        """
        # 1. Determine the start of the current cycle
        # Use last_maintenance_date if it exists, otherwise fallback to purchase_date
        start_date = self.last_maintenance_date or self.purchase_date
        
        if not start_date:
            return None
            
        today = date.today()
        cycle_length = 90
        
        # 2. Calculate the specific Due Date for this cycle
        next_due_date = start_date + timedelta(days=cycle_length)
        
        # 3. Calculate time difference
        # If result is positive: Days remaining
        # If result is negative: Days overdue
        days_diff = (next_due_date - today).days
        
        is_overdue = days_diff < 0
        
        return {
            'days_remaining': days_diff if not is_overdue else 0,
            'overdue_days': abs(days_diff) if is_overdue else 0,
            'next_date': next_due_date,
            'is_overdue': is_overdue,
            'is_due_soon': days_diff <= 7 and not is_overdue
        }

class Client(db.Model):
    """Client profile information."""
    __tablename__ = 'clients'
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(120), nullable=False, index=True)
    phone = db.Column(db.String(20))
    company = db.Column(db.String(100))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    bookings = db.relationship('Booking', back_populates='client', cascade='all, delete-orphan')
    projects = db.relationship('Project', back_populates='client', cascade='all, delete-orphan')
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

class Booking(db.Model):
    """Central booking record for services and studios."""
    __tablename__ = 'bookings'
    id = db.Column(db.Integer, primary_key=True)
    booking_reference = db.Column(db.String(20), unique=True, nullable=False)
    
    # Foreign Keys
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey('services.id'), nullable=False)
    studio_id = db.Column(db.Integer, db.ForeignKey('studios.id'), nullable=True)
    is_seen = db.Column(db.Boolean, default=False)
    # Schedule
    booking_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)  # Store actual end time
    duration_hours = db.Column(db.Float, nullable=False)
    
    # Status: pending, confirmed, completed, cancelled, refunded
    status = db.Column(db.String(20), default='pending')
    
    # Financials
    base_price = db.Column(db.Float, nullable=True)      
    studio_price = db.Column(db.Float, default=0.0)       # Cost of Studio Time
    equipment_price = db.Column(db.Float, default=0.0)    # Cost of Add-ons
    total_price = db.Column(db.Float, nullable=False)     # Grand Total
    
    is_paid = db.Column(db.Boolean, default=False)
    payment_method = db.Column(db.String(50))
    
    # Equipment data - stores quantities as JSON
    equipment_data = db.Column(db.Text, nullable=True)  # JSON string of equipment quantities
    
    # Notes
    client_notes = db.Column(db.Text)
    internal_notes = db.Column(db.Text)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    client = db.relationship('Client', back_populates='bookings')
    service = db.relationship('Service', back_populates='bookings')
    studio = db.relationship('Studio', back_populates='bookings')
    booking_add_ons = db.relationship('BookingAddOn', back_populates='booking', cascade='all, delete-orphan')
    project = db.relationship('Project', back_populates='booking', uselist=False)
    
    @staticmethod
    def generate_reference():
        """Generates a unique reference string like PT-202601-ABC123."""
        date_str = datetime.now().strftime('%Y%m')
        random_str = secrets.token_hex(3).upper()
        return f"PT-{date_str}-{random_str}"

    @property
    def end_time_calculated(self):
        """Calculates the end time object based on start_time and duration."""
        # This is a helper, logic handles midnight rollover naively for this demo
        dt = datetime.combine(date.today(), self.start_time) + timedelta(hours=self.duration_hours)
        return dt.time()

class BookingAddOn(db.Model):
    """Link table between Booking and ServiceAddOn with price snapshot."""
    __tablename__ = 'booking_add_ons'
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id'), nullable=False)
    add_on_id = db.Column(db.Integer, db.ForeignKey('service_add_ons.id'), nullable=False)
    price_paid = db.Column(db.Float, nullable=False) # Snapshot price at time of booking
    quantity = db.Column(db.Integer, default=1)
    
    booking = db.relationship('Booking', back_populates='booking_add_ons')
    add_on = db.relationship('ServiceAddOn')

class Project(db.Model):
    """Long-term projects resulting from bookings."""
    __tablename__ = 'projects'
    id = db.Column(db.Integer, primary_key=True)
    project_reference = db.Column(db.String(20), unique=True, nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id'), nullable=True)
    priority = db.Column(db.String(20), default='medium')  # critical, high, medium, low

    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(30), default='planning') # planning, in_progress, review, completed
    progress_percentage = db.Column(db.Integer, default=0)
    description = db.Column(db.Text, nullable=True)
    
    start_date = db.Column(db.Date)
    due_date = db.Column(db.Date)
    completed_date = db.Column(db.Date)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    client = db.relationship('Client', back_populates='projects')
    booking = db.relationship('Booking', back_populates='project')
    milestones = db.relationship('ProjectMilestone', back_populates='project', cascade='all, delete-orphan')
    tasks = db.relationship('ProjectTask', back_populates='project', lazy='dynamic', cascade='all, delete-orphan')
    memberships = db.relationship('ProjectMembership', back_populates='project', cascade='all, delete-orphan')

    @property
    def total_tasks(self):
        return self.tasks.count()
    
    @property
    def team_members(self):
        return [m.user for m in self.memberships]

    @property
    def completed_tasks(self):
        return self.tasks.filter_by(status='completed').count()


    @staticmethod
    def generate_reference():
        return f"PRJ-{datetime.now().strftime('%Y%m')}-{secrets.token_hex(3).upper()}"


# ============================================
# 2. HELPER FUNCTIONS
# ============================================


def check_project_permission(project_id, required_permission='view'):
    """
    Check if current user has permission for a project action.
    
    Permissions hierarchy:
    - Supervisor: all permissions (view, edit, manage_tasks, delete)
    - Editor: view, edit, manage_tasks
    - Reviewer: view only
    
    Returns: (has_permission: bool, user_role: str)
    """
    if 'user_id' not in session:
        return False, None
        
    user = db.session.get(User, session['user_id'])
    
    # Super admins have all permissions
    if user.role == 'super_admin':
        return True, 'super_admin'
    
    # Find membership
    membership = ProjectMembership.query.filter_by(
        user_id=user.id,
        project_id=project_id
    ).first()
    
    if not membership:
        return False, None
    
    role = membership.role
    
    # Permission matrix
    permissions = {
        'Supervisor': ['view', 'edit_project', 'create_task', 'toggle_task', 'delete_project', 'delete_task'],
        'Editor':     ['view', 'toggle_task'], 
        'Reviewer':   ['view']
    }
    
    has_access = required_permission in permissions.get(role, [])
    return has_access, role


def log_project_activity(project_id, action, user_id=None):
    """Helper to save an activity log."""
    try:
        if not user_id and 'user_id' in session:
            user_id = session['user_id']
        
        # Create record
        activity = ProjectActivity(
            project_id=project_id,
            user_id=user_id,
            action=action
        )
        db.session.add(activity)
        db.session.commit()
    except Exception as e:
        print(f"Error logging activity: {e}")


class ProjectMilestone(db.Model):
    """Major milestones for a project."""
    __tablename__ = 'project_milestones'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    due_date = db.Column(db.Date)
    is_completed = db.Column(db.Boolean, default=False)
    completed_at = db.Column(db.DateTime)
    
    project = db.relationship('Project', back_populates='milestones')

class ProjectTask(db.Model):
    """Granular tasks for project management."""
    __tablename__ = 'project_tasks'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(20), default='pending') # pending, in_progress, completed
    priority = db.Column(db.String(10), default='medium') # low, medium, high, critical
    assigned_to = db.Column(db.String(100))
    description = db.Column(db.Text)
    due_date = db.Column(db.Date)
    completed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    project = db.relationship('Project', back_populates='tasks')

class PortfolioItem(db.Model):
    """Portfolio items for the public showcase."""
    __tablename__ = 'portfolio_items'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    title_ar = db.Column(db.String(200))
    slug = db.Column(db.String(200), unique=True, nullable=False)
    client_name = db.Column(db.String(100))
    client_name_ar = db.Column(db.String(100))
    category = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text)
    description_ar = db.Column(db.Text)
    thumbnail_url = db.Column(db.String(500))
    image_urls = db.Column(db.Text) # Newline separated URLs
    video_url = db.Column(db.String(500))
    tags = db.Column(db.String(500))
    tags_ar = db.Column(db.String(500))
    is_featured = db.Column(db.Boolean, default=False)
    display_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    
    # Link to the actual Studio model for booking
    studio_id = db.Column(db.Integer, db.ForeignKey('studios.id'), nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def get_image_list(self):
        if self.image_urls:
            return [url.strip() for url in self.image_urls.split('\n') if url.strip()]
        return []

class ContactInquiry(db.Model):
    __tablename__ = 'contact_inquiries'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    subject = db.Column(db.String(200))
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='new')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Lead(db.Model):
    """Lead management for tracking prospective clients through sales funnel."""
    __tablename__ = 'leads'
    
    # --- THESE CONSTANTS WERE MISSING ---
    STAGE_NEW = 'new'
    STAGE_CONTACTED = 'contacted'
    STAGE_QUALIFIED = 'qualified'
    STAGE_PROPOSAL_SENT = 'proposal_sent'
    STAGE_CONVERTED = 'converted'
    STAGE_LOST = 'lost'
    
    STAGE_CHOICES = [
        (STAGE_NEW, 'New Leads'),
        (STAGE_CONTACTED, 'Contacted'),
        (STAGE_QUALIFIED, 'Qualified'),
        (STAGE_PROPOSAL_SENT, 'Proposal Sent'),
        (STAGE_CONVERTED, 'Converted'),
        (STAGE_LOST, 'Lost')
    ]


    TEMP_COLD = 'cold'
    TEMP_WARM = 'warm'
    TEMP_HOT = 'hot'
    TEMP_CHOICES = [
        (TEMP_COLD, 'Cold'),
        (TEMP_WARM, 'Warm'),
        (TEMP_HOT, 'Hot')
    ]


    SOURCE_WEBSITE = 'website'
    SOURCE_REFERRAL = 'referral'
    SOURCE_SOCIAL = 'social'
    SOURCE_GOOGLE = 'google'
    SOURCE_NEWSLETTER = 'newsletter'
    SOURCE_OTHER = 'other'

    SOURCE_CHOICES = [
        (SOURCE_WEBSITE, 'Website'),
        (SOURCE_REFERRAL, 'Referral'),
        (SOURCE_SOCIAL, 'Social Media'),
        (SOURCE_GOOGLE, 'Google Search'),
        (SOURCE_NEWSLETTER, 'Newsletter'), 
        (SOURCE_OTHER, 'Other')
    ]

    
    # ------------------------------------
    
    
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False, index=True)
    phone = db.Column(db.String(20))
    company = db.Column(db.String(100))
    is_seen = db.Column(db.Boolean, default=False)
    
    # NEW FIELDS
    company_size = db.Column(db.String(50))
    service_interest = db.Column(db.String(100))
    
    # Tracking
    source = db.Column(db.String(50), default=SOURCE_WEBSITE)
    stage = db.Column(db.String(20), default=STAGE_NEW, index=True)
    temperature = db.Column(db.String(10), default=TEMP_COLD)
    source_detail = db.Column(db.String(255))
    lead_score = db.Column(db.Integer, default=0)
    
    # Content
    subject = db.Column(db.String(200))
    original_message = db.Column(db.Text)
    admin_notes = db.Column(db.Text)
    
    # Metadata
    last_contact_at = db.Column(db.DateTime)
    follow_up_date = db.Column(db.Date)
    converted_at = db.Column(db.DateTime)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    activities = db.relationship('LeadActivity', back_populates='lead', cascade='all, delete-orphan', order_by='LeadActivity.created_at.desc()')
    
    def get_stage_display(self):
        return dict(self.STAGE_CHOICES).get(self.stage, self.stage)
    
    def add_note(self, note):
        notes = self.admin_notes.split('\n') if self.admin_notes else []
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
        notes.append(f"[{timestamp}] {note}")
        self.admin_notes = '\n'.join(notes)

    
    def get_temperature_display(self):
        return self.temperature.capitalize()
    
    def get_score_color(self):
        if self.lead_score >= 70:
            return 'hot'
        elif self.lead_score >= 40:
            return 'warm'
        return 'cold'
    
    def get_notes_list(self):
        if self.admin_notes:
            return [n.strip() for n in self.admin_notes.split('\n') if n.strip()]
        return []
    
   


class LeadActivity(db.Model):
    __tablename__ = 'lead_activities'

    TYPE_CALL = 'call'
    TYPE_EMAIL = 'email'
    TYPE_MEETING = 'meeting'
    TYPE_NOTE = 'note'
    TYPE_STAGE_CHANGE = 'stage_change'
    
    TYPE_CHOICES = [
        (TYPE_CALL, 'Phone Call'),
        (TYPE_EMAIL, 'Email'),
        (TYPE_MEETING, 'Meeting'),
        (TYPE_NOTE, 'Note'),
        (TYPE_STAGE_CHANGE, 'Stage Change')
    ]
    
    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey('leads.id'), nullable=False)
    activity_type = db.Column(db.String(20)) # call, email, note, stage_change
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.String(100))
    lead = db.relationship('Lead', back_populates='activities')


class GeneralService(db.Model):
    """
    Services displayed on the Website (Index/Services pages).
    Separated from Booking logic.
    """
    __tablename__ = 'general_services'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    name_ar = db.Column(db.String(100))
    slug = db.Column(db.String(100), unique=True, nullable=False)
    
    # Visuals
    icon = db.Column(db.String(50), default='star')
    category = db.Column(db.String(50)) # e.g., 'production', 'post_production'
    description = db.Column(db.Text)
    features = db.Column(db.Text) # Pipe-separated features for the card
    
    description_ar = db.Column(db.Text) # NEW
    features_ar = db.Column(db.Text)
    linked_booking_service_id = db.Column(db.Integer, db.ForeignKey('services.id'), nullable=True)
    linked_service = db.relationship('Service', backref='marketing_pages')
    
    display_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def get_features_list(self):
        if self.features:
            return [f.strip() for f in self.features.split('|') if f.strip()]
        return []

    def get_features_list_ar(self):
        if self.features_ar:
            return [f.strip() for f in self.features_ar.split('|') if f.strip()]
        return []
    
# ============================================
# Forms (WTForms)
# ============================================

class Package(db.Model):
    """Special promotional packages."""
    __tablename__ = 'packages'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    name_ar = db.Column(db.String(100))
    description = db.Column(db.Text)
    description_ar = db.Column(db.Text)
    original_price = db.Column(db.Float, nullable=False, default=0.0)
    package_price = db.Column(db.Float, nullable=False, default=0.0)
    duration_hours = db.Column(db.Float, nullable=False, default=0.0)
    icon = db.Column(db.String(50), default='gift')
    features = db.Column(db.Text) # Pipe-separated string
    features_ar = db.Column(db.Text)
    display_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def discount_percentage(self):
        if self.original_price > 0:
            return int(((self.original_price - self.package_price) / self.original_price) * 100)
        return 0
        
    def get_features_list(self):
        if self.features:
            return [f.strip() for f in self.features.split('|') if f.strip()]
        return []

    # NEW: Helper for Arabic Features
    def get_features_list_ar(self):
        if self.features_ar:
            return [f.strip() for f in self.features_ar.split('|') if f.strip()]
        return []



class BTSProject(db.Model):
    """A container 'Folder' for Behind The Scenes content."""
    __tablename__ = 'bts_projects'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    title_ar = db.Column(db.String(200))
    slug = db.Column(db.String(200), unique=True, nullable=False)
    description = db.Column(db.Text)
    description_ar = db.Column(db.Text)
    thumbnail_url = db.Column(db.String(500)) # Cover image for the folder
    event_date = db.Column(db.Date, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    media = db.relationship('BTSMedia', back_populates='project', cascade='all, delete-orphan')

    @property
    def media_count(self):
        return len(self.media)



class BTSMedia(db.Model):
    """Photos and Videos inside a BTS Project."""
    __tablename__ = 'bts_media'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('bts_projects.id'), nullable=False)
    file_url = db.Column(db.String(500), nullable=False)
    file_type = db.Column(db.String(20)) # 'image' or 'video'
    caption = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    project = db.relationship('BTSProject', back_populates='media')


class BookingForm(FlaskForm):
    """
    Unified Booking Form.
    Handles both standard wizard flow and custom service flow.
    """
    service_id = HiddenField('Service', validators=[DataRequired()])
    studio_id = HiddenField('Studio') 
    
    booking_date = DateField('Preferred Date', validators=[DataRequired()])
    
    # CHANGED: Changed from SelectField to StringField to accept values from <input type="time">
    # The frontend validation and backend logic handle the actual time parsing.
    start_time = StringField('Start Time', validators=[DataRequired()])
    
    # CHANGED: Changed from SelectField to StringField
    end_time = StringField('End Time', validators=[Optional()])

    # Client Details
    first_name = StringField('First Name', validators=[DataRequired(), Length(min=2)])
    last_name = StringField('Last Name', validators=[DataRequired(), Length(min=2)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    phone = StringField('Phone', validators=[DataRequired(), Length(max=20)])
    company = StringField('Company', validators=[Length(max=100)])
    
    client_notes = TextAreaField('Project Details / Notes')
    submit = SubmitField('Submit Booking Request')


def validate_egyptian_phone(form, field):
    if not field.data:
        return  
    
    pattern = r'^(\+20|0)1[0125]\d{8}$'
    
    # Strip spaces or dashes just in case the user adds them
    clean_number = field.data.strip().replace(' ', '').replace('-', '')
    
    if not re.match(pattern, clean_number):
        raise ValidationError('Invalid format. Must be Egyptian number (e.g. 010xxxx or +2010xxxx).')
    

class ContactForm(FlaskForm):
    """Updated Contact Form matching the design."""
    name = StringField('Full Name', validators=[DataRequired(), Length(min=2)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    phone = StringField('Phone', validators=[Optional(), Length(max=20), validate_egyptian_phone])
    company = StringField('Company', validators=[Optional(), Length(max=100)])

    company_size = SelectField('Company Size', choices=[
        ('', 'Select size'),
        ('1-10', '1-10 employees'),
        ('11-50', '11-50 employees'),
        ('51-200', '51-200 employees'),
        ('200+', '200+ employees')
    ], validators=[Optional()])
    
    service_interest = SelectField('Service Interested In', choices=[
        ('', 'Select service'),
        ('Video Production', 'Video Production'),
        ('Podcast Production', 'Podcast Production'),
        ('Product Advertising', 'Product Advertising'),
        ('Corporate Services', 'Corporate Services'),
        ('Social Media Content', 'Social Media Content'),
        ('Other', 'Other')
    ], validators=[Optional()])
    
    how_did_you_know = SelectField('How did you know about us?', choices=[
        ('', 'Select an option'),
        ('website', 'Website'),
        ('referral', 'Referral'),
        ('social', 'Social Media'),
        ('google', 'Google Search'),
        ('other', 'Other')
    ], validators=[Optional()])
    

    source_detail = StringField('Please Specify', validators=[Optional(), Length(max=255)])
    referrer_number = StringField('Referrer Number', validators=[Optional(), Length(max=20), validate_egyptian_phone])
    message = TextAreaField('Message', validators=[DataRequired(), Length(min=10)])
    submit = SubmitField('Send Message')


class PortfolioForm(FlaskForm):
    """Admin form for managing portfolio items."""
    title = StringField('Title', validators=[DataRequired()])
    slug = StringField('Slug (Optional)')
    client_name = StringField('Client Name')
    category = SelectField('Category', choices=[
        ('video', 'Video Production'), 
        ('audio', 'Audio/Podcast'), 
        ('photo', 'Photography'), 
        ('campaign', 'Ad Campaign')
    ])
    description = TextAreaField('Description')
    video_url = StringField('Video Embed URL')
    tags = StringField('Tags (comma separated)')
    display_order = FloatField('Display Order', default=0)
    is_featured = BooleanField('Featured on Homepage')
    is_active = BooleanField('Active', default=True)
    studio_id = SelectField('Link to Studio (for booking)', coerce=int, validators=[Optional()])
    submit = SubmitField('Save Portfolio Item')
    
    def __init__(self, *args, **kwargs):
        super(PortfolioForm, self).__init__(*args, **kwargs)
        # Populate studio choices
        studios = Studio.query.filter_by(is_active=True).order_by(Studio.name).all()
        self.studio_id.choices = [(0, 'No studio linked')] + [(s.id, s.name) for s in studios]

# ============================================
# Public Routes
# ============================================

@app.route('/')
def index():
    """Home page with featured content."""
    featured_items = PortfolioItem.query.filter_by(is_featured=True, is_active=True).order_by(PortfolioItem.display_order).limit(6).all()
    services = GeneralService.query.filter_by(is_active=True).order_by(GeneralService.display_order).all()
    packages = Package.query.filter_by(is_active=True).order_by(Package.display_order).all()
    return render_template('public/index.html', featured_studios=featured_items, services=services,packages=packages)

@app.route('/set_language/<language>')
def set_language(language):
    if language in app.config['BABEL_SUPPORTED_LOCALES']:
        session['lang'] = language
    return redirect(request.referrer or url_for('index'))


@app.route('/services')
def services():
    """List of all services."""
    services_list = GeneralService.query.filter_by(is_active=True).order_by(GeneralService.display_order).all()
    return render_template('public/services.html', services=services_list)

@app.route('/services/<slug>')
def service_detail(slug):
    """Detail view for a specific service."""
    service = GeneralService.query.filter_by(slug=slug, is_active=True).first_or_404()
    return render_template('public/service_detail.html', service=service)

@app.route('/portfolio')
def portfolio():
    """Portfolio gallery with filtering."""
    category = request.args.get('category')
    query = PortfolioItem.query.filter_by(is_active=True)
    if category:
        query = query.filter_by(category=category)
    items = query.order_by(PortfolioItem.display_order).all()
    
    # Get category counts for filter menu
    categories = db.session.query(
        PortfolioItem.category, func.count(PortfolioItem.id)
    ).filter(PortfolioItem.is_active == True).group_by(PortfolioItem.category).all()
    
    cat_list = [{'name': c[0], 'count': c[1]} for c in categories]
    
    return render_template('public/portfolio.html', items=items, categories=cat_list, selected_category=category)

@app.route('/portfolio/<slug>')
def portfolio_item(slug):
    """Single portfolio project view."""
    item = PortfolioItem.query.filter_by(slug=slug, is_active=True).first_or_404()
    
    # Get the related studio if linked
    linked_studio = None
    if item.studio_id:
        linked_studio = db.session.get(Studio, item.studio_id)
    
    return render_template('public/portfolio_item.html', item=item, linked_studio=linked_studio)


@app.route('/pricing')
def pricing():
    """Pricing overview page."""
    services_list = Service.query.filter_by(is_active=True).order_by(Service.display_order).all()
    return render_template('public/pricing.html', services=services_list)


def is_time_slot_taken(studio_id, booking_date, start_time, end_time):
    """
    Checks if a specific time slot is already booked for a studio.
    Returns True if taken, False if available.
    """
    if not studio_id:
        return False
        
    # Logic: (StartA < EndB) and (EndA > StartB)
    # We check for any booking that is NOT cancelled and overlaps.
    conflict = Booking.query.filter(
        Booking.studio_id == studio_id,
        Booking.booking_date == booking_date,
        Booking.status.notin_(['cancelled', 'rejected', 'refunded']),
        Booking.start_time < end_time,
        Booking.end_time > start_time
    ).first()
    
    return conflict is not None



@app.route('/booking', methods=['GET', 'POST'])
def booking():
    """
    Main Booking Route.
    Handles standard wizard logic, Custom Service logic, and User Dashboard.
    """
    services_list = Service.query.filter_by(is_active=True).order_by(Service.display_order).all()
    studios_list = Studio.query.filter_by(is_active=True).order_by(Studio.display_order.asc()).all()
    
    # Organize equipment for UI rendering
    equipment = ServiceAddOn.query.filter_by(is_active=True).all()
    equipment_by_cat = {}
    for item in equipment:
        cat = item.category if item.category else 'general'
        if cat not in equipment_by_cat:
            equipment_by_cat[cat] = []
        equipment_by_cat[cat].append(item)
    
    # --- FETCH USER'S PAST BOOKINGS (SECURE & CLIENT SPECIFIC) ---
    my_bookings = []
    current_user = None
    
    if 'user_id' in session:
        current_user = User.query.get(session['user_id'])
        if current_user:
            user_email = current_user.email.lower().strip()
            
            # Explicit eager loading of all relationships
            my_bookings = db.session.query(Booking)\
                .join(Client, Booking.client_id == Client.id)\
                .join(Service, Booking.service_id == Service.id)\
                .outerjoin(Studio, Booking.studio_id == Studio.id)\
                .filter(func.lower(Client.email) == user_email)\
                .order_by(Booking.booking_date.desc(), Booking.start_time.desc())\
                .all()
            
            # DEBUG: Log what we found
            current_app.logger.info(f"Found {len(my_bookings)} bookings for {user_email}")
    
    form = BookingForm()
    
    # Pre-fill form if user is logged in
    if request.method == 'GET' and current_user and not form.email.data:
        form.email.data = current_user.email
        if current_user.name:
            names = current_user.name.split(' ', 1)
            form.first_name.data = names[0]
            if len(names) > 1: form.last_name.data = names[1]
        
        # Check if client record exists for more details
        existing_client = Client.query.filter(func.lower(Client.email) == current_user.email.lower()).first()
        if existing_client:
            form.first_name.data = existing_client.first_name
            form.last_name.data = existing_client.last_name
            form.phone.data = existing_client.phone
            form.company.data = existing_client.company

    # ============================================
    # HANDLE FORM SUBMISSION - BOTH TYPES
    # ============================================
    if request.method == 'POST':
        # CRITICAL: Detect which form was submitted using marker field
        is_custom_form = 'custom_booking_marker' in request.form
        
        current_app.logger.info(f"Form submitted. Is custom: {is_custom_form}")
        
        if is_custom_form:
            # ========== CUSTOM SERVICE BOOKING (PRESERVED) ==========
            try:
                current_app.logger.info("Processing CUSTOM booking")
                
                # Extract and validate fields
                email = request.form.get('email', '').strip().lower()
                first_name = request.form.get('first_name', '').strip()
                last_name = request.form.get('last_name', '').strip()
                phone = request.form.get('phone', '').strip()
                company = request.form.get('company', '').strip()
                notes = request.form.get('client_notes', '')
                
                current_app.logger.info(f"Custom booking for: {first_name} {last_name} ({email})")
                
                if not all([email, first_name, last_name, phone]):
                    flash('Please fill in all required fields (Name, Email, Phone).', 'error')
                    return redirect(url_for('booking') + '#custom-section')
                
                # Get custom service
                custom_service = Service.query.filter_by(slug='custom-package').first()
                if not custom_service:
                    current_app.logger.error("Custom service not found!")
                    flash('Custom service not available.', 'error')
                    return redirect(url_for('booking'))
                
                # Get studio from radio buttons
                studio_id = request.form.get('studio_radio_custom')
                if not studio_id:
                    flash('Please select a studio location.', 'error')
                    return redirect(url_for('booking') + '#custom-section')
                
                studio = Studio.query.get(studio_id)
                if not studio:
                    flash('Invalid studio selection.', 'error')
                    return redirect(url_for('booking'))
                
                # Get date and time
                booking_date_str = request.form.get('booking_date')
                start_time_str = request.form.get('start_time')
                end_time_str = request.form.get('end_time')
                
                if not all([booking_date_str, start_time_str, end_time_str]):
                    flash('Please select date, start time, and end time.', 'error')
                    return redirect(url_for('booking') + '#custom-section')
                
                try:
                    booking_date = datetime.strptime(booking_date_str, '%Y-%m-%d').date()
                    start_time = datetime.strptime(start_time_str, '%H:%M')
                    end_time = datetime.strptime(end_time_str, '%H:%M')
                    
                    if is_time_slot_taken(studio.id, booking_date, start_time.time(), end_time.time()):
                        flash('Error: This time slot was just booked by another client.', 'error')
                        return redirect(url_for('booking') + '#custom-section')

                    if end_time <= start_time:
                        flash('End time must be after start time.', 'error')
                        return redirect(url_for('booking') + '#custom-section')
                    
                    duration_hours = (end_time - start_time).seconds / 3600.0
                    
                    if duration_hours < 2:
                        flash('Minimum booking duration is 2 hours.', 'error')
                        return redirect(url_for('booking') + '#custom-section')
                    
                    booking_start_time = start_time.time()
                    
                except ValueError as e:
                    flash('Invalid date or time format.', 'error')
                    return redirect(url_for('booking'))
                
                # Pricing - Custom service uses simple hourly multiplication
                custom_hourly_rate = custom_service.hourly_rate if custom_service.hourly_rate else 0.0
                service_cost = custom_hourly_rate * duration_hours
                studio_cost = 0.0   # Studio is free, only pay for equipment
                
                # Get add-ons with quantities
                equipment_cost = 0.0
                selected_addons = []
                
                # Check for new equipment_data JSON format first
                equipment_data_json = request.form.get('equipment_data', '{}')
                try:
                    equipment_data = json.loads(equipment_data_json)
                    if equipment_data:
                        addon_ids = [int(aid) for aid in equipment_data.keys()]
                        addons = ServiceAddOn.query.filter(ServiceAddOn.id.in_(addon_ids)).all()
                        for addon in addons:
                            quantity = int(equipment_data.get(str(addon.id), 1))
                            if quantity > 0:
                                equipment_cost += addon.price * quantity
                                selected_addons.append({'addon': addon, 'quantity': quantity})
                except (json.JSONDecodeError, ValueError) as e:
                    # Fall back to old format
                    addon_ids = request.form.getlist('addons[]')
                    if addon_ids:
                        addons = ServiceAddOn.query.filter(ServiceAddOn.id.in_(addon_ids)).all()
                        for addon in addons:
                            quantity = int(request.form.get(f'addon_quantity_{addon.id}', 1))
                            if quantity > 0:
                                equipment_cost += addon.price * quantity
                                selected_addons.append({'addon': addon, 'quantity': quantity})
                
                total_cost = service_cost + studio_cost + equipment_cost
                
                # Find or create client
                client = Client.query.filter(func.lower(Client.email) == email).first()
                if not client:
                    client = Client(
                        first_name=first_name, last_name=last_name, email=email, phone=phone, company=company
                    )
                    db.session.add(client)
                    db.session.flush()
                else:
                    if phone: client.phone = phone
                    if company: client.company = company
                
                # Create booking
                booking_ref = Booking.generate_reference()
                booking = Booking(
                    booking_reference=booking_ref,
                    client_id=client.id,
                    service_id=custom_service.id,
                    studio_id=studio.id,
                    booking_date=booking_date,
                    start_time=booking_start_time,
                    end_time=end_time.time(),
                    duration_hours=duration_hours,
                    base_price=service_cost,
                    studio_price=studio_cost,
                    equipment_price=equipment_cost,
                    total_price=total_cost,
                    equipment_data=equipment_data_json,
                    client_notes=notes,
                    status='pending'
                )
                db.session.add(booking)
                db.session.flush()
                
                # Add equipment links
                for item in selected_addons:
                    link = BookingAddOn(
                        booking_id=booking.id,
                        add_on_id=item['addon'].id,
                        price_paid=item['addon'].price * item['quantity'],
                        quantity=item['quantity']
                    )
                    db.session.add(link)
                
                db.session.commit()
                flash('Your custom booking has been submitted successfully!', 'success')
                return redirect(url_for('booking_success', reference=booking.booking_reference))
                
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Custom booking ERROR: {str(e)}")
                flash(f'An error occurred: {str(e)}', 'error')
                return redirect(url_for('booking'))
        
        elif form.validate_on_submit():
            # ========== STANDARD SERVICE BOOKING (UPDATED WITH TIERS) ==========
            try:
                current_app.logger.info("Processing STANDARD booking")
                
                booking_email = form.email.data.lower().strip()
                
                service_id = form.service_id.data
                service = Service.query.get(service_id)
                if not service:
                    flash('Invalid service selection.', 'error')
                    return redirect(url_for('booking'))
                
                current_app.logger.info(f"Service: {service.name}")
                
                studio_id = form.studio_id.data
                if not studio_id:
                    studio_id = request.form.get('studio_radio')
                
                studio = Studio.query.get(studio_id)
                if not studio:
                    flash('Please select a studio location.', 'error')
                    return redirect(url_for('booking'))
                
                # Time Handling
                start_time_str = request.form.get('start_time', '09:00')
                end_time_str = request.form.get('end_time', '17:00')
                
                try:
                    booking_start_time = datetime.strptime(start_time_str, '%H:%M').time()
                    end_time = datetime.strptime(end_time_str, '%H:%M')
                    start_dt = datetime.strptime(start_time_str, '%H:%M')
                    
                    if end_time <= start_dt:
                        end_time = end_time + timedelta(days=1)

                    final_end_time = end_time.time() if 'end_time' in locals() else (start_dt + timedelta(hours=duration_hours)).time()
                    
                    if is_time_slot_taken(studio.id, form.booking_date.data, booking_start_time, final_end_time):
                        flash('Error: This time slot is unavailable.', 'error')
                        return redirect(url_for('booking'))
                        
                    duration_hours = (end_time - start_dt).seconds / 3600.0
                    
                    if duration_hours < 2:
                        flash('Minimum booking duration is 2 hours.', 'error')
                        return redirect(url_for('booking'))
                    
                except (ValueError, TypeError):
                    booking_start_time = time(9, 0)
                    duration_hours = 4.0
                    final_end_time = (datetime.combine(date.today(), booking_start_time) + timedelta(hours=4)).time()
                
                # --- [START] UPDATED PRICING LOGIC ---
                service_cost = 0.0
                
                if service.is_quotation_only:
                    service_cost = 0.0 
                else:
                    # 1. Fetch all tiers for this service, sorted by duration (Ascending)
                    tiers = sorted(service.pricing_tiers, key=lambda t: t.duration_hours)
                    
                    if not tiers:
                        # Fallback if no tiers exist: Pure Overtime/Hourly calculation
                        hourly_rate = service.hourly_rate if service.hourly_rate else 0.0
                        service_cost = hourly_rate * duration_hours
                    else:
                        # 2. Find the highest tier that fits within the duration
                        # e.g. Duration 10, Tiers [2, 4, 6, 8] -> Match 8
                        applicable_tier = None
                        for tier in tiers:
                            if duration_hours >= tier.duration_hours:
                                applicable_tier = tier
                            else:
                                break # Stop if next tier is larger than duration
                        
                        if applicable_tier:
                            # Base cost is the tier price
                            base_cost = applicable_tier.price
                            
                            # Calculate Overtime
                            extra_hours = duration_hours - applicable_tier.duration_hours
                            
                            # Ensure small floating point errors don't count as overtime (e.g. 0.00001)
                            if extra_hours < 0.1: 
                                extra_hours = 0
                                
                            overtime_rate = service.hourly_rate if service.hourly_rate else 0.0
                            overtime_cost = extra_hours * overtime_rate
                            
                            service_cost = base_cost + overtime_cost
                            
                            current_app.logger.info(f"Tier Pricing: Base {base_cost} (for {applicable_tier.duration_hours}h) + Overtime {overtime_cost} ({extra_hours}h * {overtime_rate})")
                        else:
                            # Duration is smaller than the smallest tier (e.g. 1 hour booking, min tier 2)
                            # Policy: Charge the minimum tier price
                            min_tier = tiers[0]
                            service_cost = min_tier.price
                            current_app.logger.info(f"Duration {duration_hours} < Min Tier {min_tier.duration_hours}. Charged Min Price: {service_cost}")

                studio_cost = 0.0
                # --- [END] UPDATED PRICING LOGIC ---
                
                # Equipment Logic (Preserved)
                equipment_cost = 0.0
                selected_addons = []
                
                equipment_data_json = request.form.get('equipment_data', '{}')
                try:
                    equipment_data = json.loads(equipment_data_json)
                    if equipment_data:
                        addon_ids = [int(aid) for aid in equipment_data.keys()]
                        addons = ServiceAddOn.query.filter(ServiceAddOn.id.in_(addon_ids)).all()
                        for addon in addons:
                            quantity = int(equipment_data.get(str(addon.id), 1))
                            if quantity > 0:
                                equipment_cost += addon.price * quantity
                                selected_addons.append({'addon': addon, 'quantity': quantity})
                except (json.JSONDecodeError, ValueError):
                    # Fallback for standard flow if needed, though usually handled by JS now
                    pass
                
                total_cost = service_cost + studio_cost + equipment_cost
                
                # Client
                client = Client.query.filter(func.lower(Client.email) == booking_email).first()
                if not client:
                    client = Client(
                        first_name=form.first_name.data,
                        last_name=form.last_name.data,
                        email=booking_email,
                        phone=form.phone.data,
                        company=form.company.data
                    )
                    db.session.add(client)
                    db.session.flush()
                else:
                    if form.phone.data: client.phone = form.phone.data
                    if form.company.data: client.company = form.company.data
                
                # Create Booking
                booking_ref = Booking.generate_reference()
                booking = Booking(
                    booking_reference=booking_ref,
                    client_id=client.id,
                    service_id=service.id,
                    studio_id=studio.id,
                    booking_date=form.booking_date.data,
                    start_time=booking_start_time,
                    end_time=final_end_time,
                    duration_hours=duration_hours,
                    base_price=service_cost,
                    studio_price=studio_cost,
                    equipment_price=equipment_cost,
                    total_price=total_cost,
                    equipment_data=equipment_data_json,
                    client_notes=form.client_notes.data,
                    status='pending'
                )
                db.session.add(booking)
                db.session.flush()
                
                for item in selected_addons:
                    link = BookingAddOn(
                        booking_id=booking.id,
                        add_on_id=item['addon'].id,
                        price_paid=item['addon'].price * item['quantity'],
                        quantity=item['quantity']
                    )
                    db.session.add(link)
                
                db.session.commit()
                
                current_app.logger.info(f"✓ Standard booking COMMITTED: {booking.booking_reference}")
                flash('Your booking has been submitted successfully!', 'success')
                return redirect(url_for('booking_success', reference=booking.booking_reference))
                
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Standard booking ERROR: {str(e)}")
                import traceback
                current_app.logger.error(traceback.format_exc())
                flash(f'An error occurred: {str(e)}', 'error')
                return redirect(url_for('booking'))
        
        else:
            current_app.logger.warning(f"Form validation failed: {form.errors}")
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f'Error in {field}: {error}', 'error')

    return render_template('public/booking.html',
                         form=form,
                         services=services_list,
                         studios=studios_list,
                         equipment_by_cat=equipment_by_cat,
                         today_date=datetime.now().strftime('%Y-%m-%d'),
                         my_bookings=my_bookings)


@app.route('/booking/success/<reference>')
def booking_success(reference):
    """Confirmation page after successful booking."""
    booking = Booking.query.filter_by(booking_reference=reference).first_or_404()
    return render_template('public/booking_success.html', booking=booking)


# Add this route to your Flask app

@app.route('/api/notifications/new-bookings')
@admin_required
def api_new_bookings_notifications():
    """API endpoint to fetch booking notifications."""
    try:
        new_count = Booking.query.filter_by(status='pending', is_seen=False).count()
        
        pending_bookings = Booking.query.filter_by(status='pending').order_by(Booking.created_at.desc()).all()
        
        # Format notifications list
        notifications = []
        for booking in pending_bookings:
            client_name = booking.client.full_name if booking.client else 'Unknown Client'
            service_name = booking.service.name if booking.service else 'Unknown Service'
            
            notifications.append({
                'id': booking.id,
                'client_name': client_name,
                'service_name': service_name,
                'client_phone': booking.client.phone if booking.client else 'N/A',
                'time': booking.booking_date.strftime('%b %d, %I:%M %p'),
                'time_ago': format_time_ago(booking.created_at),
                'url': url_for('booking_details_view', highlight=booking.id),
                'is_new': not booking.is_seen,
                'total_price': booking.total_price,
                'is_quote': booking.service.is_quotation_only if booking.service else False,
                'initial_cost': (booking.studio_price + booking.equipment_price)
            })
        
        return jsonify({
            'success': True,
            'count': new_count,
            'notifications': notifications
        })
        
    except Exception as e:
        current_app.logger.error(f"Error fetching notifications: {str(e)}")
        return jsonify({'success': False, 'count': 0, 'notifications': []})

@app.route('/api/notifications/mark-seen', methods=['POST'])
@admin_required
def mark_notifications_seen():
    """Mark all pending bookings as seen."""
    try:
        unseen = Booking.query.filter_by(status='pending', is_seen=False).all()
        for b in unseen:
            b.is_seen = True
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})



def format_time_ago(dt):
    """Format datetime as 'X time ago' string."""
    now = datetime.utcnow()
    diff = now - dt
    
    if diff.days > 0:
        return f"{diff.days} day{'s' if diff.days != 1 else ''} ago"
    elif diff.seconds > 3600:
        hours = diff.seconds // 3600
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    elif diff.seconds > 60:
        minutes = diff.seconds // 60
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    else:
        return "Just now"
    
    
@app.route('/about-us')
def about_us():
    """About Us page."""
    return render_template('public/about-us.html')

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    form = ContactForm()
    if form.validate_on_submit():
        # Get the source from form or default to 'website'
        how_knew = form.how_did_you_know.data if form.how_did_you_know.data else 'website'
        detail_val = None

        if how_knew == 'referral':
            # Combine Name and Number for the database
            name = form.source_detail.data
            number = form.referrer_number.data
            detail_val = f"Referrer: {name} | Phone: {number}"
        elif how_knew == 'other':
            detail_val = form.source_detail.data

        # Create Lead directly
        lead = Lead(
            name=form.name.data,
            email=form.email.data,
            phone=form.phone.data,
            company=form.company.data,
            company_size=form.company_size.data,
            service_interest=form.service_interest.data,
            original_message=form.message.data,
            source=how_knew,
            source_detail=detail_val,
            stage='new',
            lead_score=20 # Higher starting score for detailed form
        )
        db.session.add(lead)
        db.session.flush() # Generate ID
        
        # Log initial activity
        activity = LeadActivity(
            lead_id=lead.id,
            activity_type='note',
            description='Lead created via Contact Form.',
            created_by='System'
        )
        db.session.add(activity)
        db.session.commit()
        
        flash('Message sent successfully! We will contact you shortly.', 'success')
        return redirect(url_for('contact'))
        
    return render_template('public/contact.html', form=form)

    
# ============================================
# User Dashboard Routes
# ============================================

@app.route('/user/dashboard')
@login_required
def user_dashboard():
    """
    User Dashboard - Shows only the logged-in user's bookings.
    Similar to admin bookings view but restricted to user's own data.
    """
    # Get current logged-in user
    current_user = User.query.get(session['user_id'])
    
    if not current_user:
        flash('Please log in to access your dashboard.', 'warning')
        return redirect(url_for('login'))
    
    # Fetch ONLY this user's bookings by matching email
    user_email = current_user.email.lower().strip()
    
    user_bookings = db.session.query(Booking)\
        .join(Client, Booking.client_id == Client.id)\
        .join(Service, Booking.service_id == Service.id)\
        .outerjoin(Studio, Booking.studio_id == Studio.id)\
        .filter(func.lower(Client.email) == user_email)\
        .order_by(Booking.booking_date.desc(), Booking.start_time.desc())\
        .all()
    
    # Get equipment list for details
    equipment_list = ServiceAddOn.query.filter_by(is_active=True).all()
    
    # Calculate stats
    total_bookings = len(user_bookings)
    pending_bookings = len([b for b in user_bookings if b.status == 'pending'])
    confirmed_bookings = len([b for b in user_bookings if b.status == 'confirmed'])
    completed_bookings = len([b for b in user_bookings if b.status == 'completed'])
    
    # Get upcoming bookings (future dates or today)
    today = date.today()
    upcoming_bookings = [b for b in user_bookings if b.booking_date >= today]
    past_bookings = [b for b in user_bookings if b.booking_date < today]
    
    return render_template(
        'user/dashboard.html',
        bookings=user_bookings,
        equipment_list=equipment_list,
        total_bookings=total_bookings,
        pending_bookings=pending_bookings,
        confirmed_bookings=confirmed_bookings,
        completed_bookings=completed_bookings,
        upcoming_count=len(upcoming_bookings),
        past_count=len(past_bookings),
        current_user=current_user
    )


@app.route('/user/bookings')
@login_required
def user_bookings():
    """
    Alternative route alias for user bookings.
    Redirects to the main user dashboard.
    """
    return redirect(url_for('user_dashboard'))


@app.route('/user/booking/<int:booking_id>')
@login_required
def user_booking_detail(booking_id):
    """
    View details of a specific booking.
    User can only view their own bookings.
    """
    current_user = User.query.get(session['user_id'])
    
    if not current_user:
        flash('Please log in to view booking details.', 'warning')
        return redirect(url_for('login'))
    
    # Get the booking
    booking = Booking.query.get_or_404(booking_id)
    
    # Verify ownership - check if booking's client email matches user's email
    user_email = current_user.email.lower().strip()
    client_email = booking.client.email.lower().strip() if booking.client else ''
    
    if user_email != client_email:
        flash('You do not have permission to view this booking.', 'error')
        return redirect(url_for('user_dashboard'))
    
    # Get equipment list
    equipment_list = ServiceAddOn.query.filter_by(is_active=True).all()
    
    return render_template(
        'user/booking_detail.html',
        booking=booking,
        equipment_list=equipment_list,
        current_user=current_user
    )


@app.route('/api/check_availability')
def check_availability():
    """API to return booked slots for a specific studio and date."""
    studio_id = request.args.get('studio_id', type=int)
    date_str = request.args.get('date')
    
    if not studio_id or not date_str:
        return jsonify({'booked_slots': []})
    
    try:
        query_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        
        # Fetch bookings for this studio on this date
        # Exclude 'cancelled' or 'rejected' bookings so they become available again
        bookings = Booking.query.filter(
            Booking.studio_id == studio_id,
            Booking.booking_date == query_date,
            Booking.status.notin_(['cancelled', 'rejected']) 
        ).all()
        
        booked_slots = []
        for b in bookings:
            # Calculate the end time based on duration if not explicitly stored, 
            # though your model has end_time.
            start_str = b.start_time.strftime('%H:%M')
            end_str = b.end_time.strftime('%H:%M')
            
            booked_slots.append({
                'start': start_str,
                'end': end_str
            })
            
        return jsonify({'booked_slots': booked_slots})
        
    except ValueError:
        return jsonify({'booked_slots': []})
    except Exception as e:
        current_app.logger.error(f"Availability check error: {e}")
        return jsonify({'booked_slots': []})
    

# ============================================
# Admin Routes
# ============================================

@app.route('/admin')
@admin_required
def admin_dashboard():
    """
    Main Admin Dashboard.
    Displays KPIs, Recent Activity, and FullCalendar data.
    """
    # Auto-convert confirmed bookings to projects
    current_user = db.session.get(User, session['user_id'])
    if current_user.role != 'super_admin':
        # If employee, redirect to their allowed page
        return redirect(url_for('manage_projects'))
    
    convert_confirmed_bookings_to_projects()
    
    today = datetime.now().date()
    current_year = today.year
    current_month = today.month
    
    # --- KPI Calculations ---
    
    # Total Revenue (Confirmed + Completed)
    total_revenue = db.session.query(func.sum(Booking.total_price)).filter(
        Booking.status.in_(['confirmed', 'completed'])
    ).scalar() or 0
    
    # Monthly Revenue
    monthly_revenue = db.session.query(func.sum(Booking.total_price)).filter(
        Booking.status.in_(['confirmed', 'completed']),
        extract('month', Booking.booking_date) == current_month,
        extract('year', Booking.booking_date) == current_year
    ).scalar() or 0
    
    # Counts
    pending_requests = Booking.query.filter_by(status='pending').count()
    active_projects_count = Project.query.filter(Project.status.notin_(['completed'])).count()
    new_inquiries = ContactInquiry.query.filter_by(status='new').count()
    
    # --- Recent Lists ---
    pending_bookings = Booking.query.filter_by(status='pending').order_by(Booking.created_at.desc()).limit(6).all()
    recent_payments = Booking.query.filter(Booking.status.in_(['confirmed', 'completed'])).order_by(desc(Booking.created_at)).limit(6).all()
    active_projects = Project.query.filter(Project.status.notin_(['completed'])).order_by(Project.due_date.asc()).limit(5).all()
    
    # --- Calendar Data Preparation ---
    calendar_events = []
    all_bookings = Booking.query.filter(Booking.status.in_(['pending', 'confirmed', 'completed'])).all()
    
    for booking in all_bookings:
        # Determine color based on status
        if booking.status == 'confirmed':
            color = '#D4AF37' # Gold
        elif booking.status == 'completed':
            color = '#10B981' # Green
        else:
            color = '#3B82F6' # Blue
            
        client_name = booking.client.full_name if booking.client else 'Unknown Client'
        service_name = booking.service.name if booking.service else 'Unknown Service'
        
        # Calculate End Time for Calendar object
        start_dt = datetime.combine(booking.booking_date, booking.start_time)
        end_dt = start_dt + timedelta(hours=booking.duration_hours)
        
        calendar_events.append({
            'id': booking.id,
            'title': f"{client_name} - {service_name}",
            'start': start_dt.isoformat(),
            'end': end_dt.isoformat(),
            'backgroundColor': color,
            'borderColor': color,
            'url': url_for('booking_details_view', highlight=booking.id), # Assuming detailed view handles this
            'extendedProps': {
                'client': client_name,
                'status': booking.status,
                'price': booking.total_price
            }
        })
    
    calendar_events_json = jsonify(calendar_events).get_data(as_text=True)
    
    return render_template('admin/base.html',
        total_revenue=total_revenue,
        monthly_revenue=monthly_revenue,
        pending_requests=pending_requests,
        active_projects_count=active_projects_count,
        pending_bookings=pending_bookings,
        recent_payments=recent_payments,
        active_projects=active_projects,
        calendar_events=calendar_events_json,
        new_inquiries=new_inquiries,
        current_date=today
    )





# ============================================
# [ADD] Admin Management for General Services
# ============================================

@app.route('/admin/general-services')
@admin_required
def admin_general_services():
    """List all General Services."""
    services = GeneralService.query.order_by(GeneralService.display_order).all()
    new_inquiries = ContactInquiry.query.filter_by(status='new').count()
    return render_template('admin/general_services_list.html', items=services, new_inquiries=new_inquiries)

@app.route('/admin/general-services/new', methods=['GET', 'POST'])
@admin_required
def admin_general_service_new():
    """Create new General Service."""
    new_inquiries = ContactInquiry.query.filter_by(status='new').count()
    
    # Fetch booking services for the dropdown
    booking_services = Service.query.filter_by(is_active=True).order_by(Service.name).all()
    
    if request.method == 'POST':
        try:
            linked_id = request.form.get('linked_booking_service_id')
            linked_id = int(linked_id) if linked_id and linked_id != '0' else None

            service = GeneralService(
                name=request.form.get('name'),
                name_ar=request.form.get('name_ar'),
                slug=request.form.get('slug') or generate_slug(request.form.get('name')),
                icon=request.form.get('icon', 'star'),
                category=request.form.get('category'),
                description=request.form.get('description'),
                description_ar=request.form.get('description_ar'),
                features=request.form.get('features'),
                features_ar=request.form.get('features_ar'),
                linked_booking_service_id=linked_id,
                display_order=int(request.form.get('display_order', 0)),
                is_active='is_active' in request.form
            )
            db.session.add(service)
            db.session.commit()
            flash('General Service created', 'success')
            return redirect(url_for('admin_general_services'))
        except Exception as e:
            flash(f'Error: {str(e)}', 'error')
            db.session.rollback()
            
    return render_template('admin/general_service_edit.html', item=None, action='Create', new_inquiries=new_inquiries, booking_services=booking_services)

@app.route('/admin/general-services/edit/<int:service_id>', methods=['GET', 'POST'])
@admin_required
def admin_general_service_edit(service_id):
    """Edit General Service."""
    service = GeneralService.query.get_or_404(service_id)
    new_inquiries = ContactInquiry.query.filter_by(status='new').count()
    booking_services = Service.query.filter_by(is_active=True).order_by(Service.name).all()
    
    if request.method == 'POST':
        try:
            linked_id = request.form.get('linked_booking_service_id')
            linked_id = int(linked_id) if linked_id and linked_id != '0' else None

            service.name = request.form.get('name')
            service.name_ar = request.form.get('name_ar')
            service.slug = request.form.get('slug') or generate_slug(service.name)
            service.icon = request.form.get('icon', 'star')
            service.category = request.form.get('category')
            service.description = request.form.get('description')
            service.description_ar = request.form.get('description_ar')
            service.features = request.form.get('features')
            service.features_ar = request.form.get('features_ar')
            service.linked_booking_service_id = linked_id
            service.display_order = int(request.form.get('display_order', 0))
            service.is_active = 'is_active' in request.form
            
            db.session.commit()
            flash('Service updated', 'success')
            return redirect(url_for('admin_general_services'))
        except Exception as e:
            flash(f'Error: {str(e)}', 'error')
            db.session.rollback()
    
    return render_template('admin/general_service_edit.html', item=service, action='Edit', new_inquiries=new_inquiries, booking_services=booking_services)

@app.route('/admin/general-services/delete/<int:service_id>', methods=['POST'])
@admin_required
def admin_general_service_delete(service_id):
    service = GeneralService.query.get_or_404(service_id)
    try:
        db.session.delete(service)
        db.session.commit()
        flash('Service deleted', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    return redirect(url_for('admin_general_services'))


# ============================================
# [INSERT THIS AFTER admin_studio_delete]
# ============================================




@app.route('/admin/studios/<int:studio_id>/block', methods=['POST'])
@admin_required
def admin_studio_block_date(studio_id):
    """
    Blocks a studio for a specific date by creating a full-day 'Internal' booking.
    """
    studio = Studio.query.get_or_404(studio_id)
    block_date_str = request.form.get('block_date')
    reason = request.form.get('reason', 'Maintenance / Unavailable')
    
    if not block_date_str:
        flash('Please select a date to block.', 'error')
        return redirect(url_for('admin_studio_edit', studio_id=studio_id))

    try:
        block_date = datetime.strptime(block_date_str, '%Y-%m-%d').date()
        
        # 1. Check if already blocked or booked
        # We check for any overlap, but since we are blocking the whole day, any booking is a conflict.
        # However, for an admin block, we might want to force it, but let's warn if bookings exist.
        existing_bookings = Booking.query.filter(
            Booking.studio_id == studio.id,
            Booking.booking_date == block_date,
            Booking.status.notin_(['cancelled', 'rejected', 'refunded'])
        ).count()
        
        if existing_bookings > 0:
            flash(f'Warning: There are already {existing_bookings} bookings on {block_date_str}. Please cancel them first before blocking the date.', 'error')
            return redirect(url_for('admin_studio_edit', studio_id=studio_id))

        # 2. Get or Create "System Admin" Client
        # We need a dummy client to attach the booking to
        system_email = 'system@ptahstudios.internal'
        client = Client.query.filter_by(email=system_email).first()
        if not client:
            client = Client(
                first_name='System',
                last_name='Block',
                email=system_email,
                phone='0000000000',
                company='Ptah Internal'
            )
            db.session.add(client)
            db.session.flush()

        # 3. Get a Service placeholder
        # We need a service ID for the foreign key. We'll use the first available active service 
        # or create a dummy one if none exist.
        service = Service.query.first()
        if not service:
            flash('Error: No services defined. Cannot create block.', 'error')
            return redirect(url_for('admin_studio_edit', studio_id=studio_id))

        # 4. Create the Block Booking (00:00 to 23:59)
        booking = Booking(
            booking_reference=f"BLK-{block_date_str.replace('-', '')}-{secrets.token_hex(2).upper()}",
            client_id=client.id,
            service_id=service.id,
            studio_id=studio.id,
            booking_date=block_date,
            start_time=time(0, 0),    # Start of day
            end_time=time(23, 59),    # End of day
            duration_hours=24.0,
            base_price=0.0,
            total_price=0.0,
            status='confirmed',       # Automatically confirmed to block slot
            client_notes=f"INTERNAL BLOCK: {reason}",
            internal_notes="Created via Admin Dashboard"
        )
        
        db.session.add(booking)
        db.session.commit()
        
        flash(f'Studio blocked successfully for {block_date_str}.', 'success')

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Block date error: {e}")
        flash(f'Error blocking date: {str(e)}', 'error')

    return redirect(url_for('admin_studio_edit', studio_id=studio_id))


@app.route('/admin/studios/unblock/<int:booking_id>', methods=['POST'])
@admin_required
def admin_studio_unblock_date(booking_id):
    """Removes a block (deletes the blocking booking)."""
    booking = Booking.query.get_or_404(booking_id)
    studio_id = booking.studio_id
    
    # Security check: Ensure this is actually a system block
    if booking.client.email != 'system@ptahstudios.internal':
        flash('Cannot delete real client bookings from here. Use the Booking Manager.', 'error')
        return redirect(url_for('admin_studio_edit', studio_id=studio_id))
        
    try:
        db.session.delete(booking)
        db.session.commit()
        flash('Date unblocked successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error unblocking date: {str(e)}', 'error')
        
    return redirect(url_for('admin_studio_edit', studio_id=studio_id))


@app.route('/admin/booking_details_view')
@admin_required
def booking_details_view():
    """Detailed table view of all bookings."""
    bookings = Booking.query.order_by(Booking.created_at.desc()).all()
    equipment_list = ServiceAddOn.query.filter_by(is_active=True).all()
    new_inquiries = ContactInquiry.query.filter_by(status='new').count()
    return render_template('admin/bookings_details.html', bookings=bookings, equipment_list=equipment_list, new_inquiries=new_inquiries)

@app.route('/admin/payment_details_view')
@admin_required
def payment_details_view():
    """Financial overview."""
    payments = Booking.query.filter(Booking.status.in_(['confirmed', 'completed', 'pending'])).order_by(Booking.created_at.desc()).all()
    
    total_collected = db.session.query(func.sum(Booking.total_price)).filter(Booking.status.in_(['confirmed', 'completed'])).scalar() or 0
    pending_collection = db.session.query(func.sum(Booking.total_price)).filter(Booking.status == 'pending').scalar() or 0
    completed_count = Booking.query.filter(Booking.status.in_(['confirmed', 'completed'])).count()
    
    new_inquiries = ContactInquiry.query.filter_by(status='new').count()
    
    return render_template('admin/payment_details.html', 
                         payments=payments, 
                         total_collected=total_collected, 
                         pending_collection=pending_collection, 
                         completed_count=completed_count, 
                         new_inquiries=new_inquiries)

@app.route('/admin/bookings')
@admin_required
def admin_bookings():
    """Managed list of bookings with filters."""
    status = request.args.get('status')
    query = Booking.query
    if status: query = query.filter_by(status=status)
    bookings = query.order_by(Booking.booking_date.asc()).all()
    new_inquiries = ContactInquiry.query.filter_by(status='new').count()
    return render_template('admin/bookings.html', bookings=bookings, new_inquiries=new_inquiries)


@app.route('/admin/bookings/<int:booking_id>/delete', methods=['POST'])
@admin_required
def delete_booking(booking_id):
    """Permanently delete a booking from the database."""
    booking = Booking.query.get_or_404(booking_id)
    try:
        # Check if there is a linked project and unlink it to prevent errors
        if booking.project:
            booking.project.booking_id = None
            db.session.add(booking.project)
            
        db.session.delete(booking)
        db.session.commit()
        flash('Booking deleted permanently.', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting booking: {str(e)}")
        flash(f'Error deleting booking: {str(e)}', 'error')
        
    return redirect(url_for('booking_details_view'))


@app.route('/admin/bookings/<int:booking_id>/update', methods=['POST'])
@admin_required
def update_booking(booking_id):
    """Quick status update for bookings with immediate project creation."""
    booking = Booking.query.get_or_404(booking_id)
    new_status = request.form.get('status')
    new_price = request.form.get('total_price')
    if new_price is not None:
        try:
            booking.total_price = float(new_price)
        except ValueError:
            pass
        
    
    if new_status:
        booking.status = new_status
        
        # Immediate check: If confirmed and no project exists, create one now
        if new_status == 'confirmed' and not booking.project:
            try:
                # Generate Reference
                project_ref = Project.generate_reference()
                
                # Determine title safely
                service_name = booking.service.name if booking.service else "Service"
                client_name = booking.client.full_name if booking.client else "Client"
                
                # Create the Project linked to this specific booking
                new_project = Project(
                    project_reference=project_ref,
                    client_id=booking.client_id,
                    booking_id=booking.id, # Link established here
                    title=f"{service_name} - {client_name}",
                    description=booking.client_notes or f"Project auto-created from booking {booking.booking_reference}",
                    status='planning',
                    progress_percentage=0,
                    start_date=booking.booking_date,
                    # Default due date to 30 days from booking
                    due_date=booking.booking_date + timedelta(days=30)
                )
                
                db.session.add(new_project)
                current_app.logger.info(f"Created project {project_ref} for booking {booking.id}")
                flash(f'Booking confirmed and Project {project_ref} created.', 'success')
                
            except Exception as e:
                current_app.logger.error(f"Error creating project for booking {booking.id}: {str(e)}")
                flash(f'Booking status updated, but Project creation failed: {str(e)}', 'warning')
        
        else:
            flash(f'Booking {booking.booking_reference} updated to {new_status}.', 'success')
            
        db.session.commit()
        
    return redirect(request.referrer or url_for('booking_details_view'))

@app.route('/admin/clients')
@admin_required
def admin_clients():
    """Client Management List."""
    search = request.args.get('search', '')
    query = Client.query
    if search:
        search_term = f"%{search}%"
        query = query.filter(or_(
            Client.first_name.ilike(search_term), 
            Client.last_name.ilike(search_term), 
            Client.email.ilike(search_term)
        ))
    clients = query.order_by(Client.created_at.desc()).all()
    new_inquiries = ContactInquiry.query.filter_by(status='new').count()
    return render_template('admin/clients.html', clients=clients, search=search, new_inquiries=new_inquiries)


@app.route('/behind-the-scenes')
def behind_the_scenes():
    """Main gallery page listing all BTS folders."""
    projects = BTSProject.query.filter_by(is_active=True).order_by(BTSProject.event_date.desc()).all()
    return render_template('public/behind_the_scenes.html', projects=projects)

@app.route('/behind-the-scenes/<slug>')
def bts_folder(slug):
    """Inside a specific BTS project folder."""
    project = BTSProject.query.filter_by(slug=slug, is_active=True).first_or_404()
    return render_template('public/bts_folder.html', project=project)

# ============================================
# Analytics & Reports Routes
# ============================================


@app.route('/admin/analytics')
@admin_required
def admin_analytics():
    """Analytics Dashboard with Charts & Reports."""
    
    today = datetime.now()

    # --- 1. KPI Calculations (Top Cards) ---
    monthly_revenue = db.session.query(func.sum(Booking.total_price)).filter(
        Booking.status.in_(['confirmed', 'completed']),
        extract('month', Booking.booking_date) == today.month,
        extract('year', Booking.booking_date) == today.year
    ).scalar() or 0
    
    # Revenue Growth Logic
    last_month_date = today - timedelta(days=30)
    last_month_revenue = db.session.query(func.sum(Booking.total_price)).filter(
        Booking.status.in_(['confirmed', 'completed']),
        extract('month', Booking.booking_date) == last_month_date.month,
        extract('year', Booking.booking_date) == last_month_date.year
    ).scalar() or 0
    
    revenue_growth = 0
    if last_month_revenue > 0:
        revenue_growth = ((monthly_revenue - last_month_revenue) / last_month_revenue) * 100

    # Basic Counts
    total_bookings_count = Booking.query.count()
    active_projects_count = Project.query.filter(Project.status.notin_(['completed', 'cancelled'])).count()
    
    # Conversion Rate
    converted_leads = Lead.query.filter_by(stage=Lead.STAGE_CONVERTED).count()
    closed_leads = Lead.query.filter(Lead.stage.in_([Lead.STAGE_CONVERTED, Lead.STAGE_LOST])).count()
    conversion_rate = round((converted_leads / closed_leads * 100), 1) if closed_leads > 0 else 0.0

    # --- 2. Chart Data Aggregation ---
    
    # A. Revenue Trend
    revenue_data = db.session.query(
        func.strftime('%Y-%m', Booking.booking_date).label('month'),
        func.sum(Booking.total_price)
    ).filter(
        Booking.status.in_(['confirmed', 'completed'])
    ).group_by('month').order_by('month').limit(12).all()
    
    rev_labels = [r[0] for r in revenue_data]
    rev_values = [r[1] for r in revenue_data]

    # B. Service Distribution
    service_dist = db.session.query(
        Service.name,
        func.count(Booking.id)
    ).join(Booking).filter(
        Booking.status.in_(['confirmed', 'completed'])
    ).group_by(Service.name).all()
    
    serv_labels = [s[0] for s in service_dist]
    serv_values = [s[1] for s in service_dist]

    # C. Lead Funnel
    lead_stages = db.session.query(Lead.stage, func.count(Lead.id)).group_by(Lead.stage).all()
    stage_map = {s[0]: s[1] for s in lead_stages}
    funnel_order = ['new', 'contacted', 'qualified', 'proposal', 'converted'] # Use lowercase to match DB
    funnel_values = [stage_map.get(s, 0) for s in funnel_order]
    funnel_labels = ['New', 'Contacted', 'Qualified', 'Proposal', 'Converted']

    # D. Source
    source_conv = db.session.query(Lead.source, func.count(Lead.id))\
        .filter(Lead.stage == Lead.STAGE_CONVERTED).group_by(Lead.source).all()
    
    if not source_conv:
        source_labels = ["No Data"]
        source_values = [1] 
    else:
        source_labels = [s[0] for s in source_conv]
        source_values = [s[1] for s in source_conv]

    # E. Project Trends (Double Bar Chart Logic)
    # We generate a list of the last 6 months to ensure clean data
    proj_labels = []
    proj_started_values = []
    proj_delivered_values = []
    
    curr_date = today - relativedelta(months=5) # Last 6 months
    while curr_date <= today:
        month_str = curr_date.strftime('%Y-%m')
        proj_labels.append(curr_date.strftime('%b %Y'))
        
        # Started: Created in this month
        started = Project.query.filter(func.strftime('%Y-%m', Project.created_at) == month_str).count()
        proj_started_values.append(started)
        
        # Delivered: Completed in this month (using updated_at as proxy if completed_at doesn't exist)
        delivered = Project.query.filter(
            Project.status == 'completed',
            func.strftime('%Y-%m', Project.updated_at) == month_str
        ).count()
        proj_delivered_values.append(delivered)
        
        curr_date += relativedelta(months=1)

    # --- 3. Bottom Summary Metrics ---
    total_revenue_lifetime = db.session.query(func.sum(Booking.total_price)).filter(
        Booking.status.in_(['confirmed', 'completed'])
    ).scalar() or 0
    
    avg_booking_val = round(total_revenue_lifetime / total_bookings_count) if total_bookings_count > 0 else 0
    
    total_leads_count = Lead.query.count()
    qualified_leads_count = Lead.query.filter_by(stage='qualified').count()
    
    total_projects = Project.query.count()
    delivered_projects_total = Project.query.filter_by(status='completed').count()
    project_completion_rate = round((delivered_projects_total / total_projects * 100)) if total_projects > 0 else 0

    services = Service.query.filter_by(is_active=True).all()

    return render_template('admin/analytics.html',
                         # Charts
                         rev_labels=json.dumps(rev_labels), rev_values=json.dumps(rev_values),
                         serv_labels=json.dumps(serv_labels), serv_values=json.dumps(serv_values),
                         funnel_labels=json.dumps(funnel_labels), funnel_values=json.dumps(funnel_values),
                         source_labels=json.dumps(source_labels), source_values=json.dumps(source_values),
                         proj_labels=json.dumps(proj_labels), 
                         proj_started_values=json.dumps(proj_started_values),
                         proj_delivered_values=json.dumps(proj_delivered_values),
                         # KPI Cards
                         monthly_revenue=monthly_revenue, revenue_growth=revenue_growth,
                         total_bookings_count=total_bookings_count, active_projects_count=active_projects_count,
                         conversion_rate=conversion_rate,
                         # Bottom Summary
                         total_revenue_lifetime=total_revenue_lifetime,
                         avg_booking_val=avg_booking_val,
                         total_leads_count=total_leads_count,
                         qualified_leads_count=qualified_leads_count,
                         delivered_projects_total=delivered_projects_total,
                         project_completion_rate=project_completion_rate,
                         # Extras
                         services=services)
@app.route('/admin/reports/export')
@admin_required
def export_report():
    """Handle CSV Export Logic with Month/Quarter/Year filtering."""
    # 1. Get Filters
    report_type = request.args.get('type', 'financial') # financial, leads, projects
    scope = request.args.get('scope', 'year')           # month, quarter, year
    year = int(request.args.get('year', datetime.now().year))
    
    # 2. Calculate Date Range
    start_date = None
    end_date = None

    if scope == 'month':
        month = int(request.args.get('month', 1))
        _, last_day = calendar.monthrange(year, month)
        start_date = date(year, month, 1)
        end_date = date(year, month, last_day)
        period_label = f"{calendar.month_name[month]}_{year}"

    elif scope == 'quarter':
        q = int(request.args.get('quarter', 1))
        start_month = (q - 1) * 3 + 1
        end_month = start_month + 2
        _, last_day = calendar.monthrange(year, end_month)
        
        start_date = date(year, start_month, 1)
        end_date = date(year, end_month, last_day)
        period_label = f"Q{q}_{year}"

    else: # scope == 'year'
        start_date = date(year, 1, 1)
        end_date = date(year, 12, 31)
        period_label = f"{year}"

    # 3. Prepare CSV Response
    si = io.StringIO()
    cw = csv.writer(si)
    filename = f"ptah_{report_type}_{period_label}.csv"
    
    # 4. Query Logic based on Date Range
    # We filter where the date is BETWEEN start_date and end_date
    
    if report_type == 'financial':
        cw.writerow(['Date', 'Reference', 'Client', 'Service', 'Total Price', 'Status'])
        
        query = Booking.query.filter(
            Booking.booking_date >= start_date,
            Booking.booking_date <= end_date
        )
        # Optional: Filter by specific service if needed (not in current UI but good to have)
        if request.args.get('service_id'):
            query = query.filter_by(service_id=request.args.get('service_id'))
            
        records = query.order_by(Booking.booking_date).all()
        for r in records:
            cw.writerow([r.booking_date, r.booking_reference, r.client.full_name, r.service.name, r.total_price, r.status])
            
    elif report_type == 'leads':
        cw.writerow(['Date', 'Name', 'Company', 'Source', 'Stage', 'Score'])
        
        # Use created_at for leads (cast to date for comparison)
        records = Lead.query.filter(
            func.date(Lead.created_at) >= start_date,
            func.date(Lead.created_at) <= end_date
        ).order_by(Lead.created_at).all()
        
        for r in records:
            cw.writerow([r.created_at.date(), r.name, r.company, r.source, r.stage, r.lead_score])
            
    elif report_type == 'projects':
        cw.writerow(['Created', 'Reference', 'Title', 'Client', 'Status', 'Progress'])
        
        records = Project.query.filter(
            func.date(Project.created_at) >= start_date,
            func.date(Project.created_at) <= end_date
        ).order_by(Project.created_at).all()
        
        for r in records:
            cw.writerow([r.created_at.date(), r.project_reference, r.title, r.client.full_name, r.status, r.progress_percentage])

    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename={filename}"
    output.headers["Content-type"] = "text/csv"
    return output

# ============================================
# 4. NEW ADMIN MANAGEMENT ROUTES
# ============================================
@app.route('/admin/equipment/maintenance-complete/<int:equipment_id>', methods=['POST'])
@admin_required
def admin_equipment_maintenance_complete(equipment_id):
    """Resets the maintenance cycle for a specific item."""
    item = ServiceAddOn.query.get_or_404(equipment_id)
    
    # Set the last maintenance date to TODAY
    item.last_maintenance_date = datetime.now().date()
    
    db.session.commit()
    flash(f'Maintenance recorded for {item.name}. New cycle started.', 'success')
    
    # Redirect back to the page user came from
    return redirect(request.referrer or url_for('admin_equipment'))


@app.route('/admin/management')
@admin_required
def admin_management_dashboard():
    """Super Admin Only: Manage Users and Roles."""
    current_user = db.session.get(User, session['user_id'])
    if current_user.role != 'super_admin':
        flash("Access Denied: Super Admin only.", "error")
        return redirect(url_for('admin_dashboard'))
    
    # UPDATED: Only fetch users marked as admins/staff (is_admin=True)
    users = User.query.filter_by(is_admin=True).all()
    
    projects = Project.query.filter(Project.status != 'completed').all()
    new_inquiries = ContactInquiry.query.filter_by(status='new').count()
    
    return render_template('admin/admin_management.html', 
                           users=users, 
                           projects=projects,
                           new_inquiries=new_inquiries)


@app.route('/admin/users/unassign-project', methods=['POST'])
@admin_required
def admin_unassign_project():
    """Remove a user from a project team."""
    current_user = db.session.get(User, session['user_id'])
    if current_user.role != 'super_admin':
        abort(403)
        
    user_id = request.form.get('user_id')
    project_id = request.form.get('project_id')
    
    membership = ProjectMembership.query.filter_by(
        user_id=user_id, 
        project_id=project_id
    ).first()
    
    if membership:
        user_name = membership.user.name
        project_title = membership.project.title
        
        db.session.delete(membership)
        db.session.commit()
        
        log_project_activity(project_id, f"Removed {user_name} from team")
        flash(f'Removed {user_name} from {project_title}', 'success')
    else:
        flash('Assignment not found', 'warning')
            
    return redirect(url_for('admin_management_dashboard'))

@app.route('/admin/users/add', methods=['POST'])
@admin_required
def admin_add_user():
    # Check permissions
    current_user = db.session.get(User, session['user_id'])
    if current_user.role != 'super_admin':
        abort(403)
        
    name = request.form.get('name')
    email = request.form.get('email')
    password = request.form.get('password')
    role = request.form.get('role', 'employee')
    
    if User.query.filter_by(email=email).first():
        flash('Email already exists', 'error')
        return redirect(url_for('admin_management_dashboard'))
        
    new_user = User(name=name, email=email, role=role, is_admin=True) # All dashboard users are is_admin=True
    new_user.set_password(password)
    db.session.add(new_user)
    db.session.commit()
    
    flash('User added successfully', 'success')
    return redirect(url_for('admin_management_dashboard'))

@app.route('/admin/users/assign-project', methods=['POST'])
@admin_required
def admin_assign_project():
    """Assign a project to a user with a specific role."""
    current_user = db.session.get(User, session['user_id'])
    if current_user.role != 'super_admin':
        abort(403)
        
    user_id = request.form.get('user_id')
    project_id = request.form.get('project_id')
    project_role = request.form.get('project_role', 'Reviewer')  # NEW: Get role from form
    
    user = db.session.get(User, user_id)
    project = db.session.get(Project, project_id)
    
    if not user or not project:
        flash('Invalid user or project', 'error')
        return redirect(url_for('admin_management_dashboard'))
    
    # Check if membership already exists
    existing = ProjectMembership.query.filter_by(
        user_id=user.id, 
        project_id=project.id
    ).first()
    
    if existing:
        # Update existing role
        old_role = existing.role
        existing.role = project_role
        db.session.commit()
        log_project_activity(project.id, f"Updated {user.name}'s role from {old_role} to {project_role}")
        flash(f"Updated {user.name}'s role to {project_role} for {project.title}", 'success')
    else:
        # Create new membership
        membership = ProjectMembership(
            user_id=user.id,
            project_id=project.id,
            role=project_role
        )
        db.session.add(membership)
        db.session.commit()
        log_project_activity(project.id, f"Assigned {user.name} as {project_role}")
        flash(f'Assigned {project.title} to {user.name} as {project_role}', 'success')
            
    return redirect(url_for('admin_management_dashboard'))

@app.route('/admin/users/delete/<int:user_id>', methods=['POST'])
@admin_required
def admin_delete_user(user_id):
    if session['user_id'] == user_id:
        flash("Cannot delete yourself.", "error")
        return redirect(url_for('admin_management_dashboard'))
        
    user = User.query.get(user_id)
    if user:
        db.session.delete(user)
        db.session.commit()
        flash('User removed', 'success')
    return redirect(url_for('admin_management_dashboard'))


@app.route('/admin/bts')
@admin_required
def admin_bts_list():
    """List all BTS projects for management."""
    projects = BTSProject.query.order_by(BTSProject.created_at.desc()).all()
    new_inquiries = ContactInquiry.query.filter_by(status='new').count()
    return render_template('admin/bts_manager.html', projects=projects, new_inquiries=new_inquiries)

@app.route('/admin/bts/media/delete/<int:media_id>', methods=['POST'])
@admin_required
def admin_bts_media_delete(media_id):
    """Delete a specific media file from a BTS project."""
    media = BTSMedia.query.get_or_404(media_id)
    project_id = media.project_id
    
    # 1. Remove file from filesystem
    try:
        # media.file_url is stored as 'uploads/img/bts/filename.ext'
        # We need to build the full system path to delete it
        file_path = os.path.join(app.root_path, 'static', media.file_url)
        
        if os.path.exists(file_path):
            os.remove(file_path)
            current_app.logger.info(f"Deleted file: {file_path}")
    except Exception as e:
        # Log the error but continue to delete the DB record so the UI isn't broken
        current_app.logger.error(f"Error deleting file from disk: {e}")
        
    # 2. Delete DB record
    try:
        db.session.delete(media)
        db.session.commit()
        flash('Media file deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting database record: {str(e)}', 'error')
    
    return redirect(url_for('admin_bts_list'))


@app.route('/admin/bts/new', methods=['POST'])
@admin_required
def admin_bts_create():
    """Create a new BTS Project Folder."""
    try:
        thumbnail_url = upload_image(request.files.get('thumbnail'), 'bts')
        
        project = BTSProject(
            title=request.form.get('title'),
            slug=generate_slug(request.form.get('title')),
            title_ar=request.form.get('title_ar'),
            description=request.form.get('description'),
            description_ar=request.form.get('description_ar'),
            thumbnail_url=thumbnail_url,
            event_date=datetime.strptime(request.form.get('date'), '%Y-%m-%d').date() if request.form.get('date') else datetime.utcnow()
        )
        db.session.add(project)
        db.session.commit()
        flash('BTS Project Folder created!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    return redirect(url_for('admin_bts_list'))

@app.route('/admin/bts/<int:project_id>/upload', methods=['POST'])
@admin_required
def admin_bts_upload(project_id):
    """Upload media to a specific project."""
    project = BTSProject.query.get_or_404(project_id)
    files = request.files.getlist('media_files')
    
    count = 0
    for file in files:
        if file and file.filename:
            # Determine type
            ext = file.filename.rsplit('.', 1)[1].lower()
            ftype = 'video' if ext in ['mp4', 'mov', 'webm'] else 'image'
            
            url = upload_image(file, 'bts') # Reusing your existing upload function
            if url:
                media = BTSMedia(project_id=project.id, file_url=url, file_type=ftype)
                db.session.add(media)
                count += 1
    
    db.session.commit()
    flash(f'{count} files uploaded successfully.', 'success')
    return redirect(url_for('admin_bts_list'))

@app.route('/admin/bts/delete/<int:project_id>', methods=['POST'])
@admin_required
def admin_bts_delete(project_id):
    project = BTSProject.query.get_or_404(project_id)
    db.session.delete(project)
    db.session.commit()
    flash('Project deleted.', 'success')
    return redirect(url_for('admin_bts_list'))


@app.template_filter('local_time')
def local_time_filter(dt):
    """Converts UTC datetime to Egypt Time (UTC+2) for display."""
    if dt is None: 
        return ""
    # Add 2 hours to match Egypt Local Time
    local_dt = dt + timedelta(hours=2) 
    # CHANGED: Now includes Month Day, Time (e.g., Jan 15, 03:27 PM)
    return local_dt.strftime('%b %d, %I:%M %p')

@app.route('/api/activity/mark-seen', methods=['POST'])
@login_required
def mark_activity_seen():
    try:
        user = db.session.get(User, session['user_id'])
        user.last_activity_check = datetime.utcnow()
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    
@app.route('/admin/clients/<int:client_id>')
@admin_required
def client_detail(client_id):
    """Single Client Profile View."""
    client = Client.query.get_or_404(client_id)
    bookings = Booking.query.filter_by(client_id=client_id).order_by(Booking.created_at.desc()).all()
    projects = Project.query.filter_by(client_id=client_id).order_by(Project.created_at.desc()).all()
    new_inquiries = ContactInquiry.query.filter_by(status='new').count()
    return render_template('admin/client_detail.html', client=client, bookings=bookings, projects=projects, new_inquiries=new_inquiries)

@app.route('/admin/projects')
@admin_required
def admin_projects():
    """Project Management Board - Shows all projects."""
    status = request.args.get('status')
    query = Project.query
    if status: query = query.filter_by(status=status)
    projects = query.order_by(Project.due_date.asc()).all()
    new_inquiries = ContactInquiry.query.filter_by(status='new').count()
    return render_template('admin/projects.html', projects=projects, new_inquiries=new_inquiries)



@app.route('/api/projects/<int:project_id>/tasks/<int:task_id>/delete', methods=['POST'])
@admin_required
def delete_project_task_api(project_id, task_id):
    """Delete a task - Supervisors Only."""
    try:
        # Check permission
        has_permission, user_role = check_project_permission(project_id, 'delete_task')
        
        if not has_permission:
            return jsonify({
                'success': False, 
                'error': 'Access denied. Only Supervisors can delete tasks.'
            }), 403
        
        task = ProjectTask.query.get_or_404(task_id)
        task_title = task.title
        
        db.session.delete(task)
        db.session.commit()
        
        # Log the activity
        log_project_activity(project_id, f"Deleted task: '{task_title}'", session['user_id'])
        
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

        
@app.route('/api/projects/<int:project_id>/tasks/<int:task_id>/toggle', methods=['POST'])
@admin_required
def toggle_project_task_api(project_id, task_id):
    """Toggle task status - Reviewers cannot do this."""
    try:
        # ✅ FIX: Check for 'toggle_task' permission (not 'manage_tasks')
        has_permission, user_role = check_project_permission(project_id, 'toggle_task')
        
        if not has_permission:
            return jsonify({
                'success': False, 
                'error': 'Access denied. You do not have permission to toggle tasks.'
            }), 403
        
        task = ProjectTask.query.get(task_id)
        if not task:
            return jsonify({'success': False, 'error': 'Task not found'}), 404
            
        data = request.get_json()
        new_status = data.get('status')
        
        if new_status in ['completed', 'pending']:
            if task.status != new_status:
                log_project_activity(project_id, f"Task '{task.title}' marked as {new_status} by {user_role}")

            task.status = new_status
            if new_status == 'completed':
                task.completed_at = datetime.utcnow()
            else:
                task.completed_at = None
                
            db.session.commit()
            return jsonify({'success': True, 'status': task.status})
        
        return jsonify({'success': False, 'error': 'Invalid status'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
# Add these API endpoints to app.py

@app.route('/api/projects/<int:project_id>/details')
@admin_required
def api_project_details(project_id):
    """Fetch complete project details for the modal"""
    project = Project.query.get_or_404(project_id)
    
    # 1. Get Client Info
    if project.client:
        client_name = project.client.full_name
        client_company = project.client.company
        client_email = project.client.email
        client_phone = project.client.phone
    else:
        client_name = "Unknown"
        client_company = "Individual Client"
        client_email = "N/A"
        client_phone = "N/A"
    
    # 2. Get Booking Info (Financials & Dates)
    booking = project.booking
    booking_reference = booking.booking_reference if booking else "N/A"
    booking_date = booking.booking_date if booking else None # Fixed: was session_date
    session_time = booking.start_time.strftime('%I:%M %p') if booking and booking.start_time else "N/A"
    duration_hours = booking.duration_hours if booking else 0
    client_notes = booking.client_notes if booking else ""
    
    # Financials (Pull from Booking)
    base_price = booking.base_price if booking else 0.0
    studio_price = booking.studio_price if booking else 0.0
    equipment_price = booking.equipment_price if booking else 0.0
    total_price = booking.total_price if booking else 0.0

    # 3. Determine Service Name
    service_name = "General Project"
    if booking and booking.service:
        service_name = booking.service.name

    return jsonify({
        'success': True,
        'project': {
            'id': project.id,
            'title': project.title,
            'project_reference': project.project_reference,
            'status': project.status,
            'priority': project.priority,
            'progress_percentage': project.progress_percentage,
            'due_date': project.due_date.isoformat() if project.due_date else None,
            'service_name': service_name,
            'studio_name': booking.studio.name if booking and booking.studio else "Not specified",
            'start_date': project.start_date.isoformat() if project.start_date else None,
            'booking_date': booking_date.isoformat() if booking_date else None,
            'session_time': session_time,
            'duration_hours': duration_hours,
            'booking_reference': booking_reference,
            'created_at': project.created_at.isoformat() if project.created_at else None,
            'updated_at': project.updated_at.isoformat() if project.updated_at else None,
            'description': project.description or "",
            
            # Client Data
            'client_name': client_name,
            'client_company': client_company,
            'client_email': client_email,
            'client_phone': client_phone,
            'client_notes': client_notes,
            
            # Financial Data
            'base_price': float(base_price),
            'studio_price': float(studio_price),
            'equipment_price': float(equipment_price),
            'total_price': float(total_price),
        }
    })

@app.route('/api/projects/<int:project_id>/tasks')
def api_project_tasks(project_id):
    """Fetch all tasks for a project"""
    # FIX: Use ProjectTask
    tasks = ProjectTask.query.filter_by(project_id=project_id).order_by(ProjectTask.created_at.desc()).all()
    return jsonify({
        'success': True,
        'tasks': [
            {
                'id': task.id,
                'title': task.title,
                'description': task.description,
                'status': task.status,
                'priority': task.priority,
                'assigned_to': task.assigned_to,
                'due_date': task.due_date.isoformat() if task.due_date else None,
                'created_at': task.created_at.isoformat() if task.created_at else None,
            } for task in tasks
        ]
    })


@app.route('/api/projects/<int:project_id>/tasks', methods=['POST'])
def api_create_task(project_id):
    """Create a new task for a project"""
    data = request.form
    has_permission, user_role = check_project_permission(project_id, 'create_task')
    
    # FIX: Use ProjectTask
    new_task = ProjectTask(
        project_id=project_id,
        title=data.get('title'),
        description=data.get('description'),
        assigned_to=data.get('assigned_to'),
        priority=data.get('priority', 'medium'),
        # Handle date parsing safely
        due_date=datetime.strptime(data.get('due_date'), '%Y-%m-%d').date() if data.get('due_date') else None,
        status='pending',
        created_at=datetime.utcnow()
    )
    
    db.session.add(new_task)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'task': {
            'id': new_task.id,
            'title': new_task.title,
            'status': new_task.status,
            'priority': new_task.priority,
        }
    })


@app.route('/api/projects/<int:project_id>/tasks/<int:task_id>/toggle', methods=['POST'])
def api_toggle_task(project_id, task_id):
    """Toggle task completion status"""
    has_permission, user_role = check_project_permission(project_id, 'toggle_task')
    data = request.get_json()
    new_status = data.get('status', 'pending')
    
    # FIX: Use ProjectTask
    task = ProjectTask.query.filter_by(id=task_id, project_id=project_id).first_or_404()
    task.status = new_status
    
    if new_status == 'completed':
        task.completed_at = datetime.utcnow()
    
    db.session.commit()
    
    return jsonify({'success': True})


@app.route('/api/projects/<int:project_id>/notes', methods=['POST'])
def api_save_notes(project_id):
    """Save project notes"""
    data = request.get_json()
    notes = data.get('notes', '')
    
    project = Project.query.get_or_404(project_id)
    project.description = notes
    project.updated_at = datetime.utcnow()
    
    db.session.commit()
    
    return jsonify({'success': True})
@app.route('/admin/manage-projects')
@admin_required
def manage_projects():
    """Project Management Dashboard with role-based filtering."""
    convert_confirmed_bookings_to_projects()
    
    current_user = db.session.get(User, session['user_id'])
    search = request.args.get('search')
    
    status_order = [
        'planning', 'pre_production', 'production', 'post_production', 
        'review', 'delivered', 'completed', 'rejected'
    ]
    
    # Base Query
    query = Project.query
    
    # Role Check: Employees only see their assigned projects
    if current_user.role != 'super_admin':
        query = query.join(ProjectMembership).filter(ProjectMembership.user_id == current_user.id)
    
    # Search Filter
    if search:
        search_term = f"%{search}%"
        query = query.filter(or_(
            Project.title.ilike(search_term),
            Project.client.has(Client.full_name.ilike(search_term)),
            Project.project_reference.ilike(search_term)
        ))

    all_projects = query.order_by(Project.created_at.desc()).all()
    
    # Group Projects by Status and ADD ROLE INFO
    grouped_projects = {status: [] for status in status_order}
    grouped_projects['other'] = []
    
    for project in all_projects:
        # Add service name
        if project.booking and project.booking.service:
            project.service_name = project.booking.service.name
        else:
            project.service_name = 'General Project'
        
        # ADD USER'S ROLE IN THIS PROJECT
        if current_user.role != 'super_admin':
            membership = ProjectMembership.query.filter_by(
                user_id=current_user.id,
                project_id=project.id
            ).first()
            project.user_role = membership.role if membership else 'Viewer'
        else:
            project.user_role = 'super_admin'
            
        # Group by status
        p_status = project.status.lower() if project.status else 'other'
        if p_status in grouped_projects:
            grouped_projects[p_status].append(project)
        else:
            grouped_projects['other'].append(project)

    new_inquiries = ContactInquiry.query.filter_by(status='new').count()
    
    return render_template('admin/manage-projects.html', 
                         grouped_projects=grouped_projects,
                         new_inquiries=new_inquiries,
                         current_user_role=current_user.role)


def convert_confirmed_bookings_to_projects():
    """
    Automatically convert confirmed bookings to projects.
    This function checks for confirmed bookings without an associated project
    and creates a project for each one.
    """
    try:
        # FIX: Use outerjoin(Project) to find bookings where Project.id IS NULL
        confirmed_bookings_without_project = Booking.query.outerjoin(Project).filter(
            Booking.status.in_(['confirmed', 'in_progress']),
            Project.id == None
        ).all()
        
        for booking in confirmed_bookings_without_project:
            # Create new project from booking
            project_ref = Project.generate_reference()
            project = Project(
                project_reference=project_ref,
                client_id=booking.client_id,
                booking_id=booking.id, # Link is established here
                title=f"{booking.service.name} - {booking.client.full_name}",
                description=booking.client_notes or f"Project for {booking.service.name}",
                status='planning',
                progress_percentage=0,
                start_date=booking.booking_date,
                due_date=booking.booking_date + timedelta(days=30)
            )
            
            db.session.add(project)
            # REMOVED: booking.project_id = project.id (This column does not exist)
            
            current_app.logger.info(f"Auto-created project {project.project_reference} from booking {booking.booking_reference}")
        
        db.session.commit()
        
    except Exception as e:
        current_app.logger.error(f"Error converting bookings to projects: {str(e)}")
        db.session.rollback()
@app.route('/admin/projects/update', methods=['POST'])
@admin_required
def update_project():
    """Update project details with consolidated logging."""
    project_id = request.form.get('project_id')
    project = Project.query.get_or_404(project_id)
    
    # Check permissions
    has_permission, user_role = check_project_permission(project_id, 'edit_project')
    
    if not has_permission:
        flash('Access denied. You do not have permission to edit this project.', 'error')
        return redirect(url_for('manage_projects'))
    
    # --- Track Changes for Single Log Entry ---
    changes = []
    
    # 1. Status
    old_status = project.status
    new_status = request.form.get('status', project.status)
    if old_status != new_status:
        project.status = new_status
        changes.append(f"status to {new_status}")

    # 2. Priority
    new_priority = request.form.get('priority', project.priority)
    if project.priority != new_priority:
        project.priority = new_priority
        changes.append(f"priority to {new_priority}")
    
    # 3. Progress
    try:
        new_progress = int(request.form.get('progress', project.progress_percentage))
        if project.progress_percentage != new_progress:
            project.progress_percentage = new_progress
            # Optional: Uncomment below if you want to log progress slider changes
            # changes.append(f"progress to {new_progress}%")
    except ValueError:
        pass
    
    # 4. Deadline
    deadline = request.form.get('deadline')
    if deadline:
        try:
            new_date = datetime.strptime(deadline, '%Y-%m-%d').date()
            if project.due_date != new_date:
                project.due_date = new_date
                changes.append(f"deadline to {deadline}")
        except ValueError:
            pass
    
    # 5. Notes
    if 'notes' in request.form:
        new_notes = request.form.get('notes', '')
        if project.description != new_notes:
            project.description = new_notes
            if not changes: changes.append("notes updated") # Log only if nothing else changed
    
    project.updated_at = datetime.utcnow()
    db.session.commit()
    
    # --- Create ONE Log Entry ---
    if changes:
        log_message = f"Updated {', '.join(changes)}"
    else:
        log_message = "Project details updated"
        
    log_project_activity(project.id, log_message)
    
    flash('Project updated successfully', 'success')
    return redirect(url_for('manage_projects'))


@app.route('/admin/projects/delete/<int:project_id>', methods=['POST'])
@admin_required
def delete_project(project_id):
    """Permanently delete a project and its history."""
    project = db.session.get(Project, project_id)
    
    if not project:
        flash('Project not found.', 'error')
        return redirect(url_for('manage_projects'))
    
    try:
        # 1. Manually delete related activity logs first (safest approach)
        ProjectActivity.query.filter_by(project_id=project.id).delete()
        
        # NOTE: We removed 'project.team_members = []' because it conflicts 
        # with the new Role system. The 'cascade' rule in your Project model 
        # will automatically remove the members.

        # 2. Delete the project
        db.session.delete(project)
        db.session.commit()
        
        flash('Project deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        # Print error to terminal so you can see it if it happens again
        print(f"Error deleting project: {e}")
        current_app.logger.error(f"Error deleting project: {e}")
        flash('Error deleting project. Please try again.', 'error')

    return redirect(url_for('manage_projects'))


@app.route('/admin/projects/<int:project_id>', methods=['GET', 'POST'])
@admin_required
def project_detail(project_id):
    """Detailed Project View with Task Management."""
    project = Project.query.get_or_404(project_id)
    new_inquiries = ContactInquiry.query.filter_by(status='new').count()
    
    if request.method == 'POST':
        project.status = request.form.get('status', project.status)
        try:
            project.progress_percentage = int(request.form.get('progress', project.progress_percentage))
        except ValueError:
            pass
        project.title = request.form.get('title', project.title)
        db.session.commit()
        flash('Project updated successfully', 'success')
        return redirect(url_for('project_detail', project_id=project_id))
    
    return render_template('admin/project_detail.html', project=project, new_inquiries=new_inquiries)

@app.route('/admin/projects/<int:project_id>/task', methods=['POST'])
@admin_required
def add_project_task(project_id):
    """Add a sub-task to a project."""
    project = Project.query.get_or_404(project_id)
    
    due_date = None
    if request.form.get('due_date'):
        try:
            due_date = datetime.strptime(request.form.get('due_date'), '%Y-%m-%d').date()
        except ValueError:
            pass
            
    task = ProjectTask(
        project_id=project.id,
        title=request.form.get('title'),
        priority=request.form.get('priority', 'medium'),
        due_date=due_date
    )
    db.session.add(task)
    db.session.commit()
    flash('Task added', 'success')
    return redirect(url_for('project_detail', project_id=project_id))

@app.route('/admin/projects/<int:project_id>/task/<int:task_id>/complete')
@admin_required
def complete_task(project_id, task_id):
    """Mark a task as complete."""
    task = ProjectTask.query.get_or_404(task_id)
    task.status = 'completed'
    task.completed_at = datetime.utcnow()
    db.session.commit()
    return redirect(url_for('project_detail', project_id=project_id))


# GET Tasks for a project (JSON)
@app.route('/api/projects/<int:project_id>/tasks', methods=['GET'])
@admin_required
def get_project_tasks(project_id):
    project = db.session.get(Project, project_id) # Updated SQLAlchemy syntax
    if not project:
        return jsonify({'tasks': []})
    
    tasks_data = []
    for t in project.tasks:
        tasks_data.append({
            'id': t.id,
            'title': t.title,
            'description': t.description,
            'assigned_to': t.assigned_to,
            'due_date': t.due_date.strftime('%Y-%m-%d') if t.due_date else None,
            'status': t.status
        })
    
    return jsonify({'tasks': tasks_data})

# POST New Task for a project (JSON)
@app.route('/api/projects/<int:project_id>/tasks', methods=['POST'])
@admin_required
def create_project_task_api(project_id):
    project = db.session.get(Project, project_id)
    if not project:
        return jsonify({'success': False, 'error': 'Project not found'}), 404
        
    try:
        due_date = None
        if request.form.get('due_date'):
            due_date = datetime.strptime(request.form.get('due_date'), '%Y-%m-%d').date()

        task = ProjectTask(
            project_id=project.id,
            title=request.form.get('title'),
            description=request.form.get('description'), # This captures the new field
            assigned_to=request.form.get('assigned_to'),
            due_date=due_date,
            status='pending'
        )
        db.session.add(task)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    


# ============================================
# Package Management Routes
# ============================================

@app.route('/admin/packages')
@admin_required
def admin_packages():
    """List all packages."""
    packages = Package.query.order_by(Package.display_order).all()
    new_inquiries = ContactInquiry.query.filter_by(status='new').count()
    return render_template('admin/package_list.html', items=packages, new_inquiries=new_inquiries)

@app.route('/admin/packages/new', methods=['GET', 'POST'])
@admin_required
def admin_package_new():
    """Create new package."""
    new_inquiries = ContactInquiry.query.filter_by(status='new').count()
    if request.method == 'POST':
        try:
            package = Package(
                name=request.form.get('name'),
                description=request.form.get('description'),
                description_ar=request.form.get('description_ar'),
                name_ar=request.form.get('name_ar'), 
                original_price=float(request.form.get('original_price', 0)),
                duration_hours=float(request.form.get('duration_hours', 0)),
                package_price=float(request.form.get('package_price', 0)),
                icon=request.form.get('icon', 'gift'),
                features=request.form.get('features'),
                features_ar=request.form.get('features_ar'),
                display_order=int(request.form.get('display_order', 0)),
                is_active='is_active' in request.form
            )
            db.session.add(package)
            db.session.commit()
            flash('Package created successfully', 'success')
            return redirect(url_for('admin_packages'))
        except Exception as e:
            flash(f'Error: {str(e)}', 'error')
            db.session.rollback()
    return render_template('admin/package_edit.html', item=None, action='Create', new_inquiries=new_inquiries)

@app.route('/admin/packages/edit/<int:package_id>', methods=['GET', 'POST'])
@admin_required
def admin_package_edit(package_id):
    """Edit package."""
    package = Package.query.get_or_404(package_id)
    new_inquiries = ContactInquiry.query.filter_by(status='new').count()
    
    if request.method == 'POST':
        try:
            package.name = request.form.get('name')
            package.name_ar = request.form.get('name_ar')
            package.description = request.form.get('description')
            package.description_ar = request.form.get('description_ar')
            package.original_price = float(request.form.get('original_price', 0))
            package.package_price = float(request.form.get('package_price', 0))
            package.duration_hours = float(request.form.get('duration_hours', 0))
            package.icon = request.form.get('icon', 'gift')
            package.features = request.form.get('features')
            package.features_ar = request.form.get('features_ar')
            package.display_order = int(request.form.get('display_order', 0))
            package.is_active = 'is_active' in request.form
            
            db.session.commit()
            flash('Package updated successfully', 'success')
            return redirect(url_for('admin_packages'))
        except Exception as e:
            flash(f'Error: {str(e)}', 'error')
            db.session.rollback()
    
    return render_template('admin/package_edit.html', item=package, action='Edit', new_inquiries=new_inquiries)

@app.route('/admin/packages/delete/<int:package_id>', methods=['POST'])
@admin_required
def admin_package_delete(package_id):
    """Delete package."""
    package = Package.query.get_or_404(package_id)
    try:
        db.session.delete(package)
        db.session.commit()
        flash('Package deleted', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    return redirect(url_for('admin_packages'))
    

@app.route('/admin/portfolio')
@admin_required
def admin_portfolio():
    """List Portfolio Items."""
    items = PortfolioItem.query.order_by(PortfolioItem.display_order).all()
    new_inquiries = ContactInquiry.query.filter_by(status='new').count()
    return render_template('admin/portfolio_list.html', items=items, new_inquiries=new_inquiries)

@app.route('/admin/portfolio/new', methods=['GET', 'POST'])
@admin_required
def admin_portfolio_new():
    """Create new Portfolio Item."""
    new_inquiries = ContactInquiry.query.filter_by(status='new').count()
    if request.method == 'POST':
        try:
            thumbnail_url = upload_image(request.files.get('thumbnail'), 'portfolio')
            
            # Handle multiple gallery images
            image_urls = []
            for f in request.files.getlist('gallery'):
                url = upload_image(f, 'portfolio')
                if url: image_urls.append(url)
            
            # Get studio_id (0 means no studio linked)
            studio_id = request.form.get('studio_id')
            if studio_id:
                try:
                    studio_id = int(studio_id)
                    if studio_id == 0:
                        studio_id = None
                except ValueError:
                    studio_id = None
            else:
                studio_id = None
            
            item = PortfolioItem(
                title=request.form.get('title'),
                title_ar=request.form.get('title_ar'),
                slug=request.form.get('slug') or generate_slug(request.form.get('title')),
                client_name=request.form.get('client_name'),
                client_name_ar=request.form.get('client_name_ar'),
                category=request.form.get('category'),
                description=request.form.get('description'),
                description_ar=request.form.get('description_ar'),
                thumbnail_url=thumbnail_url,
                image_urls='\n'.join(image_urls) if image_urls else None,
                video_url=request.form.get('video_url'),
                tags=request.form.get('tags'),
                tags_ar=request.form.get('tags_ar'),
                is_featured='is_featured' in request.form,
                display_order=int(request.form.get('display_order', 0)),
                is_active='is_active' in request.form,
                studio_id=studio_id
            )
            db.session.add(item)
            db.session.commit()
            flash('Portfolio item created', 'success')
            return redirect(url_for('admin_portfolio'))
        except Exception as e:
            flash(f'Error: {str(e)}', 'error')
            db.session.rollback()
    
    # Get available studios for dropdown
    studios = Studio.query.filter_by(is_active=True).order_by(Studio.name).all()
    
    return render_template('admin/portfolio_edit.html', item=None, action='Create', new_inquiries=new_inquiries, studios=studios)

@app.route('/admin/portfolio/edit/<int:item_id>', methods=['GET', 'POST'])
@admin_required
def admin_portfolio_edit(item_id):
    """Edit Portfolio Item."""
    item = PortfolioItem.query.get_or_404(item_id)
    new_inquiries = ContactInquiry.query.filter_by(status='new').count()
    
    if request.method == 'POST':
        try:
            if request.files.get('thumbnail'):
                url = upload_image(request.files.get('thumbnail'), 'portfolio')
                if url: item.thumbnail_url = url
            
            existing_imgs = item.get_image_list()
            for f in request.files.getlist('gallery'):
                url = upload_image(f, 'portfolio')
                if url: existing_imgs.append(url)
            
            # Get studio_id (0 means no studio linked)
            studio_id = request.form.get('studio_id')
            if studio_id:
                try:
                    studio_id = int(studio_id)
                    if studio_id == 0:
                        studio_id = None
                except ValueError:
                    studio_id = None
            else:
                studio_id = None
            
            item.title = request.form.get('title')
            item.title_ar = request.form.get('title_ar')
            item.slug = request.form.get('slug') or generate_slug(item.title)
            item.client_name = request.form.get('client_name')
            item.client_name_ar = request.form.get('client_name_ar')
            item.category = request.form.get('category')
            item.description = request.form.get('description')
            item.description_ar = request.form.get('description_ar')
            item.image_urls = '\n'.join(existing_imgs) if existing_imgs else None
            item.video_url = request.form.get('video_url')
            item.tags = request.form.get('tags')
            item.tags_ar = request.form.get('tags_ar')
            item.is_featured = 'is_featured' in request.form
            item.display_order = int(request.form.get('display_order', 0))
            item.is_active = 'is_active' in request.form
            item.studio_id = studio_id
            
            db.session.commit()
            flash('Portfolio item updated', 'success')
            return redirect(url_for('admin_portfolio'))
        except Exception as e:
            flash(f'Error: {str(e)}', 'error')
            db.session.rollback()
    
    # Get available studios for dropdown
    studios = Studio.query.filter_by(is_active=True).order_by(Studio.name).all()
    
    return render_template('admin/portfolio_edit.html', item=item, action='Edit', new_inquiries=new_inquiries, studios=studios)

@app.route('/admin/portfolio/delete/<int:item_id>', methods=['POST'])
@admin_required
def admin_portfolio_delete(item_id):
    item = PortfolioItem.query.get_or_404(item_id)
    try:
        db.session.delete(item)
        db.session.commit()
        flash('Item deleted', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    return redirect(url_for('admin_portfolio'))

@app.route('/admin/portfolio/delete-image/<int:item_id>', methods=['POST'])
@admin_required
def admin_portfolio_delete_image(item_id):
    """Remove a specific image from the gallery."""
    item = PortfolioItem.query.get_or_404(item_id)
    url = request.form.get('image_url')
    if url and item.image_urls:
        imgs = item.get_image_list()
        if url in imgs:
            imgs.remove(url)
            item.image_urls = '\n'.join(imgs) if imgs else None
            db.session.commit()
            flash('Image removed', 'success')
    return redirect(url_for('admin_portfolio_edit', item_id=item_id))

@app.route('/admin/inquiries')
@admin_required
def admin_inquiries():
    """List Contact Inquiries."""
    inquiries = ContactInquiry.query.order_by(ContactInquiry.created_at.desc()).all()
    new_inquiries = ContactInquiry.query.filter_by(status='new').count()
    return render_template('admin/inquiries.html', inquiries=inquiries, new_inquiries=new_inquiries)

@app.route('/admin/inquiries/<int:inquiry_id>/update', methods=['POST'])
@admin_required
def update_inquiry(inquiry_id):
    """Update inquiry status (e.g., mark read)."""
    inquiry = ContactInquiry.query.get_or_404(inquiry_id)
    inquiry.status = request.form.get('status', inquiry.status)
    db.session.commit()
    flash('Inquiry status updated', 'success')
    return redirect(url_for('admin_inquiries'))


@app.route('/subscribe', methods=['POST'])
def newsletter_subscribe():
    """Handle footer newsletter subscriptions - Strict Email Only."""
    name = request.form.get('name', 'Subscriber')
    email = request.form.get('email', '').strip().lower()
    
    # 1. Server-Side Validation: Check pattern
    # This ensures that even if someone bypasses HTML, the server rejects it.
    email_pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    
    if not email or not re.match(email_pattern, email):
        flash('Invalid email format. Please enter a valid email address (e.g., user@example.com).', 'error')
        return redirect(request.referrer + '#footer')

    # 2. Check if lead already exists
    existing_lead = Lead.query.filter_by(email=email).first()

    if existing_lead:
        # Update existing lead note
        existing_lead.add_note(f"Re-subscribed to Newsletter on {datetime.now().strftime('%Y-%m-%d')}")
        db.session.commit()
        flash('You are already subscribed! We updated your profile.', 'info')
    else:
        # 3. Create new Lead (Email only)
        new_lead = Lead(
            name=name if name else "Newsletter Subscriber",
            email=email,
            phone=None, # Explicitly set phone to None
            source=Lead.SOURCE_NEWSLETTER,
            stage=Lead.STAGE_NEW,
            lead_score=10, 
            subject="Newsletter Subscription",
            admin_notes=f"Subscribed via footer form on {datetime.now().strftime('%Y-%m-%d')}"
        )
        db.session.add(new_lead)
        
        # Add Activity Log
        activity = LeadActivity(
            lead=new_lead,
            activity_type='note',
            description='User subscribed to newsletter.',
            created_by='System'
        )
        db.session.add(activity)
        db.session.commit()
        
        flash('Successfully subscribed to our newsletter!', 'success')

    return redirect(request.referrer + '#contact')

# ============================================
# Services Management Routes
# ============================================

@app.route('/admin/services')
@admin_required
def admin_services():
    """List all services."""
    services = Service.query.order_by(Service.display_order).all()
    new_inquiries = ContactInquiry.query.filter_by(status='new').count()
    return render_template('admin/services_list.html', items=services, new_inquiries=new_inquiries)

@app.route('/admin/services/new', methods=['GET', 'POST'])
@admin_required
def admin_service_new():
    """Create new service with tiers."""
    new_inquiries = ContactInquiry.query.filter_by(status='new').count()
    if request.method == 'POST':
        try:
            name_val = request.form.get('name')
            service = Service(
                name=name_val,
                name_ar=request.form.get('name_ar'),
                slug=generate_slug(name_val),
                category=request.form.get('category'),
                details=request.form.get('details'), 
                details_ar=request.form.get('details_ar'),
                hourly_rate=float(request.form.get('hourly_rate', 0)),
                is_quotation_only='is_quotation_only' in request.form, # NEW
                icon=request.form.get('icon', 'film'),
                display_order=int(request.form.get('display_order', 0)),
                is_active='is_active' in request.form,
                description="",
                features="",
                base_price=0.0
            )
            db.session.add(service)
            db.session.flush() # Get ID

            # Process Pricing Tiers
            durations = request.form.getlist('tier_duration[]')
            prices = request.form.getlist('tier_price[]')
            labels = request.form.getlist('tier_label[]')
            labels_ar = request.form.getlist('tier_label_ar[]')
            
            for i, (d, p, l) in enumerate(zip(durations, prices, labels)):
                l_ar = labels_ar[i] if i < len(labels_ar) else ""
                if d and p:
                    tier = ServicePricingTier(
                        service_id=service.id,
                        duration_hours=float(d),
                        price=float(p),
                        label=l,
                        label_ar=l_ar
                    )
                    db.session.add(tier)

            db.session.commit()
            flash('Service created successfully', 'success')
            return redirect(url_for('admin_services'))
        except Exception as e:
            flash(f'Error: {str(e)}', 'error')
            db.session.rollback()
    return render_template('admin/service_edit.html', item=None, action='Create', new_inquiries=new_inquiries)

@app.route('/admin/services/edit/<int:service_id>', methods=['GET', 'POST'])
@admin_required
def admin_service_edit(service_id):
    """Edit service and its tiers."""
    service = Service.query.get_or_404(service_id)
    new_inquiries = ContactInquiry.query.filter_by(status='new').count()
    
    if request.method == 'POST':
        try:
            service.name = request.form.get('name')
            service.name_ar = request.form.get('name_ar')
            service.slug = generate_slug(service.name)
            service.category = request.form.get('category')
            service.description = request.form.get('description')
            service.details = request.form.get('details') # NEW
            service.details_ar = request.form.get('details_ar')
            service.hourly_rate = float(request.form.get('hourly_rate', 0))
            service.is_quotation_only = 'is_quotation_only' in request.form # NEW
            service.features = request.form.get('features')
            service.icon = request.form.get('icon', 'film')
            service.display_order = int(request.form.get('display_order', 0))
            service.is_active = 'is_active' in request.form
            
            # Clear existing tiers and re-add
            ServicePricingTier.query.filter_by(service_id=service.id).delete()
            
            durations = request.form.getlist('tier_duration[]')
            prices = request.form.getlist('tier_price[]')
            labels = request.form.getlist('tier_label[]')
            labels_ar = request.form.getlist('tier_label_ar[]')
            
            for i, (d, p, l) in enumerate(zip(durations, prices, labels)):
                l_ar = labels_ar[i] if i < len(labels_ar) else ""
                if d and p:
                    tier = ServicePricingTier(
                        service_id=service.id,
                        duration_hours=float(d),
                        price=float(p),
                        label=l,
                        label_ar=l_ar
                    )
                    db.session.add(tier)
            
            db.session.commit()
            flash('Service updated', 'success')
            return redirect(url_for('admin_services'))
        except Exception as e:
            flash(f'Error: {str(e)}', 'error')
            db.session.rollback()
    
    return render_template('admin/service_edit.html', item=service, action='Edit', new_inquiries=new_inquiries)


@app.route('/admin/services/delete/<int:service_id>', methods=['POST'])
@admin_required
def admin_service_delete(service_id):
    """
    Delete service PERMANENTLY.
    WARNING: This deletes the service AND all Bookings/Quotes linked to it.
    """
    service = Service.query.get_or_404(service_id)
    try:
        num_bookings = Booking.query.filter_by(service_id=service.id).delete()
        db.session.delete(service)
        db.session.commit()
        
        if num_bookings > 0:
            flash(f'Service and {num_bookings} associated bookings were deleted permanently.', 'success')
        else:
            flash('Service deleted permanently.', 'success')
            
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting service: {str(e)}")
        flash(f'Error deleting service: {str(e)}', 'error')
        
    return redirect(url_for('admin_services'))

# ============================================
# Studios Management Routes
# ============================================

@app.route('/admin/studios')
@admin_required
def admin_studios():
    """List all studios."""
    studios = Studio.query.order_by(Studio.display_order.asc(), Studio.name.asc()).all()
    new_inquiries = ContactInquiry.query.filter_by(status='new').count()
    return render_template('admin/studios_list.html', items=studios, new_inquiries=new_inquiries)


@app.route('/admin/studios/delete-image/<int:studio_id>')
@admin_required
def admin_studio_delete_image(studio_id):
    """Remove studio image."""
    studio = Studio.query.get_or_404(studio_id)
    try:
        # Clear the image reference
        studio.image_url = None
        db.session.commit()
        flash('Studio image removed', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    return redirect(url_for('admin_studio_edit', studio_id=studio_id))


@app.route('/admin/studios/new', methods=['GET', 'POST'])
@admin_required
def admin_studio_new():
    """Create new studio."""
    new_inquiries = ContactInquiry.query.filter_by(status='new').count()
    if request.method == 'POST':
        try:
            image_url = None
            if 'image' in request.files and request.files['image'].filename:
                image_url = upload_image(request.files['image'], 'studios')

            studio = Studio(
                name=request.form.get('name'),
                ame_ar=request.form.get('name_ar'),
                slug=request.form.get('slug') or generate_slug(request.form.get('name')),
                persons_capacity=int(request.form.get('persons_capacity', 3)),
                description=request.form.get('description'),
                description_ar=request.form.get('description_ar'),
                specs=request.form.get('specs'),
                specs_ar=request.form.get('specs_ar'),
                image_url=image_url,  
                is_active='is_active' in request.form
            )
            db.session.add(studio)
            db.session.commit()
            flash('Studio created', 'success')
            return redirect(url_for('admin_studios'))
        except Exception as e:
            flash(f'Error: {str(e)}', 'error')
            db.session.rollback()
    return render_template('admin/studio_edit.html', item=None, action='Create', new_inquiries=new_inquiries)


@app.route('/admin/studios/edit/<int:studio_id>', methods=['GET', 'POST'])
@admin_required
def admin_studio_edit(studio_id):
    """Edit studio."""
    studio = Studio.query.get_or_404(studio_id)
    new_inquiries = ContactInquiry.query.filter_by(status='new').count()
    
    if request.method == 'POST':
        try:
            if 'image' in request.files and request.files['image'].filename:
                new_image_url = upload_image(request.files['image'], 'studios')
                if new_image_url:
                    studio.image_url = new_image_url

            studio.name = request.form.get('name')
            studio.name_ar = request.form.get('name_ar')
            studio.slug = request.form.get('slug') or generate_slug(studio.name)
            studio.display_order = int(request.form.get('display_order', 0))
            studio.persons_capacity = int(request.form.get('persons_capacity', 3))
            studio.description = request.form.get('description')
            studio.description_ar = request.form.get('description_ar')
            studio.specs = request.form.get('specs')
            studio.specs_ar = request.form.get('specs_ar')
            studio.is_active = 'is_active' in request.form
            
            db.session.commit()
            flash('Studio updated', 'success')
            return redirect(url_for('admin_studios'))
        except Exception as e:
            flash(f'Error: {str(e)}', 'error')
            db.session.rollback()
    
    
    return render_template('admin/studio_edit.html', item=studio, action='Edit', new_inquiries=new_inquiries)


@app.route('/admin/studios/delete/<int:studio_id>', methods=['POST'])
@admin_required
def admin_studio_delete(studio_id):
    """Delete studio."""
    studio = Studio.query.get_or_404(studio_id)
    try:
        db.session.delete(studio)
        db.session.commit()
        flash('Studio deleted', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    return redirect(url_for('admin_studios'))

# ============================================
# Equipment Management Routes
# ============================================

@app.route('/admin/equipment')
@admin_required
def admin_equipment():
    """List all equipment/extras."""
    equipment = ServiceAddOn.query.order_by(ServiceAddOn.category, ServiceAddOn.name).all()
    new_inquiries = ContactInquiry.query.filter_by(status='new').count()
    return render_template('admin/equipment_list.html', items=equipment, new_inquiries=new_inquiries)

@app.route('/admin/equipment/new', methods=['GET', 'POST'])
@admin_required
def admin_equipment_new():
    """Create new equipment item."""
    new_inquiries = ContactInquiry.query.filter_by(status='new').count()
    services = Service.query.filter_by(is_active=True).all()
    if request.method == 'POST':
        try:
            # Handle image upload
            image_url = None
            if 'image' in request.files and request.files['image'].filename:
                image_url = upload_image(request.files['image'], 'equipment')
            
            equipment = ServiceAddOn(
                service_id=request.form.get('service_id') or None,
                name=request.form.get('name'),
                name_ar=request.form.get('name_ar'),
                category=request.form.get('category', 'general'),
                description=request.form.get('description'),
                price=float(request.form.get('price', 0)),
                image_url=image_url,
                is_active='is_active' in request.form
            )
            db.session.add(equipment)
            db.session.commit()
            flash('Equipment item created', 'success')
            return redirect(url_for('admin_equipment'))
        except Exception as e:
            flash(f'Error: {str(e)}', 'error')
            db.session.rollback()
    return render_template('admin/equipment_edit.html', item=None, action='Create', new_inquiries=new_inquiries, services=services)

@app.route('/admin/equipment/edit/<int:equipment_id>', methods=['GET', 'POST'])
@admin_required
def admin_equipment_edit(equipment_id):
    """Edit equipment item."""
    equipment = ServiceAddOn.query.get_or_404(equipment_id)
    new_inquiries = ContactInquiry.query.filter_by(status='new').count()
    services = Service.query.filter_by(is_active=True).all()
    
    if request.method == 'POST':
        try:
            # Handle image upload (only if new image is provided)
            if 'image' in request.files and request.files['image'].filename:
                new_image_url = upload_image(request.files['image'], 'equipment')
                if new_image_url:
                    equipment.image_url = new_image_url


            if request.form.get('purchase_date'):
                 equipment.purchase_date = datetime.strptime(request.form.get('purchase_date'), '%Y-%m-%d').date()
            else:
                 equipment.purchase_date = None

            equipment.service_id = request.form.get('service_id') or None
            equipment.name = request.form.get('name')
            equipment.name_ar = request.form.get('name_ar')
            equipment.category = request.form.get('category', 'general')
            equipment.description = request.form.get('description')
            equipment.price = float(request.form.get('price', 0))
            equipment.is_active = 'is_active' in request.form
            
            db.session.commit()
            flash('Equipment updated', 'success')
            return redirect(url_for('admin_equipment'))
        except Exception as e:
            flash(f'Error: {str(e)}', 'error')
            db.session.rollback()
    
    return render_template('admin/equipment_edit.html', item=equipment, action='Edit', new_inquiries=new_inquiries, services=services)

@app.route('/admin/equipment/delete-image/<int:equipment_id>', methods=['POST'])
@admin_required
def admin_equipment_delete_image(equipment_id):
    """Remove equipment image."""
    equipment = ServiceAddOn.query.get_or_404(equipment_id)
    try:
        equipment.image_url = None
        db.session.commit()
        flash('Equipment image removed', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    return redirect(url_for('admin_equipment_edit', equipment_id=equipment_id))

@app.route('/admin/equipment/delete/<int:equipment_id>', methods=['POST'])
@admin_required
def admin_equipment_delete(equipment_id):
    """Delete equipment item."""
    equipment = ServiceAddOn.query.get_or_404(equipment_id)
    try:
        db.session.delete(equipment)
        db.session.commit()
        flash('Equipment deleted', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    return redirect(url_for('admin_equipment'))

# ============================================
# Lead Management Routes
# ============================================

@app.route('/admin/leads')
@admin_required
def admin_leads():
    """Lead Management Dashboard with Kanban board."""
    # Get KPI metrics

    try:
        unseen_leads = Lead.query.filter_by(is_seen=False).all()
        if unseen_leads:
            for lead in unseen_leads:
                lead.is_seen = True
            db.session.commit()
    except Exception as e:
        current_app.logger.error(f"Error resetting lead notifications: {e}")

    total_leads = Lead.query.count()
    new_leads_count = Lead.query.filter_by(stage=Lead.STAGE_NEW).count()
    qualified_leads = Lead.query.filter_by(stage=Lead.STAGE_QUALIFIED).count()
    converted_leads = Lead.query.filter_by(stage=Lead.STAGE_CONVERTED).count()
    
    # Get leads grouped by stage for the Kanban board
    leads_by_stage = {}
    for stage_value, stage_label in Lead.STAGE_CHOICES:
        leads = Lead.query.filter_by(stage=stage_value).order_by(Lead.created_at.desc()).all()
        leads_by_stage[stage_value] = {
            'label': stage_label,
            'leads': leads,
            'count': len(leads)
        }
    
    new_inquiries = ContactInquiry.query.filter_by(status='new').count()
    
    return render_template('admin/leads.html',
                         leads_by_stage=leads_by_stage,
                         total_leads=total_leads,
                         new_leads_count=new_leads_count,
                         qualified_leads=qualified_leads,
                         converted_leads=converted_leads,
                         new_inquiries=new_inquiries)


@app.route('/admin/leads/<int:lead_id>')
@admin_required
def lead_detail(lead_id):
    """Get lead details for modal."""
    lead = Lead.query.get_or_404(lead_id)
    new_inquiries = ContactInquiry.query.filter_by(status='new').count()
    return render_template('admin/lead_detail.html', lead=lead, new_inquiries=new_inquiries)


@app.route('/admin/leads/<int:lead_id>/update', methods=['POST'])
@admin_required
def lead_update(lead_id):
    """Update lead details."""
    lead = Lead.query.get_or_404(lead_id)
    
    # 1. Update Standard Fields
    lead.name = request.form.get('name', lead.name)
    lead.email = request.form.get('email', lead.email)
    lead.phone = request.form.get('phone', lead.phone)
    lead.company = request.form.get('company', lead.company)
    
    # 2. Handle Status/Stage Change (Log it if changed)
    new_stage = request.form.get('stage')
    if new_stage and new_stage != lead.stage:
        # Create activity log automatically
        activity = LeadActivity(
            lead_id=lead.id,
            activity_type=LeadActivity.TYPE_STAGE_CHANGE,
            description=f"Status updated manually from {lead.stage} to {new_stage}",
            created_by=session.get('user_name', 'Admin')
        )
        db.session.add(activity)
        lead.stage = new_stage

    # 3. Handle Temperature & Score
    lead.temperature = request.form.get('temperature', lead.temperature)
    try:
        lead.lead_score = int(request.form.get('lead_score', lead.lead_score))
    except (ValueError, TypeError):
        pass # Keep previous score if invalid input

    # 4. FIX: Handle Date Correctly (The cause of your 500 error)
    date_str = request.form.get('follow_up_date', '').strip()
    if date_str:
        try:
            lead.follow_up_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            lead.follow_up_date = None
    else:
        lead.follow_up_date = None  # Set to None (NULL) if empty string

    db.session.commit()
    flash('Lead details updated successfully', 'success')
    return redirect(request.referrer or url_for('admin_leads'))


@app.route('/admin/leads/<int:lead_id>/stage', methods=['POST'])
@admin_required
def lead_update_stage(lead_id):
    """Update lead stage via AJAX."""
    lead = Lead.query.get_or_404(lead_id)
    new_stage = request.form.get('stage')
    
    if new_stage in [s[0] for s in Lead.STAGE_CHOICES]:
        old_stage = lead.stage
        lead.stage = new_stage
        
        # Log stage change activity
        activity = LeadActivity(
            lead_id=lead.id,
            activity_type=LeadActivity.TYPE_STAGE_CHANGE,
            description=f"Stage changed from {old_stage} to {new_stage}",
            created_by=session.get('user_name', 'Admin')
        )
        db.session.add(activity)
        
        # Update temperature based on stage
        if new_stage == Lead.STAGE_CONVERTED:
            lead.converted_at = datetime.utcnow()
            lead.temperature = Lead.TEMP_HOT
            lead.lead_score = 100
        elif new_stage == Lead.STAGE_LOST:
            lead.temperature = Lead.TEMP_COLD
        
        db.session.commit()
        return jsonify({'success': True, 'new_stage': new_stage})
    
    return jsonify({'success': False, 'error': 'Invalid stage'}), 400


@app.route('/admin/leads/<int:lead_id>/activity', methods=['POST'])
@admin_required
def lead_add_activity(lead_id):
    """Add activity to lead via AJAX."""
    lead = Lead.query.get_or_404(lead_id)
    
    activity_type = request.form.get('activity_type', LeadActivity.TYPE_NOTE)
    description = request.form.get('description', '').strip()
    
    if description:
        activity = LeadActivity(
            lead_id=lead.id,
            activity_type=activity_type,
            description=description,
            created_by=session.get('user_name', 'Admin')
        )
        db.session.add(activity)
        
        # Update last contact timestamp for calls/emails/meetings
        if activity_type in [LeadActivity.TYPE_CALL, LeadActivity.TYPE_EMAIL, LeadActivity.TYPE_MEETING]:
            lead.last_contact_at = datetime.utcnow()
            # Boost score slightly for engagement
            lead.lead_score = min(100, lead.lead_score + 5)
        
        db.session.commit()
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'error': 'Description required'}), 400


@app.route('/admin/leads/<int:lead_id>/delete', methods=['POST'])
@admin_required
def lead_delete(lead_id):
    """Delete a lead."""
    lead = Lead.query.get_or_404(lead_id)
    try:
        db.session.delete(lead)
        db.session.commit()
        flash('Lead deleted successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting lead: {str(e)}', 'error')
    return redirect(url_for('admin_leads'))


# ============================================
# Lead API Routes (JSON)
# ============================================

@app.route('/api/leads')
@admin_required
def api_leads():
    """Get leads as JSON for filtering."""
    stage = request.args.get('stage')
    search = request.args.get('search')
    temperature = request.args.get('temperature')
    
    query = Lead.query
    
    if stage:
        query = query.filter_by(stage=stage)
    
    if temperature:
        query = query.filter_by(temperature=temperature)
    
    if search:
        search_term = f"%{search}%"
        query = query.filter(or_(
            Lead.name.ilike(search_term),
            Lead.email.ilike(search_term),
            Lead.company.ilike(search_term)
        ))
    
    leads = query.order_by(Lead.created_at.desc()).all()
    
    return jsonify({
        'leads': [{
            'id': lead.id,
            'name': lead.name,
            'email': lead.email,
            'phone': lead.phone,
            'company': lead.company,
            'stage': lead.stage,
            'temperature': lead.temperature,
            'lead_score': lead.lead_score,
            'source': lead.source,
            'created_at': lead.created_at.isoformat(),
            'subject': lead.subject
        } for lead in leads]
    })


@app.route('/api/leads/stats')
@admin_required
def api_leads_stats():
    """Get lead statistics."""
    total = Lead.query.count()
    new_leads = Lead.query.filter_by(stage=Lead.STAGE_NEW).count()
    qualified = Lead.query.filter_by(stage=Lead.STAGE_QUALIFIED).count()
    converted = Lead.query.filter_by(stage=Lead.STAGE_CONVERTED).count()
    
    # Calculate conversion rate
    closed = converted + Lead.query.filter_by(stage=Lead.STAGE_LOST).count()
    conversion_rate = round((converted / closed * 100), 1) if closed > 0 else 0
    
    return jsonify({
        'total': total,
        'new': new_leads,
        'qualified': qualified,
        'converted': converted,
        'conversion_rate': conversion_rate
    })

# ============================================
# Unified Services Management Route
# ============================================

@app.route('/admin/services-management')
@admin_required
def admin_services_management():
    """Unified services management dashboard."""
    services = Service.query.order_by(Service.display_order).all()
    studios = Studio.query.order_by(Studio.name).all()
    equipment = ServiceAddOn.query.order_by(ServiceAddOn.category, ServiceAddOn.name).all()
    new_inquiries = ContactInquiry.query.filter_by(status='new').count()
    
    return render_template('admin/services_management.html',
                         services=services,
                         studios=studios,
                         equipment=equipment,
                         new_inquiries=new_inquiries)

# ============================================
# API Routes (JSON)
# ============================================

@app.route('/admin/settings')
@login_required 
def admin_settings():
    # Update the path to match your folder structure
    return render_template('admin/admin_hub.html')
    
@app.route('/api/services')
def api_services():
    services = Service.query.filter_by(is_active=True).all()
    return jsonify({'services': [s.to_dict() for s in services]})

@app.route('/api/portfolio')
def api_portfolio():
    category = request.args.get('category')
    query = PortfolioItem.query.filter_by(is_active=True)
    if category: query = query.filter_by(category=category)
    items = query.order_by(PortfolioItem.display_order).all()
    
    categories = db.session.query(
        PortfolioItem.category, func.count(PortfolioItem.id)
    ).filter(PortfolioItem.is_active == True).group_by(PortfolioItem.category).all()
    
    return jsonify({
        'portfolio': [{
            'id': item.id, 'title': item.title, 'slug': item.slug, 
            'thumbnail_url': item.thumbnail_url, 'category': item.category
        } for item in items],
        'categories': [{'name': c[0], 'count': c[1]} for c in categories]
    })

# ============================================
# CLI Commands
# ============================================

@app.cli.command('init-db')
def init_db_command():
    """Initialize the database with specific requested data."""
    db.create_all()
    
    # Check if data exists
    if Service.query.first():
        print('Database already contains data. Drop db first if you want to reset.')
        return
    
    # 1. Services (Phase 1 Data)
    services_data = [
        {
            'name': 'Customize Your Service', 
            'slug': 'custom-package', 
            'duration': 0.0, 
            'price': 0.0, 
            'icon': 'wand-magic-sparkles', 
            'cat': 'exclusive',
            'order': -1, # Ensures it is first
            'features': 'Fully Tailored Experience|Dedicated Creative Director|Priority Support|Flexible Timeline'
        },
        
        {'name': 'Podcast Production', 'slug': 'podcast', 'duration': 4.0, 'price': 500.0, 'icon': 'microphone', 'cat': 'audio'},
        {'name': 'Product Advertising', 'slug': 'product', 'duration': 6.0, 'price': 800.0, 'icon': 'shopping-bag', 'cat': 'advertising'},
        {'name': 'Corporate Video Services', 'slug': 'corporate', 'duration': 8.0, 'price': 1200.0, 'icon': 'building', 'cat': 'corporate'},
        {'name': 'Social Media Content', 'slug': 'social', 'duration': 3.0, 'price': 400.0, 'icon': 'hashtag', 'cat': 'social'},
        {'name': 'Pre-Production Services', 'slug': 'pre-prod', 'duration': 8.0, 'price': 600.0, 'icon': 'clipboard-list', 'cat': 'pre_production'},
        {'name': 'Post-Production Services', 'slug': 'post-prod', 'duration': 10.0, 'price': 700.0, 'icon': 'laptop-medical', 'cat': 'post_production'},
    ]
    
    for i, s in enumerate(services_data):
        service = Service(
            name=s['name'], 
            slug=s['slug'],
            category=s['cat'],
            base_price=s['price'], 
            duration_hours=s['duration'],
            icon=s['icon'],
            display_order=i,
            description=f"Professional {s['name']} session."
        )
        db.session.add(service)
    
    # 2. Studios (Phase 2 Data)
    studios_data = [
        {'name': 'Digital whiteboard studio', 'persons': 3},
        {'name': 'Modern Kitchen', 'persons': 4},
        {'name': 'Studio A - Main Production Floor', 'persons': 6},
        {'name': 'Studio B - Podcast Suite', 'persons': 4},
        {'name': 'Studio C - Green Screen', 'persons': 5},
    ]
    
    for s in studios_data:
        db.session.add(Studio(name=s['name'], persons_capacity=s['persons']))

    # 3. Equipment & Extras (Phase 3 Data)
    extras_data = [
        {'name': 'Sony FX30 Cinema Camera Kit', 'cat': 'camera', 'price': 250.0},
        {'name': 'Blackmagic URSA Mini Pro', 'cat': 'camera', 'price': 200.0},
        {'name': 'Canon R6 camera kit', 'cat': 'camera', 'price': 200.0},
        {'name': 'Professional Lighting Package', 'cat': 'lighting', 'price': 100.0},
        {'name': 'Aputure 600D Pro', 'cat': 'lighting', 'price': 75.0},
        {'name': 'Hollyland Lark 2 Wireless Mic Set', 'cat': 'audio', 'price': 80.0},
        {'name': 'Rode Podcaster Kit', 'cat': 'audio', 'price': 60.0},
        {'name': 'Teleprompter System', 'cat': 'accessories', 'price': 50.0},
        {'name': 'DJI Ronin RS3 Pro', 'cat': 'accessories', 'price': 100.0},
    ]

    for e in extras_data:
        # Note: service_id is None because these are global extras
        db.session.add(ServiceAddOn(name=e['name'], category=e['cat'], price=e['price']))
        
    # Create sample portfolio items (Studios)
    # Categories: Production, Podcast, Commercial, Educational
    portfolio_data = [
        {'title': 'Studio A - Main Production Floor', 'slug': 'studio-a-main-production', 'client_name': 'Ptah Studios', 'category': 'production', 'is_featured': True},
        {'title': 'Studio B - Podcast Suite', 'slug': 'studio-b-podcast', 'client_name': 'Ptah Studios', 'category': 'podcast', 'is_featured': True},
        {'title': 'Studio C - Green Screen', 'slug': 'studio-c-green-screen', 'client_name': 'Ptah Studios', 'category': 'commercial', 'is_featured': True},
        {'title': 'Digital Whiteboard Studio', 'slug': 'digital-whiteboard', 'client_name': 'Ptah Studios', 'category': 'educational', 'is_featured': True},
        {'title': 'Modern Kitchen', 'slug': 'modern-kitchen', 'client_name': 'Ptah Studios', 'category': 'commercial', 'is_featured': True}
    ]
    
    for item_data in portfolio_data:
        item = PortfolioItem(**item_data)
        db.session.add(item)
    
    db.session.commit()
    print('Database initialized with requested data successfully!')


@app.cli.command('drop-db')
def drop_db_command():
    """Drop all database tables."""
    db.drop_all()
    print('Database dropped successfully!')


# ============================================
# Auth Routes
# ============================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User Login."""
    if 'user_id' in session:
        return redirect(url_for('admin_dashboard') if session.get('is_admin') else url_for('index'))
    
    error = None
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        
        # 1. Fetch the user by email
        user = User.query.filter_by(email=email).first()
        
        # 2. CRITICAL FIX: Ensure BOTH the user exists AND the password matches
        if user and user.check_password(password):
            # Login successful
            session['user_id'] = user.id
            session['is_admin'] = user.is_admin
            session['user_name'] = user.name
            flash(f'Welcome back, {user.name}!', 'success')
            
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            
            if user.role == 'super_admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('index'))
        else:
            # Login failed: Either user doesn't exist OR password was wrong
            error = 'Invalid email or password'
            
    return render_template('public/login.html', error=error)

@app.route('/register', methods=['GET', 'POST'])
def register():
    """User Registration."""
    error = None
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        
        if not name or not email or not password:
            error = 'All fields required'
        elif password != confirm:
            error = 'Passwords do not match'
        elif len(password) < 6:
            error = 'Password must be at least 6 characters'
        elif User.query.filter_by(email=email).first():
            error = 'Email already registered'
        else:
            user = User(name=name, email=email)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            
            session['user_id'] = user.id
            session['is_admin'] = user.is_admin
            session['user_name'] = user.name
            
            flash('Account created successfully!', 'success')
            return redirect(url_for('index'))
    
    return render_template('public/register.html', error=error)

@app.route('/logout')
def logout():
    """User Logout."""
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

# ============================================
# Error Handlers
# ============================================

@app.errorhandler(404)
def not_found_error(error):
    return render_template('errors/404.html'), 404

@app.errorhandler(403)
def forbidden_error(error):
    return render_template('errors/403.html'), 403

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('errors/500.html'), 500

# ============================================
# Main Entry Point
# ============================================

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
