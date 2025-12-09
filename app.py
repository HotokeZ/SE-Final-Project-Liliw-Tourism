from flask import Flask, render_template, redirect, url_for, request, flash, session
from supabase import create_client, Client
from dotenv import load_dotenv
from functools import wraps
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
import re

# Load environment variables from .env file in the same directory as app.py
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'your-secret-key-here')

# ============================================
# SUPABASE CONFIGURATION
# ============================================

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
SUPABASE_SERVICE_ROLE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY')  # Optional, for server-side privileged ops

# Check if credentials are loaded
if not SUPABASE_URL or not SUPABASE_KEY:
    print("WARNING: Supabase credentials not found in .env file!")
    print(f"Looking for .env at: {env_path}")
    # Use empty values to prevent crash during development
    supabase = None
else:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Create an admin client when service role key is available (server-side only)
supabase_admin: Client | None = None
try:
    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
        print("Supabase admin client initialized for privileged operations (storage/uploads).")
except Exception as _e:
    print(f"WARNING: Could not initialize Supabase admin client: {_e}")

# ============================================
# HELPER FUNCTIONS
# ============================================

def generate_slug(text):
    """Generate URL-friendly slug from text"""
    slug = text.lower()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    return slug.strip('-')

def calculate_reading_time(content):
    """Calculate approximate reading time in minutes"""
    words = len(content.split())
    return max(1, round(words / 200))  # Average 200 words per minute

def admin_required(f):
    """Decorator to require admin login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            flash('Please login to access the admin panel.', 'error')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

def login_required(f):
    """Decorator to require user login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            flash('Please login to access this page.', 'error')
            return redirect(url_for('user_login'))
        return f(*args, **kwargs)
    return decorated_function

def verified_required(f):
    """Decorator to require verified user"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            flash('Please login to access this page.', 'error')
            return redirect(url_for('user_login'))
        if not session.get('user_verified'):
            flash('Please verify your email to access this feature.', 'warning')
            return redirect(url_for('verification_pending'))
        return f(*args, **kwargs)
    return decorated_function

def get_stats():
    """Get dashboard statistics"""
    stats = {
        'blogs': 0, 'pending_blogs': 0, 'attractions': 0,
        'products': 0, 'events': 0, 'hotels': 0,
        'restaurants': 0, 'reports': 0
    }
    
    if supabase:
        try:
            # Count blogs
            response = supabase.table('blogs').select('id, status').execute()
            blogs = response.data
            stats['blogs'] = len(blogs)
            stats['pending_blogs'] = len([b for b in blogs if b.get('status') == 'pending'])
            
            # Count other entities (with error handling for missing tables)
            for table, key in [('attractions', 'attractions'), ('products', 'products'), 
                              ('events', 'events'), ('hotels', 'hotels'), 
                              ('restaurants', 'restaurants')]:
                try:
                    response = supabase.table(table).select('id', count='exact').execute()
                    stats[key] = len(response.data) if response.data else 0
                except:
                    pass
            
            # Count reports
            try:
                response = supabase.table('blog_reports').select('id').execute()
                stats['reports'] = len(response.data) if response.data else 0
            except:
                pass
        except Exception as e:
            print(f"Error getting stats: {e}")
    
    return stats

# ============================================
# HOME & MAIN PAGES
# ============================================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/home')
def home():
    return render_template('index.html')

@app.route('/map')
def map():
    return render_template('map.html')

# ============================================
# ATTRACTIONS ROUTES
# ============================================

@app.route('/attractions')
def attractions():
    return render_template('home/attractions.html')

@app.route('/attractions/natural')
def natural():
    return render_template('home/attractions/natural.html')

@app.route('/attractions/heritage')
def heritage():
    return render_template('home/attractions/heritage.html')

@app.route('/attractions/<attraction>')
def indiv_attractions(attraction):
    # Define heritage attractions
    heritage_attractions = ['gat-tayaw', 'liliw-church', 'old-houses', 'plaza']

    # Determine category
    category = 'heritage' if attraction in heritage_attractions else 'natural'

    # Sample data - replace with database queries
    attraction_data = {
        'name': attraction.replace('-', ' ').title(),
        'category': category,
        'image': 'hero.JPG',
        'location': 'Liliw, Laguna',
        'description': 'A beautiful attraction in Liliw',
        'full_description': 'Detailed description of the attraction.',
        'duration': '2-3 hours',
        'difficulty': 'Moderate',
        'highlights': ['Beautiful scenery', 'Perfect for photos', 'Family-friendly'],
        'activities': [
            {'icon': 'swimming-pool', 'name': 'Swimming', 'description': 'Enjoy the cool waters'},
            {'icon': 'camera', 'name': 'Photography', 'description': 'Capture stunning views'}
        ],
        'directions': {
            'car': 'Drive from Manila via SLEX, approximately 2 hours',
            'public': 'Take a bus to Liliw then tricycle to the site'
        },
        'tips': [
            {'icon': 'clock', 'title': 'Best Time', 'description': 'Visit early morning for fewer crowds'},
            {'icon': 'shoe-prints', 'title': 'What to Wear', 'description': 'Comfortable hiking shoes recommended'}
        ],
        'entrance_fee': '₱50 per person',
        'hours': '7:00 AM - 5:00 PM',
        'best_time': 'November to May',
        'contact': '(049) 123-4567',
        'map_embed': 'https://www.google.com/maps/embed?pb=!1m18!1m12!1m3!1d3872.7!2d121.4!3d14.1!2m3!1f0!2f0!3f0!3m2!1i1024!2i768!4f13.1!3m3!1m2!1s0x0%3A0x0!2zMTTCsDA2JzAwLjAiTiAxMjHCsDI0JzAwLjAiRQ!5e0!3m2!1sen!2sph!4v1234567890'
    }

    related_attractions = [
        {'name': 'Hulugan Falls', 'slug': 'hulugan-falls', 'category': 'natural', 'image': 'hero.JPG', 'location': 'Barangay Luquin'},
        {'name': 'Taytay Falls', 'slug': 'taytay-falls', 'category': 'natural', 'image': 'hero.JPG', 'location': 'Barangay Dagatan'}
    ]

    return render_template('home/attractions/indiv-attractions.html',
                         attraction=attraction_data,
                         related_attractions=related_attractions)

# ============================================
# EXPERIENCES ROUTES
# ============================================

@app.route('/experiences')
def experiences():
    return render_template('experiences/products.html')

@app.route('/experiences/festivals')
def festivals():
    return render_template('experiences/festivals.html')

@app.route('/experiences/festivals/events')
def events():
    return render_template('experiences/festivals/events.html')

@app.route('/experiences/festivals/about')
def festivals_about():
    return render_template('experiences/festivals/about.html')

@app.route('/experiences/festivals/history')
def festivals_history():
    return render_template('experiences/festivals/history.html')

@app.route('/experiences/products')
def products():
    return render_template('experiences/products.html')

@app.route('/experiences/products/<product>')
def indiv_product(product):
    # Sample product data
    product_data = {
        'name': product.replace('-', ' ').title(),
        'category': 'Footwear',
        'main_image': 'tsinelas.jpg',
        'description': 'High-quality handcrafted product from Liliw',
        'full_description': 'Detailed description of the product and its making process.',
        'price': '₱150 - ₱500',
        'features': ['Handmade', 'Durable materials', 'Comfortable fit', 'Various designs'],
        'specifications': [
            {'label': 'Material', 'value': 'Genuine leather'},
            {'label': 'Available Sizes', 'value': '5-12'},
            {'label': 'Colors', 'value': 'Multiple options'}
        ],
        'making_process': 'Our artisans carefully craft each piece using traditional techniques passed down through generations.',
        'process_steps': [
            {'title': 'Material Selection', 'description': 'Choose high-quality leather and materials'},
            {'title': 'Cutting & Shaping', 'description': 'Precisely cut and shape the components'},
            {'title': 'Assembly', 'description': 'Skillfully assemble all pieces together'},
            {'title': 'Finishing', 'description': 'Add final touches and quality check'}
        ],
        'sellers': [
            {'name': 'Liliw Footwear Center', 'location': 'Town Center'},
            {'name': 'Gat Tayaw Vendor Area', 'location': 'Near Plaza'}
        ],
        'gallery': ['tsinelas-1.jpg', 'tsinelas-2.jpg', 'tsinelas-3.jpg']
    }

    related_products = [
        {'name': 'Leather Sandals', 'slug': 'leather-sandals', 'image': 'hero.JPG', 'price': '₱300 - ₱800'},
        {'name': 'Leather Bags', 'slug': 'leather-bags', 'image': 'hero.JPG', 'price': '₱500 - ₱1,500'}
    ]

    return render_template('experiences/indiv-product.html',
                         product=product_data,
                         related_products=related_products)

@app.route('/experiences/gallery')
def gallery():
    return render_template('experiences/gallery.html')

@app.route('/experiences/add-media')
def add_media():
    return render_template('experiences/add-media.html')

# ============================================
# PLAN YOUR TRIP ROUTES
# ============================================

@app.route('/plan')
def plan():
    return render_template('plan/stay.html')

@app.route('/plan/stay')
def stay():
    return render_template('plan/stay.html')

@app.route('/plan/stay/<hotel>')
def indiv_hotel(hotel):
    # Sample hotel data
    hotel_data = {
        'name': hotel.replace('-', ' ').title(),
        'image': 'hero.JPG',
        'rating': 4.5,
        'price_range': '₱1,500 - ₱3,500 per night',
        'address': 'Main Street, Liliw, Laguna',
        'phone': '(049) 123-4567',
        'email': 'info@hotel.com',
        'description': 'Comfortable accommodation in the heart of Liliw',
        'amenities': [
            {'icon': 'wifi', 'name': 'Free WiFi'},
            {'icon': 'parking', 'name': 'Free Parking'},
            {'icon': 'swimming-pool', 'name': 'Swimming Pool'},
            {'icon': 'utensils', 'name': 'Restaurant'},
            {'icon': 'coffee', 'name': 'Breakfast Included'},
            {'icon': 'concierge-bell', 'name': '24/7 Reception'}
        ],
        'rooms': [
            {'name': 'Standard Room', 'price': '₱1,500', 'features': ['Queen bed', 'AC', 'Cable TV'], 'image': 'hero.JPG'},
            {'name': 'Deluxe Room', 'price': '₱2,500', 'features': ['King bed', 'AC', 'Smart TV', 'Mini bar'], 'image': 'hero.JPG'}
        ],
        'policies': ['Check-in: 2:00 PM', 'Check-out: 12:00 NN', 'Free cancellation up to 48 hours'],
        'map_embed': 'https://www.google.com/maps/embed?pb=!1m18!1m12!1m3!1d3872.7!2d121.4!3d14.1'
    }

    similar_hotels = [
        {'name': 'Other Hotel', 'slug': 'other-hotel', 'image': 'hero.JPG', 'price': '₱2,000', 'rating': 4.3},
    ]

    return render_template('plan/indiv-hotel.html', hotel=hotel_data, similar_hotels=similar_hotels)

@app.route('/plan/eat')
def eat():
    return render_template('plan/eat.html')

@app.route('/plan/eat/<restaurant>')
def indiv_resto(restaurant):
    # Sample restaurant data
    resto_data = {
        'name': restaurant.replace('-', ' ').title(),
        'image': 'hero.JPG',
        'rating': 4.7,
        'cuisine': 'Filipino',
        'price_range': '₱150 - ₱400 per person',
        'address': 'Town Plaza, Liliw, Laguna',
        'phone': '(049) 123-4567',
        'hours': '10:00 AM - 9:00 PM Daily',
        'description': 'Authentic Filipino cuisine in a cozy atmosphere',
        'specialties': ['Adobo', 'Sinigang', 'Lechon Kawali', 'Kare-Kare'],
        'menu_highlights': [
            {'name': 'Adobo', 'price': '₱180', 'description': 'Classic chicken and pork adobo'},
            {'name': 'Sinigang', 'price': '₱200', 'description': 'Sour tamarind soup with pork'},
            {'name': 'Lechon Kawali', 'price': '₱250', 'description': 'Crispy pork belly'},
        ],
        'features': ['Dine-in', 'Take-out', 'Free WiFi', 'Air-conditioned'],
        'map_embed': 'https://www.google.com/maps/embed?pb=!1m18!1m12!1m3!1d3872.7!2d121.4!3d14.1'
    }

    similar_restos = [
        {'name': 'Other Restaurant', 'slug': 'other-restaurant', 'image': 'hero.JPG', 'cuisine': 'Filipino', 'price_range': '₱200-500'},
    ]

    return render_template('plan/indiv-resto.html', resto=resto_data, similar_restos=similar_restos)

@app.route('/plan/travel-tips')
def travel_tips():
    return render_template('plan/travel-tips.html')

@app.route('/plan/blog')
def blog():
    # Pagination params
    try:
        per_page = int(request.args.get('per_page', 6))
        if per_page <= 0 or per_page > 50:
            per_page = 6
    except ValueError:
        per_page = 6
    try:
        page = int(request.args.get('page', 1))
        if page <= 0:
            page = 1
    except ValueError:
        page = 1

    blogs = []
    total_items = 0
    total_pages = 1

    if supabase:
        try:
            # Get total count (safe approach)
            total_resp = supabase.table('blogs').select('id').eq('status', 'approved').execute()
            total_items = len(total_resp.data) if total_resp and total_resp.data else 0
            total_pages = max(1, (total_items + per_page - 1) // per_page)

            # Clamp page to available range
            if page > total_pages:
                page = total_pages

            start = (page - 1) * per_page
            end = start + per_page - 1

            # Fetch page slice
            response = (supabase
                        .table('blogs')
                        .select('*')
                        .eq('status', 'approved')
                        .order('created_at', desc=True)
                        .range(start, end)
                        .execute())
            blogs = response.data or []
        except Exception as e:
            print(f"Error fetching blogs: {e}")

    return render_template('plan/blog.html', 
                           blogs=blogs, 
                           current_page=page, 
                           total_pages=total_pages, 
                           per_page=per_page,
                           total_items=total_items)

@app.route('/plan/blog/<int:blog_id>')
def view_blog(blog_id):
    # Fetch a single blog post
    if not supabase:
        flash('Database connection unavailable.', 'error')
        return redirect(url_for('blog'))
    
    try:
        response = supabase.table('blogs').select('*').eq('id', blog_id).eq('status', 'approved').single().execute()
        blog_post = response.data
        if not blog_post:
            raise Exception('Blog not found')

        # Parse gallery images from comma-separated image_url field
        gallery_images = []
        raw_url = blog_post.get('image_url')
        if isinstance(raw_url, str) and raw_url.strip():
            gallery_images = [u.strip() for u in raw_url.split(',') if u.strip()]
    except Exception as e:
        print(f"Error fetching blog: {e}")
        flash('Blog post not found.', 'error')
        return redirect(url_for('blog'))
    
    return render_template('plan/view-blog.html', blog=blog_post, gallery_images=gallery_images)

@app.route('/plan/blog/create')
@verified_required
def create_blog():
    return render_template('plan/create.html')

@app.route('/blog/create')
def create():
    return redirect(url_for('create_blog'))

@app.route('/plan/blog/submit', methods=['POST'])
@verified_required
def submit_blog():
    if not supabase:
        flash('Database connection unavailable. Please try again later.', 'error')
        return redirect(url_for('blog'))
    
    try:
        # Get form data
        title = request.form.get('title')
        category = request.form.get('category', 'Adventure')
        content = request.form.get('content')
        
        # Get user info from session
        user_id = session.get('user_id')
        author = session.get('user_name')
        email = session.get('user_email')

        def upload_bytes_get_url(file_bytes: bytes, file_ext: str, content_type: str) -> str:
            unique_filename = f"{uuid.uuid4()}.{file_ext}"
            if supabase_admin:
                try:
                    supabase_admin.storage.from_('blog-images').upload(
                        path=unique_filename,
                        file=file_bytes,
                        file_options={"content-type": content_type}
                    )
                    return supabase_admin.storage.from_('blog-images').get_public_url(unique_filename)
                except Exception as supabase_error:
                    print(f"Supabase Storage failed, using local: {supabase_error}")
            # Fallback to local storage
            uploads_folder = Path(__file__).parent / 'static' / 'uploads'
            uploads_folder.mkdir(parents=True, exist_ok=True)
            file_path = uploads_folder / unique_filename
            file_path.write_bytes(file_bytes)
            return f"/static/uploads/{unique_filename}"

        # Collect all uploaded image URLs here
        all_image_urls = []

        # Handle featured image (thumbnail) - uploaded first so it becomes first in list
        if 'featured_image' in request.files:
            file = request.files['featured_image']
            if file and file.filename:
                try:
                    file_ext = file.filename.rsplit('.', 1)[-1].lower()
                    file_bytes = file.read()
                    url = upload_bytes_get_url(file_bytes, file_ext, file.content_type)
                    all_image_urls.append(url)
                except Exception as img_error:
                    flash(f'Image upload failed: {img_error}', 'warning')

        # Handle gallery images (multiple)
        gallery_files = request.files.getlist('gallery_images') or []
        for gf in gallery_files:
            try:
                if gf and gf.filename:
                    gext = gf.filename.rsplit('.', 1)[-1].lower()
                    gbytes = gf.read()
                    gurl = upload_bytes_get_url(gbytes, gext, gf.content_type)
                    all_image_urls.append(gurl)
            except Exception as gerr:
                print(f"Gallery image upload failed: {gerr}")

        # Join all URLs with comma for storage in a single field
        image_url = ','.join(all_image_urls) if all_image_urls else None
        
        # Insert blog post into database
        blog_data = {
            'title': title,
            'author': author,
            'email': email,
            'category': category,
            'content': content,
            'image_url': image_url,  # Now contains all URLs comma-separated
            'user_id': user_id,
            'status': 'pending',  # Requires admin approval
            'is_archived': False,
            'is_deleted': False
        }
        
        result = supabase.table('blogs').insert(blog_data).execute()
        
        flash('Thank you! Your blog post has been submitted for review.', 'success')
    except Exception as e:
        flash('An error occurred while submitting your blog post. Please try again.', 'error')
    
    return redirect(url_for('blog'))

# ============================================
# USER AUTHENTICATION (SUPABASE AUTH)
# ============================================

def get_current_user():
    """Get current user from session (synced with Supabase Auth)"""
    if session.get('user_id'):
        return {
            'id': session.get('user_id'),
            'email': session.get('user_email'),
            'name': session.get('user_name'),
            'is_verified': session.get('user_verified', False)
        }
    return None

@app.route('/signup', methods=['GET', 'POST'])
def user_signup():
    if request.method == 'POST':
        if not supabase:
            flash('Database unavailable. Please try again later.', 'error')
            return redirect(url_for('user_signup'))
        
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Validation
        if not all([name, email, password, confirm_password]):
            flash('All fields are required.', 'error')
            return redirect(url_for('user_signup'))
        
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('user_signup'))
        
        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return redirect(url_for('user_signup'))
        
        try:
            # Sign up with Supabase Auth
            # This will automatically send verification email
            auth_response = supabase.auth.sign_up({
                'email': email,
                'password': password,
                'options': {
                    'data': {
                        'name': name
                    }
                }
            })
            
            if auth_response.user:
                # Also store user in our users table for additional data
                user_data = {
                    'id': auth_response.user.id,  # Use Supabase Auth user id
                    'name': name,
                    'email': email,
                    'is_verified': False  # Will be updated when email is confirmed
                }
                
                try:
                    supabase.table('users').insert(user_data).execute()
                except Exception as e:
                    print(f"Note: Could not create user profile: {e}")
                
                flash('Account created! Please check your email to verify your account.', 'success')
                return redirect(url_for('user_login'))
            else:
                flash('An error occurred during signup. Please try again.', 'error')
            
        except Exception as e:
            error_msg = str(e)
            print(f"Signup error: {error_msg}")
            
            if 'already registered' in error_msg.lower() or 'already exists' in error_msg.lower():
                flash('An account with this email already exists.', 'error')
            elif 'invalid email' in error_msg.lower():
                flash('Please enter a valid email address.', 'error')
            elif 'password' in error_msg.lower():
                flash('Password must be at least 6 characters.', 'error')
            else:
                flash('An error occurred. Please try again.', 'error')
    
    return render_template('auth/signup.html')

@app.route('/login', methods=['GET', 'POST'])
def user_login():
    if request.method == 'POST':
        if not supabase:
            flash('Database unavailable. Please try again later.', 'error')
            return redirect(url_for('user_login'))
        
        email = request.form.get('email')
        password = request.form.get('password')
        
        try:
            # Sign in with Supabase Auth
            auth_response = supabase.auth.sign_in_with_password({
                'email': email,
                'password': password
            })
            
            if auth_response.user:
                user = auth_response.user
                
                # Check if email is verified
                is_verified = user.email_confirmed_at is not None
                
                # Get user name from user metadata or users table
                user_name = user.user_metadata.get('name', '')
                
                if not user_name:
                    # Try to get from users table
                    try:
                        user_result = supabase.table('users').select('name').eq('id', user.id).execute()
                        if user_result.data:
                            user_name = user_result.data[0].get('name', '')
                    except:
                        pass
                
                # Update users table verification status
                try:
                    supabase.table('users').update({
                        'is_verified': is_verified
                    }).eq('id', user.id).execute()
                except:
                    pass
                
                # Store in session
                session['user_id'] = user.id
                session['user_name'] = user_name or email.split('@')[0]
                session['user_email'] = user.email
                session['user_verified'] = is_verified
                session['access_token'] = auth_response.session.access_token
                session['refresh_token'] = auth_response.session.refresh_token
                
                flash(f'Welcome back, {session["user_name"]}!', 'success')
                
                # Redirect to verification page if not verified
                if not is_verified:
                    return redirect(url_for('verification_pending'))
                
                return redirect(url_for('blog'))
            
        except Exception as e:
            error_msg = str(e)
            print(f"Login error: {error_msg}")
            
            if 'invalid login' in error_msg.lower() or 'invalid credentials' in error_msg.lower():
                flash('Invalid email or password.', 'error')
            elif 'email not confirmed' in error_msg.lower():
                flash('Please verify your email before logging in.', 'error')
            else:
                flash('Invalid email or password.', 'error')
    
    return render_template('auth/login.html')

@app.route('/logout')
def user_logout():
    try:
        if supabase and session.get('access_token'):
            supabase.auth.sign_out()
    except Exception as e:
        print(f"Logout error: {e}")
    
    # Clear session
    session.pop('user_id', None)
    session.pop('user_name', None)
    session.pop('user_email', None)
    session.pop('user_verified', None)
    session.pop('access_token', None)
    session.pop('refresh_token', None)
    
    flash('You have been logged out.', 'success')
    return redirect(url_for('index'))

@app.route('/auth/callback')
def auth_callback():
    """Handle Supabase Auth callback (for email verification)"""
    if not supabase:
        flash('Database unavailable.', 'error')
        return redirect(url_for('index'))
    
    # Get tokens from URL fragment (Supabase sends these as hash params)
    # For email confirmation, Supabase redirects with access_token
    access_token = request.args.get('access_token')
    refresh_token = request.args.get('refresh_token')
    token_type = request.args.get('type')
    
    if token_type == 'signup' or token_type == 'email_confirmation':
        try:
            # Get user info from the token
            if access_token:
                user = supabase.auth.get_user(access_token)
                if user and user.user:
                    # Update verification status in users table
                    supabase.table('users').update({
                        'is_verified': True
                    }).eq('id', user.user.id).execute()
                    
                    flash('Email verified successfully! You can now login and create blog posts.', 'success')
                    return redirect(url_for('user_login'))
        except Exception as e:
            print(f"Auth callback error: {e}")
    
    # Default: just redirect to login
    flash('Email verified successfully! Please login to continue.', 'success')
    return redirect(url_for('user_login'))

@app.route('/verification-pending')
@login_required
def verification_pending():
    return render_template('auth/verification-pending.html')

@app.route('/resend-verification', methods=['POST'])
@login_required
def resend_verification():
    if not supabase:
        flash('Database unavailable.', 'error')
        return redirect(url_for('verification_pending'))
    
    try:
        email = session.get('user_email')
        if email:
            # Resend verification email using Supabase Auth
            supabase.auth.resend({
                'type': 'signup',
                'email': email
            })
            flash('Verification email sent! Please check your inbox.', 'success')
        else:
            flash('Could not resend verification email.', 'error')
            
    except Exception as e:
        print(f"Resend verification error: {e}")
        flash('An error occurred. Please try again.', 'error')
    
    return redirect(url_for('verification_pending'))

@app.route('/my-blogs')
@login_required
def my_blogs():
    blogs = []
    if supabase:
        try:
            user_id = session.get('user_id')
            result = supabase.table('blogs').select('*').eq('user_id', user_id).eq('is_deleted', False).order('created_at', desc=True).execute()
            blogs = result.data if result.data else []
        except Exception as e:
            print(f"Error fetching user blogs: {e}")
    
    return render_template('auth/my-blogs.html', blogs=blogs)

@app.route('/my-blogs/edit/<blog_id>', methods=['GET', 'POST'])
@login_required
def edit_my_blog(blog_id):
    if not supabase:
        flash('Database unavailable.', 'error')
        return redirect(url_for('my_blogs'))
    
    try:
        # Get blog and verify ownership
        result = supabase.table('blogs').select('*').eq('id', blog_id).execute()
        
        if not result.data:
            flash('Blog not found.', 'error')
            return redirect(url_for('my_blogs'))
        
        blog = result.data[0]
        
        # Check ownership
        if blog['user_id'] != session.get('user_id'):
            flash('You can only edit your own blogs.', 'error')
            return redirect(url_for('my_blogs'))
        
        # Can only edit pending blogs
        if blog['status'] == 'approved':
            flash('You cannot edit an approved blog.', 'error')
            return redirect(url_for('my_blogs'))
        
        if request.method == 'POST':
            title = request.form.get('title')
            category = request.form.get('category')
            content = request.form.get('content')
            
            update_data = {
                'title': title,
                'category': category,
                'content': content,
                'status': 'pending'  # Reset to pending after edit
            }
            
            supabase.table('blogs').update(update_data).eq('id', blog_id).execute()
            flash('Blog updated and resubmitted for review.', 'success')
            return redirect(url_for('my_blogs'))
        
        return render_template('auth/edit-blog.html', blog=blog)
        
    except Exception as e:
        print(f"Error editing blog: {e}")
        flash('An error occurred.', 'error')
        return redirect(url_for('my_blogs'))

@app.route('/my-blogs/delete/<blog_id>', methods=['POST'])
@login_required
def delete_my_blog(blog_id):
    if not supabase:
        flash('Database unavailable.', 'error')
        return redirect(url_for('my_blogs'))
    
    try:
        # Get blog and verify ownership
        result = supabase.table('blogs').select('*').eq('id', blog_id).execute()
        
        if not result.data:
            flash('Blog not found.', 'error')
            return redirect(url_for('my_blogs'))
        
        blog = result.data[0]
        
        # Check ownership
        if blog['user_id'] != session.get('user_id'):
            flash('You can only delete your own blogs.', 'error')
            return redirect(url_for('my_blogs'))
        
        # Soft delete
        supabase.table('blogs').update({
            'is_deleted': True,
            'deleted_at': datetime.now().isoformat()
        }).eq('id', blog_id).execute()
        
        flash('Blog deleted.', 'success')
        
    except Exception as e:
        print(f"Error deleting blog: {e}")
        flash('An error occurred.', 'error')
    
    return redirect(url_for('my_blogs'))

# ============================================
# FOOTER PAGES
# ============================================

@app.route('/contact')
def contact():
    return render_template('footer/contact.html')

@app.route('/tourism-info')
def tourism_info():
    return render_template('footer/tourism-info.html')

@app.route('/privacy')
def privacy():
    return render_template('footer/privacy.html')

@app.route('/cookie-policy')
def cookie():
    return render_template('footer/cookie.html')

@app.route('/terms')
def terms():
    return render_template('footer/terms.html')

# ============================================
# FORM SUBMISSIONS
# ============================================

@app.route('/contact/submit', methods=['POST'])
def submit_contact():
    # Handle contact form submission
    name = request.form.get('name')
    email = request.form.get('email')
    subject = request.form.get('subject')
    message = request.form.get('message')

    # Here you would typically save to database or send email
    flash('Thank you for contacting us! We will get back to you soon.', 'success')
    return redirect(url_for('contact'))

@app.route('/newsletter/subscribe', methods=['POST'])
def newsletter_subscribe():
    # Handle newsletter subscription
    email = request.form.get('email')

    # Here you would typically save to database
    flash('Successfully subscribed to our newsletter!', 'success')
    return redirect(request.referrer or url_for('index'))

# ============================================
# ERROR HANDLERS
# ============================================

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500

# ============================================
# ADMIN AUTHENTICATION
# ============================================

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if session.get('admin_logged_in'):
        return redirect(url_for('admin_dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if supabase:
            try:
                response = supabase.table('admins').select('*').eq('username', username).execute()
                if response.data:
                    admin = response.data[0]
                    # Simple password check (in production, use proper hashing!)
                    if admin['password_hash'] == password:
                        session['admin_logged_in'] = True
                        session['admin_username'] = username
                        flash('Welcome back!', 'success')
                        return redirect(url_for('admin_dashboard'))
                flash('Invalid username or password.', 'error')
            except Exception as e:
                print(f"Login error: {e}")
                flash('Login failed. Please try again.', 'error')
        else:
            flash('Database connection unavailable.', 'error')
    
    return render_template('admin/login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    session.pop('admin_username', None)
    flash('You have been logged out.', 'success')
    return redirect(url_for('admin_login'))

# ============================================
# ADMIN DASHBOARD
# ============================================

@app.route('/admin')
@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    stats = get_stats()
    recent_blogs = []
    
    if supabase:
        try:
            response = supabase.table('blogs').select('*').order('created_at', desc=True).limit(10).execute()
            recent_blogs = response.data or []
        except Exception as e:
            print(f"Error fetching recent blogs: {e}")
    
    return render_template('admin/dashboard.html', 
                          stats=stats, 
                          recent_blogs=recent_blogs,
                          pending_blogs=stats['pending_blogs'],
                          pending_reviews=0,
                          pending_reports=stats['reports'])

# ============================================
# ADMIN - BLOGS MANAGEMENT
# ============================================

@app.route('/admin/blogs')
@admin_required
def admin_blogs():
    blogs = []
    filter_status = request.args.get('filter', 'all')
    
    if supabase:
        try:
            # Only show non-deleted, non-archived blogs
            query = supabase.table('blogs').select('*').eq('is_deleted', False).eq('is_archived', False).order('created_at', desc=True)
            if filter_status != 'all':
                query = query.eq('status', filter_status)
            response = query.execute()
            blogs = response.data or []
        except Exception as e:
            print(f"Error fetching blogs: {e}")
    
    return render_template('admin/blogs.html', blogs=blogs, filter_status=filter_status)

@app.route('/admin/blogs/archive')
@admin_required
def admin_blogs_archive():
    """View archived blogs (previously approved then deleted)"""
    blogs = []
    if supabase:
        try:
            response = supabase.table('blogs').select('*').eq('is_archived', True).order('deleted_at', desc=True).execute()
            blogs = response.data or []
        except Exception as e:
            print(f"Error fetching archived blogs: {e}")
    
    return render_template('admin/blogs-archive.html', blogs=blogs)

@app.route('/admin/blogs/bin')
@admin_required
def admin_blogs_bin():
    """View deleted blogs (non-approved, will be cleared after 30 days)"""
    blogs = []
    if supabase:
        try:
            response = supabase.table('blogs').select('*').eq('is_deleted', True).eq('is_archived', False).order('deleted_at', desc=True).execute()
            blogs = response.data or []
            
            # Calculate days remaining for each blog
            for blog in blogs:
                if blog.get('deleted_at'):
                    deleted_date = datetime.fromisoformat(blog['deleted_at'].replace('Z', '+00:00'))
                    days_passed = (datetime.now(deleted_date.tzinfo) - deleted_date).days
                    blog['days_remaining'] = max(0, 30 - days_passed)
                else:
                    blog['days_remaining'] = 30
                    
        except Exception as e:
            print(f"Error fetching bin blogs: {e}")
    
    return render_template('admin/blogs-bin.html', blogs=blogs)

@app.route('/admin/blogs/<blog_id>/approve')
@admin_required
def admin_blog_approve(blog_id):
    if supabase:
        try:
            supabase.table('blogs').update({
                'status': 'approved',
                'approved_at': datetime.now().isoformat()
            }).eq('id', blog_id).execute()
            flash('Blog post approved!', 'success')
        except Exception as e:
            print(f"Error approving blog: {e}")
            flash('Failed to approve blog post.', 'error')
    return redirect(url_for('admin_blogs'))

@app.route('/admin/blogs/<blog_id>/reject')
@admin_required
def admin_blog_reject(blog_id):
    if supabase:
        try:
            supabase.table('blogs').update({
                'status': 'rejected'
            }).eq('id', blog_id).execute()
            flash('Blog post rejected.', 'success')
        except Exception as e:
            print(f"Error rejecting blog: {e}")
            flash('Failed to reject blog post.', 'error')
    return redirect(url_for('admin_blogs'))

@app.route('/admin/blogs/<blog_id>/delete')
@admin_required
def admin_blog_delete(blog_id):
    """Delete a blog - archive if approved, bin if not approved"""
    if supabase:
        try:
            # Get blog to check status
            result = supabase.table('blogs').select('status, approved_at').eq('id', blog_id).execute()
            
            if result.data:
                blog = result.data[0]
                
                if blog.get('status') == 'approved' or blog.get('approved_at'):
                    # Was approved - move to archive
                    supabase.table('blogs').update({
                        'is_archived': True,
                        'is_deleted': False,
                        'deleted_at': datetime.now().isoformat()
                    }).eq('id', blog_id).execute()
                    flash('Approved blog moved to archive.', 'success')
                else:
                    # Not approved - move to bin (30 day delete)
                    supabase.table('blogs').update({
                        'is_deleted': True,
                        'is_archived': False,
                        'deleted_at': datetime.now().isoformat()
                    }).eq('id', blog_id).execute()
                    flash('Blog moved to bin. It will be permanently deleted in 30 days.', 'success')
            
        except Exception as e:
            print(f"Error deleting blog: {e}")
            flash('Failed to delete blog post.', 'error')
    return redirect(url_for('admin_blogs'))

@app.route('/admin/blogs/<blog_id>/restore')
@admin_required
def admin_blog_restore(blog_id):
    """Restore a blog from archive or bin"""
    if supabase:
        try:
            supabase.table('blogs').update({
                'is_archived': False,
                'is_deleted': False,
                'deleted_at': None
            }).eq('id', blog_id).execute()
            flash('Blog restored successfully!', 'success')
        except Exception as e:
            print(f"Error restoring blog: {e}")
            flash('Failed to restore blog.', 'error')
    
    return redirect(request.referrer or url_for('admin_blogs'))

@app.route('/admin/blogs/<blog_id>/permanent-delete', methods=['POST'])
@admin_required
def admin_blog_permanent_delete(blog_id):
    """Permanently delete a blog from bin"""
    if supabase:
        try:
            supabase.table('blogs').delete().eq('id', blog_id).execute()
            flash('Blog permanently deleted.', 'success')
        except Exception as e:
            print(f"Error permanently deleting blog: {e}")
            flash('Failed to delete blog.', 'error')
    
    return redirect(url_for('admin_blogs_bin'))

@app.route('/admin/blogs/cleanup-bin')
@admin_required
def admin_cleanup_bin():
    """Clean up blogs older than 30 days in the bin"""
    if supabase:
        try:
            cutoff_date = (datetime.now() - timedelta(days=30)).isoformat()
            result = supabase.table('blogs').delete().eq('is_deleted', True).lt('deleted_at', cutoff_date).execute()
            flash(f'Cleaned up old blogs from bin.', 'success')
        except Exception as e:
            print(f"Error cleaning bin: {e}")
            flash('Failed to clean bin.', 'error')
    
    return redirect(url_for('admin_blogs_bin'))

# ============================================
# ADMIN - ATTRACTIONS MANAGEMENT
# ============================================

@app.route('/admin/attractions')
@admin_required
def admin_attractions():
    attractions = []
    if supabase:
        try:
            response = supabase.table('attractions').select('*').order('created_at', desc=True).execute()
            attractions = response.data or []
        except Exception as e:
            print(f"Error fetching attractions: {e}")
    
    return render_template('admin/attractions.html', attractions=attractions)

@app.route('/admin/attractions/add', methods=['GET', 'POST'])
@admin_required
def admin_attractions_add():
    if request.method == 'POST':
        if supabase:
            try:
                name = request.form.get('name')
                image_url = None
                
                # Handle image upload
                if 'image' in request.files:
                    file = request.files['image']
                    if file and file.filename:
                        file_ext = file.filename.rsplit('.', 1)[-1].lower()
                        unique_filename = f"attractions/{uuid.uuid4()}.{file_ext}"
                        file_bytes = file.read()
                        supabase.storage.from_('blog-images').upload(
                            unique_filename, file_bytes,
                            {'content-type': file.content_type}
                        )
                        image_url = f"{SUPABASE_URL}/storage/v1/object/public/blog-images/{unique_filename}"
                
                attraction_data = {
                    'name': name,
                    'slug': generate_slug(name),
                    'category': request.form.get('category'),
                    'description': request.form.get('description'),
                    'full_description': request.form.get('full_description'),
                    'location': request.form.get('location'),
                    'image_url': image_url,
                    'entrance_fee': request.form.get('entrance_fee'),
                    'hours': request.form.get('hours'),
                    'best_time': request.form.get('best_time'),
                    'duration': request.form.get('duration'),
                    'difficulty': request.form.get('difficulty'),
                    'contact': request.form.get('contact'),
                    'map_embed': request.form.get('map_embed'),
                    'is_active': True
                }
                
                supabase.table('attractions').insert(attraction_data).execute()
                flash('Attraction added successfully!', 'success')
                return redirect(url_for('admin_attractions'))
            except Exception as e:
                print(f"Error adding attraction: {e}")
                flash('Failed to add attraction.', 'error')
    
    return render_template('admin/attraction-form.html', attraction=None)

@app.route('/admin/attractions/<int:attraction_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_attractions_edit(attraction_id):
    if request.method == 'POST':
        if supabase:
            try:
                update_data = {
                    'name': request.form.get('name'),
                    'category': request.form.get('category'),
                    'description': request.form.get('description'),
                    'full_description': request.form.get('full_description'),
                    'location': request.form.get('location'),
                    'entrance_fee': request.form.get('entrance_fee'),
                    'hours': request.form.get('hours'),
                    'best_time': request.form.get('best_time'),
                    'duration': request.form.get('duration'),
                    'difficulty': request.form.get('difficulty'),
                    'contact': request.form.get('contact'),
                    'map_embed': request.form.get('map_embed'),
                    'is_active': request.form.get('is_active') == 'on',
                    'updated_at': datetime.now().isoformat()
                }
                
                # Handle new image upload
                if 'image' in request.files:
                    file = request.files['image']
                    if file and file.filename:
                        file_ext = file.filename.rsplit('.', 1)[-1].lower()
                        unique_filename = f"attractions/{uuid.uuid4()}.{file_ext}"
                        file_bytes = file.read()
                        supabase.storage.from_('blog-images').upload(
                            unique_filename, file_bytes,
                            {'content-type': file.content_type}
                        )
                        update_data['image_url'] = f"{SUPABASE_URL}/storage/v1/object/public/blog-images/{unique_filename}"
                
                supabase.table('attractions').update(update_data).eq('id', attraction_id).execute()
                flash('Attraction updated successfully!', 'success')
                return redirect(url_for('admin_attractions'))
            except Exception as e:
                print(f"Error updating attraction: {e}")
                flash('Failed to update attraction.', 'error')
    
    attraction = None
    if supabase:
        try:
            response = supabase.table('attractions').select('*').eq('id', attraction_id).single().execute()
            attraction = response.data
        except:
            flash('Attraction not found.', 'error')
            return redirect(url_for('admin_attractions'))
    
    return render_template('admin/attraction-form.html', attraction=attraction)

@app.route('/admin/attractions/<int:attraction_id>/delete')
@admin_required
def admin_attractions_delete(attraction_id):
    if supabase:
        try:
            supabase.table('attractions').delete().eq('id', attraction_id).execute()
            flash('Attraction deleted.', 'success')
        except Exception as e:
            print(f"Error deleting attraction: {e}")
            flash('Failed to delete attraction.', 'error')
    return redirect(url_for('admin_attractions'))

# ============================================
# ADMIN - PRODUCTS MANAGEMENT
# ============================================

@app.route('/admin/products')
@admin_required
def admin_products():
    products = []
    if supabase:
        try:
            response = supabase.table('products').select('*').order('created_at', desc=True).execute()
            products = response.data or []
        except Exception as e:
            print(f"Error fetching products: {e}")
    
    return render_template('admin/products.html', products=products)

@app.route('/admin/products/add', methods=['GET', 'POST'])
@admin_required
def admin_products_add():
    if request.method == 'POST':
        if supabase:
            try:
                name = request.form.get('name')
                image_url = None
                
                if 'image' in request.files:
                    file = request.files['image']
                    if file and file.filename:
                        file_ext = file.filename.rsplit('.', 1)[-1].lower()
                        unique_filename = f"products/{uuid.uuid4()}.{file_ext}"
                        file_bytes = file.read()
                        supabase.storage.from_('blog-images').upload(
                            unique_filename, file_bytes,
                            {'content-type': file.content_type}
                        )
                        image_url = f"{SUPABASE_URL}/storage/v1/object/public/blog-images/{unique_filename}"
                
                product_data = {
                    'name': name,
                    'slug': generate_slug(name),
                    'category': request.form.get('category'),
                    'description': request.form.get('description'),
                    'full_description': request.form.get('full_description'),
                    'price_range': request.form.get('price_range'),
                    'image_url': image_url,
                    'making_process': request.form.get('making_process'),
                    'is_active': True
                }
                
                supabase.table('products').insert(product_data).execute()
                flash('Product added successfully!', 'success')
                return redirect(url_for('admin_products'))
            except Exception as e:
                print(f"Error adding product: {e}")
                flash('Failed to add product.', 'error')
    
    return render_template('admin/product-form.html', product=None)

@app.route('/admin/products/<int:product_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_products_edit(product_id):
    if request.method == 'POST':
        if supabase:
            try:
                update_data = {
                    'name': request.form.get('name'),
                    'category': request.form.get('category'),
                    'description': request.form.get('description'),
                    'full_description': request.form.get('full_description'),
                    'price_range': request.form.get('price_range'),
                    'making_process': request.form.get('making_process'),
                    'is_active': request.form.get('is_active') == 'on',
                    'updated_at': datetime.now().isoformat()
                }
                
                if 'image' in request.files:
                    file = request.files['image']
                    if file and file.filename:
                        file_ext = file.filename.rsplit('.', 1)[-1].lower()
                        unique_filename = f"products/{uuid.uuid4()}.{file_ext}"
                        file_bytes = file.read()
                        supabase.storage.from_('blog-images').upload(
                            unique_filename, file_bytes,
                            {'content-type': file.content_type}
                        )
                        update_data['image_url'] = f"{SUPABASE_URL}/storage/v1/object/public/blog-images/{unique_filename}"
                
                supabase.table('products').update(update_data).eq('id', product_id).execute()
                flash('Product updated successfully!', 'success')
                return redirect(url_for('admin_products'))
            except Exception as e:
                print(f"Error updating product: {e}")
                flash('Failed to update product.', 'error')
    
    product = None
    if supabase:
        try:
            response = supabase.table('products').select('*').eq('id', product_id).single().execute()
            product = response.data
        except:
            flash('Product not found.', 'error')
            return redirect(url_for('admin_products'))
    
    return render_template('admin/product-form.html', product=product)

@app.route('/admin/products/<int:product_id>/delete')
@admin_required
def admin_products_delete(product_id):
    if supabase:
        try:
            supabase.table('products').delete().eq('id', product_id).execute()
            flash('Product deleted.', 'success')
        except Exception as e:
            print(f"Error deleting product: {e}")
            flash('Failed to delete product.', 'error')
    return redirect(url_for('admin_products'))

# ============================================
# ADMIN - EVENTS MANAGEMENT
# ============================================

@app.route('/admin/events')
@admin_required
def admin_events():
    events = []
    if supabase:
        try:
            response = supabase.table('events').select('*').order('event_date', desc=True).execute()
            events = response.data or []
        except Exception as e:
            print(f"Error fetching events: {e}")
    
    return render_template('admin/events.html', events=events)

@app.route('/admin/events/add', methods=['GET', 'POST'])
@admin_required
def admin_events_add():
    if request.method == 'POST':
        if supabase:
            try:
                title = request.form.get('title')
                image_url = None
                
                if 'image' in request.files:
                    file = request.files['image']
                    if file and file.filename:
                        file_ext = file.filename.rsplit('.', 1)[-1].lower()
                        unique_filename = f"events/{uuid.uuid4()}.{file_ext}"
                        file_bytes = file.read()
                        supabase.storage.from_('blog-images').upload(
                            unique_filename, file_bytes,
                            {'content-type': file.content_type}
                        )
                        image_url = f"{SUPABASE_URL}/storage/v1/object/public/blog-images/{unique_filename}"
                
                event_data = {
                    'title': title,
                    'slug': generate_slug(title),
                    'description': request.form.get('description'),
                    'full_description': request.form.get('full_description'),
                    'event_date': request.form.get('event_date'),
                    'end_date': request.form.get('end_date') or None,
                    'start_time': request.form.get('start_time') or None,
                    'end_time': request.form.get('end_time') or None,
                    'location': request.form.get('location'),
                    'category': request.form.get('category'),
                    'image_url': image_url,
                    'is_featured': request.form.get('is_featured') == 'on',
                    'is_active': True
                }
                
                supabase.table('events').insert(event_data).execute()
                flash('Event added successfully!', 'success')
                return redirect(url_for('admin_events'))
            except Exception as e:
                print(f"Error adding event: {e}")
                flash('Failed to add event.', 'error')
    
    return render_template('admin/event-form.html', event=None)

@app.route('/admin/events/<int:event_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_events_edit(event_id):
    if request.method == 'POST':
        if supabase:
            try:
                update_data = {
                    'title': request.form.get('title'),
                    'description': request.form.get('description'),
                    'full_description': request.form.get('full_description'),
                    'event_date': request.form.get('event_date'),
                    'end_date': request.form.get('end_date') or None,
                    'start_time': request.form.get('start_time') or None,
                    'end_time': request.form.get('end_time') or None,
                    'location': request.form.get('location'),
                    'category': request.form.get('category'),
                    'is_featured': request.form.get('is_featured') == 'on',
                    'is_active': request.form.get('is_active') == 'on',
                    'updated_at': datetime.now().isoformat()
                }
                
                if 'image' in request.files:
                    file = request.files['image']
                    if file and file.filename:
                        file_ext = file.filename.rsplit('.', 1)[-1].lower()
                        unique_filename = f"events/{uuid.uuid4()}.{file_ext}"
                        file_bytes = file.read()
                        supabase.storage.from_('blog-images').upload(
                            unique_filename, file_bytes,
                            {'content-type': file.content_type}
                        )
                        update_data['image_url'] = f"{SUPABASE_URL}/storage/v1/object/public/blog-images/{unique_filename}"
                
                supabase.table('events').update(update_data).eq('id', event_id).execute()
                flash('Event updated successfully!', 'success')
                return redirect(url_for('admin_events'))
            except Exception as e:
                print(f"Error updating event: {e}")
                flash('Failed to update event.', 'error')
    
    event = None
    if supabase:
        try:
            response = supabase.table('events').select('*').eq('id', event_id).single().execute()
            event = response.data
        except:
            flash('Event not found.', 'error')
            return redirect(url_for('admin_events'))
    
    return render_template('admin/event-form.html', event=event)

@app.route('/admin/events/<int:event_id>/delete')
@admin_required
def admin_events_delete(event_id):
    if supabase:
        try:
            supabase.table('events').delete().eq('id', event_id).execute()
            flash('Event deleted.', 'success')
        except Exception as e:
            print(f"Error deleting event: {e}")
            flash('Failed to delete event.', 'error')
    return redirect(url_for('admin_events'))

# ============================================
# ADMIN - HOTELS MANAGEMENT
# ============================================

@app.route('/admin/hotels')
@admin_required
def admin_hotels():
    hotels = []
    if supabase:
        try:
            response = supabase.table('hotels').select('*').order('created_at', desc=True).execute()
            hotels = response.data or []
        except Exception as e:
            print(f"Error fetching hotels: {e}")
    
    return render_template('admin/hotels.html', hotels=hotels)

@app.route('/admin/hotels/add', methods=['GET', 'POST'])
@admin_required
def admin_hotels_add():
    if request.method == 'POST':
        if supabase:
            try:
                name = request.form.get('name')
                image_url = None
                
                if 'image' in request.files:
                    file = request.files['image']
                    if file and file.filename:
                        file_ext = file.filename.rsplit('.', 1)[-1].lower()
                        unique_filename = f"hotels/{uuid.uuid4()}.{file_ext}"
                        file_bytes = file.read()
                        supabase.storage.from_('blog-images').upload(
                            unique_filename, file_bytes,
                            {'content-type': file.content_type}
                        )
                        image_url = f"{SUPABASE_URL}/storage/v1/object/public/blog-images/{unique_filename}"
                
                hotel_data = {
                    'name': name,
                    'slug': generate_slug(name),
                    'description': request.form.get('description'),
                    'address': request.form.get('address'),
                    'phone': request.form.get('phone'),
                    'email': request.form.get('email'),
                    'price_range': request.form.get('price_range'),
                    'image_url': image_url,
                    'map_embed': request.form.get('map_embed'),
                    'is_active': True
                }
                
                supabase.table('hotels').insert(hotel_data).execute()
                flash('Hotel added successfully!', 'success')
                return redirect(url_for('admin_hotels'))
            except Exception as e:
                print(f"Error adding hotel: {e}")
                flash('Failed to add hotel.', 'error')
    
    return render_template('admin/hotel-form.html', hotel=None)

@app.route('/admin/hotels/<int:hotel_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_hotels_edit(hotel_id):
    if request.method == 'POST':
        if supabase:
            try:
                update_data = {
                    'name': request.form.get('name'),
                    'description': request.form.get('description'),
                    'address': request.form.get('address'),
                    'phone': request.form.get('phone'),
                    'email': request.form.get('email'),
                    'price_range': request.form.get('price_range'),
                    'map_embed': request.form.get('map_embed'),
                    'is_active': request.form.get('is_active') == 'on',
                    'updated_at': datetime.now().isoformat()
                }
                
                if 'image' in request.files:
                    file = request.files['image']
                    if file and file.filename:
                        file_ext = file.filename.rsplit('.', 1)[-1].lower()
                        unique_filename = f"hotels/{uuid.uuid4()}.{file_ext}"
                        file_bytes = file.read()
                        supabase.storage.from_('blog-images').upload(
                            unique_filename, file_bytes,
                            {'content-type': file.content_type}
                        )
                        update_data['image_url'] = f"{SUPABASE_URL}/storage/v1/object/public/blog-images/{unique_filename}"
                
                supabase.table('hotels').update(update_data).eq('id', hotel_id).execute()
                flash('Hotel updated successfully!', 'success')
                return redirect(url_for('admin_hotels'))
            except Exception as e:
                print(f"Error updating hotel: {e}")
                flash('Failed to update hotel.', 'error')
    
    hotel = None
    if supabase:
        try:
            response = supabase.table('hotels').select('*').eq('id', hotel_id).single().execute()
            hotel = response.data
        except:
            flash('Hotel not found.', 'error')
            return redirect(url_for('admin_hotels'))
    
    return render_template('admin/hotel-form.html', hotel=hotel)

@app.route('/admin/hotels/<int:hotel_id>/delete')
@admin_required
def admin_hotels_delete(hotel_id):
    if supabase:
        try:
            supabase.table('hotels').delete().eq('id', hotel_id).execute()
            flash('Hotel deleted.', 'success')
        except Exception as e:
            print(f"Error deleting hotel: {e}")
            flash('Failed to delete hotel.', 'error')
    return redirect(url_for('admin_hotels'))

# ============================================
# ADMIN - RESTAURANTS MANAGEMENT
# ============================================

@app.route('/admin/restaurants')
@admin_required
def admin_restaurants():
    restaurants = []
    if supabase:
        try:
            response = supabase.table('restaurants').select('*').order('created_at', desc=True).execute()
            restaurants = response.data or []
        except Exception as e:
            print(f"Error fetching restaurants: {e}")
    
    return render_template('admin/restaurants.html', restaurants=restaurants)

@app.route('/admin/restaurants/add', methods=['GET', 'POST'])
@admin_required
def admin_restaurants_add():
    if request.method == 'POST':
        if supabase:
            try:
                name = request.form.get('name')
                image_url = None
                
                if 'image' in request.files:
                    file = request.files['image']
                    if file and file.filename:
                        file_ext = file.filename.rsplit('.', 1)[-1].lower()
                        unique_filename = f"restaurants/{uuid.uuid4()}.{file_ext}"
                        file_bytes = file.read()
                        supabase.storage.from_('blog-images').upload(
                            unique_filename, file_bytes,
                            {'content-type': file.content_type}
                        )
                        image_url = f"{SUPABASE_URL}/storage/v1/object/public/blog-images/{unique_filename}"
                
                resto_data = {
                    'name': name,
                    'slug': generate_slug(name),
                    'description': request.form.get('description'),
                    'cuisine': request.form.get('cuisine'),
                    'address': request.form.get('address'),
                    'phone': request.form.get('phone'),
                    'price_range': request.form.get('price_range'),
                    'hours': request.form.get('hours'),
                    'image_url': image_url,
                    'map_embed': request.form.get('map_embed'),
                    'is_active': True
                }
                
                supabase.table('restaurants').insert(resto_data).execute()
                flash('Restaurant added successfully!', 'success')
                return redirect(url_for('admin_restaurants'))
            except Exception as e:
                print(f"Error adding restaurant: {e}")
                flash('Failed to add restaurant.', 'error')
    
    return render_template('admin/restaurant-form.html', restaurant=None)

@app.route('/admin/restaurants/<int:resto_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_restaurants_edit(resto_id):
    if request.method == 'POST':
        if supabase:
            try:
                update_data = {
                    'name': request.form.get('name'),
                    'description': request.form.get('description'),
                    'cuisine': request.form.get('cuisine'),
                    'address': request.form.get('address'),
                    'phone': request.form.get('phone'),
                    'price_range': request.form.get('price_range'),
                    'hours': request.form.get('hours'),
                    'map_embed': request.form.get('map_embed'),
                    'is_active': request.form.get('is_active') == 'on',
                    'updated_at': datetime.now().isoformat()
                }
                
                if 'image' in request.files:
                    file = request.files['image']
                    if file and file.filename:
                        file_ext = file.filename.rsplit('.', 1)[-1].lower()
                        unique_filename = f"restaurants/{uuid.uuid4()}.{file_ext}"
                        file_bytes = file.read()
                        supabase.storage.from_('blog-images').upload(
                            unique_filename, file_bytes,
                            {'content-type': file.content_type}
                        )
                        update_data['image_url'] = f"{SUPABASE_URL}/storage/v1/object/public/blog-images/{unique_filename}"
                
                supabase.table('restaurants').update(update_data).eq('id', resto_id).execute()
                flash('Restaurant updated successfully!', 'success')
                return redirect(url_for('admin_restaurants'))
            except Exception as e:
                print(f"Error updating restaurant: {e}")
                flash('Failed to update restaurant.', 'error')
    
    restaurant = None
    if supabase:
        try:
            response = supabase.table('restaurants').select('*').eq('id', resto_id).single().execute()
            restaurant = response.data
        except:
            flash('Restaurant not found.', 'error')
            return redirect(url_for('admin_restaurants'))
    
    return render_template('admin/restaurant-form.html', restaurant=restaurant)

@app.route('/admin/restaurants/<int:resto_id>/delete')
@admin_required
def admin_restaurants_delete(resto_id):
    if supabase:
        try:
            supabase.table('restaurants').delete().eq('id', resto_id).execute()
            flash('Restaurant deleted.', 'success')
        except Exception as e:
            print(f"Error deleting restaurant: {e}")
            flash('Failed to delete restaurant.', 'error')
    return redirect(url_for('admin_restaurants'))

# ============================================
# ADMIN - REVIEWS MANAGEMENT
# ============================================

@app.route('/admin/reviews')
@admin_required
def admin_reviews():
    reviews = []
    if supabase:
        try:
            response = supabase.table('reviews').select('*').order('created_at', desc=True).execute()
            reviews = response.data or []
        except Exception as e:
            print(f"Error fetching reviews: {e}")
    
    return render_template('admin/reviews.html', reviews=reviews)

@app.route('/admin/reviews/<int:review_id>/approve')
@admin_required
def admin_review_approve(review_id):
    if supabase:
        try:
            supabase.table('reviews').update({'status': 'approved'}).eq('id', review_id).execute()
            flash('Review approved!', 'success')
        except Exception as e:
            print(f"Error approving review: {e}")
            flash('Failed to approve review.', 'error')
    return redirect(url_for('admin_reviews'))

@app.route('/admin/reviews/<int:review_id>/reject')
@admin_required
def admin_review_reject(review_id):
    if supabase:
        try:
            supabase.table('reviews').update({'status': 'rejected'}).eq('id', review_id).execute()
            flash('Review rejected.', 'success')
        except Exception as e:
            print(f"Error rejecting review: {e}")
            flash('Failed to reject review.', 'error')
    return redirect(url_for('admin_reviews'))

@app.route('/admin/reviews/<int:review_id>/delete')
@admin_required
def admin_review_delete(review_id):
    if supabase:
        try:
            supabase.table('reviews').delete().eq('id', review_id).execute()
            flash('Review deleted.', 'success')
        except Exception as e:
            print(f"Error deleting review: {e}")
            flash('Failed to delete review.', 'error')
    return redirect(url_for('admin_reviews'))

# ============================================
# ADMIN - REPORTS MANAGEMENT
# ============================================

@app.route('/admin/reports')
@admin_required
def admin_reports():
    reports = []
    if supabase:
        try:
            response = supabase.table('blog_reports').select('*, blogs(title, author)').order('created_at', desc=True).execute()
            reports = response.data or []
        except Exception as e:
            print(f"Error fetching reports: {e}")
    
    return render_template('admin/reports.html', reports=reports)

@app.route('/admin/reports/<int:report_id>/dismiss')
@admin_required
def admin_report_dismiss(report_id):
    if supabase:
        try:
            supabase.table('blog_reports').delete().eq('id', report_id).execute()
            flash('Report dismissed.', 'success')
        except Exception as e:
            print(f"Error dismissing report: {e}")
            flash('Failed to dismiss report.', 'error')
    return redirect(url_for('admin_reports'))

# ============================================
# BLOG VOTING & REPORTING (Public)
# ============================================

@app.route('/blog/<int:blog_id>/vote/<vote_type>')
def blog_vote(blog_id, vote_type):
    if vote_type not in ['up', 'down']:
        flash('Invalid vote type.', 'error')
        return redirect(url_for('blog'))
    
    if supabase:
        try:
            voter_ip = request.remote_addr
            
            # Check if already voted
            existing = supabase.table('blog_votes').select('*').eq('blog_id', blog_id).eq('voter_ip', voter_ip).execute()
            
            if existing.data:
                flash('You have already voted on this post.', 'info')
            else:
                supabase.table('blog_votes').insert({
                    'blog_id': blog_id,
                    'vote_type': vote_type,
                    'voter_ip': voter_ip
                }).execute()
                
                # Update vote count on blog
                blog = supabase.table('blogs').select('upvotes, downvotes').eq('id', blog_id).single().execute()
                if blog.data:
                    if vote_type == 'up':
                        supabase.table('blogs').update({'upvotes': (blog.data.get('upvotes') or 0) + 1}).eq('id', blog_id).execute()
                    else:
                        supabase.table('blogs').update({'downvotes': (blog.data.get('downvotes') or 0) + 1}).eq('id', blog_id).execute()
                
                flash('Thank you for your vote!', 'success')
        except Exception as e:
            print(f"Error voting: {e}")
            flash('Failed to submit vote.', 'error')
    
    return redirect(request.referrer or url_for('blog'))

@app.route('/blog/<int:blog_id>/report', methods=['POST'])
def blog_report(blog_id):
    if supabase:
        try:
            report_data = {
                'blog_id': blog_id,
                'reason': request.form.get('reason', 'other'),
                'description': request.form.get('description', ''),
                'reporter_ip': request.remote_addr
            }
            supabase.table('blog_reports').insert(report_data).execute()
            
            # Update report count
            blog = supabase.table('blogs').select('report_count').eq('id', blog_id).single().execute()
            if blog.data:
                supabase.table('blogs').update({
                    'is_reported': True,
                    'report_count': (blog.data.get('report_count') or 0) + 1
                }).eq('id', blog_id).execute()
            
            flash('Thank you for your report. We will review it shortly.', 'success')
        except Exception as e:
            print(f"Error reporting: {e}")
            flash('Failed to submit report.', 'error')
    
    return redirect(request.referrer or url_for('blog'))

# ============================================
# RUN APP
# ============================================

if __name__ == '__main__':
    app.run(debug=True)
