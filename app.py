from flask import Flask, render_template, redirect, url_for, request, flash, session, jsonify
from supabase import create_client, Client
from dotenv import load_dotenv
from functools import wraps
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
import re
import traceback
import json

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
SUPABASE_PRODUCT_BUCKET = os.getenv('SUPABASE_PRODUCT_BUCKET', 'product-images')

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


def upload_bytes_get_url_to_bucket(file_bytes: bytes, file_ext: str, content_type: str, bucket: str, prefix: str = '') -> str:
    """Upload raw bytes to the specified Supabase storage bucket and return a public URL.
    Uses the admin client (service role) when available; falls back to the public client or local storage.
    """
    unique_filename = f"{prefix}{uuid.uuid4()}.{file_ext}"
    # Try admin client first
    if supabase_admin:
        try:
            supabase_admin.storage.from_(bucket).upload(unique_filename, file_bytes, {'content-type': content_type})
            return supabase_admin.storage.from_(bucket).get_public_url(unique_filename)
        except Exception as sup_err:
            print(f"Supabase admin upload failed for {unique_filename}: {sup_err}")
    # Try public client
    try:
        if supabase:
            supabase.storage.from_(bucket).upload(unique_filename, file_bytes, {'content-type': content_type})
            return f"{SUPABASE_URL}/storage/v1/object/public/{bucket}/{unique_filename}"
    except Exception as pub_err:
        print(f"Supabase public upload failed for {unique_filename}: {pub_err}")
    # Fallback to local storage
    try:
        uploads_folder = Path(__file__).parent / 'static' / 'uploads'
        uploads_folder.mkdir(parents=True, exist_ok=True)
        file_path = uploads_folder / unique_filename
        file_path.write_bytes(file_bytes)
        return f"/static/uploads/{unique_filename}"
    except Exception as local_err:
        print(f"Failed to write file locally for {unique_filename}: {local_err}")
        return ''


def _log_hotel_error(label: str, exc: Exception = None, payload: dict = None):
    """Append detailed error information to logs/hotel_errors.log for debugging."""
    try:
        logs_dir = Path(__file__).parent / 'logs'
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_file = logs_dir / 'hotel_errors.log'
        with log_file.open('a', encoding='utf-8') as f:
            f.write(f"[{datetime.now().isoformat()}] {label}\n")
            if exc is not None:
                f.write('Exception:\n')
                f.write(traceback.format_exc())
                f.write('\n')
            if payload is not None:
                try:
                    f.write('Payload:\n')
                    f.write(json.dumps(payload, default=str, ensure_ascii=False, indent=2))
                    f.write('\n')
                except Exception as _j:
                    f.write(f'Failed to serialize payload: {_j}\n')
            f.write('\n')
    except Exception as _e:
        # fallback to console if file logging fails
        print('Failed to write hotel error log:', _e)

# Cache for product columns existence checks
_PRODUCT_COLUMNS_CACHE = {}

def product_column_exists(col_name: str) -> bool:
    """Check whether the `products` table has a column named `col_name`.
    Performs a cheap select and caches the result. Returns False if Supabase is not configured.
    """
    global _PRODUCT_COLUMNS_CACHE
    if not supabase:
        return False
    if col_name in _PRODUCT_COLUMNS_CACHE:
        return _PRODUCT_COLUMNS_CACHE[col_name]
    try:
        # Try selecting the column; if the column doesn't exist the request will error
        resp = supabase.table('products').select(col_name).limit(1).execute()
        # Some clients return a response object with .error when the column is missing
        if hasattr(resp, 'error') and resp.error:
            _PRODUCT_COLUMNS_CACHE[col_name] = False
            return False
        # If we reach here assume column exists
        _PRODUCT_COLUMNS_CACHE[col_name] = True
        return True
    except Exception as e:
        print(f"product_column_exists check failed for '{col_name}': {e}")
        _PRODUCT_COLUMNS_CACHE[col_name] = False
        return False

# Cache for events columns existence checks
_EVENT_COLUMNS_CACHE = {}

# Cache for hotels columns existence checks
_HOTEL_COLUMNS_CACHE = {}

# Cache for restaurants columns existence checks
_RESTAURANT_COLUMNS_CACHE = {}

def hotel_column_exists(col_name: str) -> bool:
    """Check whether the `hotels` table has a column named `col_name`.
    Performs a cheap select and caches the result. Returns False if Supabase is not configured.
    """
    global _HOTEL_COLUMNS_CACHE
    if not supabase:
        return False
    # Avoid permanently caching negative results because the schema may change at runtime
    if col_name in _HOTEL_COLUMNS_CACHE and _HOTEL_COLUMNS_CACHE[col_name] is True:
        return True
    try:
        resp = supabase.table('hotels').select(col_name).limit(1).execute()
        if hasattr(resp, 'error') and resp.error:
            return False
        # Cache positive result to reduce repeated checks
        _HOTEL_COLUMNS_CACHE[col_name] = True
        return True
    except Exception as e:
        print(f"hotel_column_exists check failed for '{col_name}': {e}")
        return False

def event_column_exists(col_name: str) -> bool:
    """Check whether the `events` table has a column named `col_name`.
    Performs a cheap select and caches the result. Returns False if Supabase is not configured.
    """
    global _EVENT_COLUMNS_CACHE
    if not supabase:
        return False

    
    if col_name in _EVENT_COLUMNS_CACHE:
        return _EVENT_COLUMNS_CACHE[col_name]
    try:
        resp = supabase.table('events').select(col_name).limit(1).execute()
        if hasattr(resp, 'error') and resp.error:
            _EVENT_COLUMNS_CACHE[col_name] = False
            return False
        _EVENT_COLUMNS_CACHE[col_name] = True
        return True
    except Exception as e:
        print(f"event_column_exists check failed for '{col_name}': {e}")
        _EVENT_COLUMNS_CACHE[col_name] = False
        return False

def restaurant_column_exists(col_name: str) -> bool:
    """Check whether the `restaurants` table has a column named `col_name`.
    Performs a cheap select and caches the result. Returns False if Supabase is not configured.
    """
    global _RESTAURANT_COLUMNS_CACHE
    if not supabase:
        return False
    if col_name in _RESTAURANT_COLUMNS_CACHE:
        return _RESTAURANT_COLUMNS_CACHE[col_name]
    try:
        resp = supabase.table('restaurants').select(col_name).limit(1).execute()
        if hasattr(resp, 'error') and resp.error:
            _RESTAURANT_COLUMNS_CACHE[col_name] = False
            return False
        _RESTAURANT_COLUMNS_CACHE[col_name] = True
        return True
    except Exception as e:
        print(f"restaurant_column_exists check failed for '{col_name}': {e}")
        _RESTAURANT_COLUMNS_CACHE[col_name] = False
        return False

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


# Template filter: format price values with PHP sign and comma separators
import re as _re

def format_price(value):
    """Format a price or price-range into PHP currency with thousand separators.
    Examples:
      1500 -> ₱1,500
      '1500 - 2500' -> ₱1,500 - ₱2,500
      '₱1500' -> ₱1,500
    """
    if value is None:
        return ''
    # If it's already numeric
    try:
        if isinstance(value, (int, float)):
            return f"₱{int(value):,}"
        # If value is a numeric string
        vstr = str(value).strip()
        # If the whole string is a single number
        if _re.fullmatch(r"[\d,]+(\.\d+)?", vstr):
            num = int(_re.sub(r"[^0-9]", "", vstr))
            return f"₱{num:,}"
    except Exception:
        pass

    s = str(value)
    # Replace all contiguous digit groups with formatted numbers (keep other chars like - or spaces)
    def _replace_num(m):
        digits = _re.sub(r"[^0-9]", "", m.group(0))
        if not digits:
            return m.group(0)
        try:
            n = int(digits)
            return f"₱{n:,}"
        except Exception:
            return m.group(0)

    formatted = _re.sub(r"\d[\d,\.]*\d|\d", _replace_num, s)
    return formatted

# register filter
app.jinja_env.filters['format_price'] = format_price

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
    attractions = []
    natural = []
    heritage = []
    if supabase:
        try:
            resp = supabase.table('attractions').select('*').eq('is_active', True).order('created_at', desc=True).execute()
            attractions = resp.data or []
            # Partition by category for the template
            natural = [a for a in attractions if (a.get('category') or '').lower() == 'natural']
            heritage = [a for a in attractions if (a.get('category') or '').lower() == 'heritage']
        except Exception as e:
            print(f"Error fetching attractions: {e}")

    return render_template('home/attractions.html', attractions=attractions, natural=natural, heritage=heritage)

@app.route('/attractions/natural')
def natural():
    return render_template('home/attractions/natural.html')

@app.route('/attractions/heritage')
def heritage():
    return render_template('home/attractions/heritage.html')

@app.route('/attractions/<attraction>')
def indiv_attractions(attraction):
    # Load attraction from Supabase by slug
    attraction_data = None
    related_attractions = []
    if supabase:
        try:
            resp = supabase.table('attractions').select('*').eq('slug', attraction).single().execute()
            if resp and resp.data:
                attraction_data = resp.data
                # Ensure gallery_urls is a list
                if isinstance(attraction_data.get('gallery_urls'), str):
                    # Attempt to parse JSON string
                    try:
                        import json
                        attraction_data['gallery_urls'] = json.loads(attraction_data['gallery_urls'])
                    except Exception:
                        attraction_data['gallery_urls'] = []
                elif attraction_data.get('gallery_urls') is None:
                    attraction_data['gallery_urls'] = []
                # fetch a few related attractions (same category, excluding current)
                try:
                    related_resp = supabase.table('attractions').select('id,name,slug,category,location,image_url').eq('category', attraction_data.get('category')).neq('id', attraction_data.get('id')).limit(4).execute()
                    related_attractions = related_resp.data or []
                except Exception:
                    related_attractions = []
        except Exception as e:
            print(f"Error fetching attraction {attraction}: {e}")

    if not attraction_data:
        flash('Attraction not found.', 'error')
        return redirect(url_for('attractions'))

    return render_template('home/attractions/indiv-attractions.html', attraction=attraction_data, related_attractions=related_attractions)

# ============================================
# EXPERIENCES ROUTES
# ============================================

@app.route('/experiences')
def experiences():
    # Fetch products and partition into categories for the products page
    footwear = []
    bags = []
    accessories = []
    handicrafts = []
    food = []
    others = []

    if supabase:
        try:
            resp = supabase.table('products').select('*').eq('is_active', True).order('created_at', desc=True).execute()
            products = resp.data or []
            for p in products:
                cat = (p.get('category') or '').lower()
                if cat == 'footwear':
                    footwear.append(p)
                elif cat == 'bags':
                    bags.append(p)
                elif cat == 'accessories':
                    accessories.append(p)
                elif cat == 'handicrafts':
                    handicrafts.append(p)
                elif 'food' in cat or cat == 'food products':
                    food.append(p)
                else:
                    others.append(p)
        except Exception as e:
            print(f"Error fetching products: {e}")

    # Server-side: build a single combined carousel.
    # For each category, pick up to `max_per_category` most recent products and combine them.
    max_per_category = 3
    categories_all = [
        ('footwear', footwear),
        ('bags', bags),
        ('accessories', accessories),
        ('handicrafts', handicrafts),
        ('food', food),
        ('others', others),
    ]

    all_products = (footwear or []) + (bags or []) + (accessories or []) + (handicrafts or []) + (food or []) + (others or [])
    slides = []
    for key, items in categories_all:
        items = items or []
        # take up to max_per_category most recent (list is ordered desc by created_at)
        for p in items[:max_per_category]:
            slide_url = p.get('image_url') if p.get('image_url') else (p.get('gallery')[0] if p.get('gallery') else url_for('static', filename='assets/images/attractions/natural/hero.JPG'))
            slug = p.get('slug') if p.get('slug') else generate_slug(p.get('name', ''))
            slide_link = url_for('indiv_product', product=slug)
            slides.append({'url': slide_url, 'name': p.get('name', ''), 'link': slide_link, 'category': key})

    carousels = []
    if slides:
        # single carousel combining selected slides from all categories
        carousels.append({'title': 'Products Showcase', 'icon': 'fa-box-open', 'slides': slides})

    return render_template('experiences/products.html', footwear=footwear, bags=bags, accessories=accessories, handicrafts=handicrafts, food=food, others=others, carousels=carousels, all_products=all_products)

@app.route('/experiences/festivals')
def festivals():
    return render_template('experiences/festivals.html')

@app.route('/experiences/festivals/events')
def events():
    events_list = []
    if supabase:
        try:
            resp = supabase.table('events').select('*').order('event_date', desc=False).execute()
            rows = resp.data or []
            for r in rows:
                # determine image to use
                image = r.get('image_url') or (r.get('gallery_urls') and (r.get('gallery_urls')[0] if isinstance(r.get('gallery_urls'), list) and len(r.get('gallery_urls'))>0 else None)) or url_for('static', filename='assets/images/attractions/natural/hero.JPG')
                # format date display
                start = r.get('event_date')
                end = r.get('end_date')
                display_date = ''
                try:
                    if start:
                        sd = datetime.fromisoformat(start)
                        if end:
                            ed = datetime.fromisoformat(end)
                            if sd.year == ed.year and sd.month == ed.month:
                                display_date = f"{sd.day}-{ed.day} {sd.strftime('%B %Y')}"
                            else:
                                display_date = f"{sd.strftime('%d %B %Y')} - {ed.strftime('%d %B %Y')}"
                        else:
                            display_date = sd.strftime('%d %B %Y')
                except Exception:
                    display_date = start or ''

                # format time display
                display_time = ''
                try:
                    if r.get('all_day') or (not r.get('start_time') and not r.get('end_time')):
                        display_time = 'All Day Event'
                    else:
                        st = r.get('start_time')
                        et = r.get('end_time')
                        if st and et:
                            t1 = datetime.strptime(st, '%H:%M').strftime('%-I:%M %p') if '%' in '%-I' else datetime.strptime(st, '%H:%M').strftime('%I:%M %p').lstrip('0')
                            t2 = datetime.strptime(et, '%H:%M').strftime('%-I:%M %p') if '%' in '%-I' else datetime.strptime(et, '%H:%M').strftime('%I:%M %p').lstrip('0')
                            display_time = f"{t1} - {t2}"
                        elif st:
                            display_time = st
                except Exception:
                    display_time = (r.get('start_time') or '')

                month = ''
                try:
                    if start:
                        month = datetime.fromisoformat(start).strftime('%B').lower()
                except Exception:
                    month = ''

                events_list.append({
                    'id': r.get('id'),
                    'title': r.get('title'),
                    'image': image,
                    'featured': bool(r.get('is_featured')),
                    'description': r.get('description') or '',
                    'full_description': r.get('full_description') or '',
                    'display_date': display_date,
                    'display_time': display_time,
                    'location': r.get('location') or r.get('venue_address') or '',
                    'start_date': start,
                    'category': r.get('category') or '',
                    'cta_text': r.get('cta_text'),
                    'cta_url': r.get('cta_url'),
                    'map_embed': r.get('map_embed'),
                    'month': month
                })
        except Exception as e:
            print(f"Error fetching events for public page: {e}")

    return render_template('experiences/festivals/events.html', events=events_list)

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
    # Attempt to load product from Supabase (by slug). If unavailable, fall back to sample data.
    product_data = None
    related_products = []
    if supabase:
        try:
            resp = supabase.table('products').select('*').eq('slug', product).single().execute()
            if resp and resp.data:
                p = resp.data
                # Normalize gallery field (could be stored as JSON string, comma-separated, or list)
                gallery = []
                raw_gallery = p.get('gallery') or p.get('gallery_urls') or p.get('images') or p.get('image_url')
                if isinstance(raw_gallery, str):
                    # try JSON
                    try:
                        import json
                        parsed = json.loads(raw_gallery)
                        if isinstance(parsed, list):
                            gallery = parsed
                        else:
                            # if it's a single string, split by comma
                            gallery = [i.strip() for i in raw_gallery.split(',') if i.strip()]
                    except Exception:
                        gallery = [i.strip() for i in raw_gallery.split(',') if i.strip()]
                elif isinstance(raw_gallery, list):
                    gallery = raw_gallery
                elif raw_gallery:
                    gallery = [raw_gallery]

                # Normalize making/process steps
                making_process = p.get('making_process') or p.get('process_steps') or p.get('process')
                steps = []
                if isinstance(making_process, str):
                    # If string, attempt to parse JSON or fallback to a single-step description
                    try:
                        import json
                        parsed = json.loads(making_process)
                        if isinstance(parsed, list):
                            steps = parsed
                        else:
                            steps = [{'title': 'Overview', 'description': making_process}]
                    except Exception:
                        steps = [{'title': 'Overview', 'description': making_process}]
                elif isinstance(making_process, list):
                    steps = making_process
                elif making_process:
                    # Unexpected type, coerce to string
                    steps = [{'title': 'Overview', 'description': str(making_process)}]

                # Artisan story maybe stored as JSON/object
                artisan_story = p.get('artisan_story')
                if isinstance(artisan_story, str):
                    try:
                        import json
                        artisan_story = json.loads(artisan_story)
                    except Exception:
                        artisan_story = {'intro': artisan_story, 'detail': '', 'quote': '', 'artisan_name': ''}

                # Buy locations normalization
                buy_locations = p.get('buy_locations') or p.get('sellers') or []
                if isinstance(buy_locations, str):
                    try:
                        import json
                        parsed = json.loads(buy_locations)
                        if isinstance(parsed, list):
                            buy_locations = parsed
                        else:
                            buy_locations = []
                    except Exception:
                        buy_locations = []

                # Build product object for template
                product_data = {
                    'name': p.get('name') or product.replace('-', ' ').title(),
                    'category': p.get('category') or 'Uncategorized',
                    'main_image': None,  # template will fallback to placeholder if needed
                    'description': p.get('short_description') or p.get('description') or p.get('summary') or p.get('excerpt') or p.get('full_description') or '',
                    'price_range': p.get('price_range') or p.get('price') or '',
                    'features': p.get('features') if isinstance(p.get('features'), list) else (p.get('features') and [p.get('features')] or []),
                    'specifications': p.get('specifications') if isinstance(p.get('specifications'), list) else [],
                    'making_process': steps,
                    'artisan_story': artisan_story,
                    'artisan_image': p.get('artisan_image') or None,
                    'buy_locations': buy_locations if isinstance(buy_locations, list) else [],
                    'gallery': gallery,
                    'slug': p.get('slug') or product.replace('-', ' ').lower(),
                }

                # main image preference
                if p.get('image_url'):
                    product_data['main_image'] = p.get('image_url')
                elif gallery:
                    product_data['main_image'] = gallery[0]

                # related products: fetch a few similar items
                try:
                    rel_resp = supabase.table('products').select('id,name,slug,image_url,price_range').neq('slug', product).eq('category', p.get('category')).limit(4).execute()
                    related_products = rel_resp.data or []
                except Exception:
                    related_products = []

        except Exception as e:
            print(f"Error fetching product {product}: {e}")

    # Fallback sample product if DB not available or product not found
    if not product_data:
        product_data = {
            'name': product.replace('-', ' ').title(),
            'category': 'Footwear',
            'main_image': 'tsinelas.jpg',
            'description': 'High-quality handcrafted product from Liliw',
            'full_description': 'Detailed description of the product and its making process.',
            'price_range': '₱150 - ₱500',
            'features': ['Handmade', 'Durable materials', 'Comfortable fit', 'Various designs'],
            'specifications': [
                {'label': 'Material', 'value': 'Genuine leather'},
                {'label': 'Available Sizes', 'value': '5-12'},
                {'label': 'Colors', 'value': 'Multiple options'}
            ],
            'making_process': [
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

    # If related_products wasn't set earlier, provide simple defaults
    if not related_products:
        related_products = [
            {'name': 'Leather Sandals', 'slug': 'leather-sandals', 'image': 'hero.JPG', 'price': '₱300 - ₱800'},
            {'name': 'Leather Bags', 'slug': 'leather-bags', 'image': 'hero.JPG', 'price': '₱500 - ₱1,500'}
        ]

    return render_template('experiences/indiv-product.html', product=product_data, related_products=related_products)

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
    hotels = []
    restaurants = []
    hotel_categories = ["Hotel", "Resort", "Inn", "Lodge", "Homestay"]
    restaurant_categories = [
        "Cafe", "Restaurant", "Fine Dining", "Fast Food", "Buffet",
        "Dessert", "Bar", "Food Stall", "Bakery", "Other"
    ]
    if supabase:
        try:
            resp = supabase.table('hotels').select('*').order('created_at', desc=True).execute()
            hotels = resp.data or []
        except Exception as e:
            print(f"Error fetching hotels for plan page: {e}")
        try:
            rresp = supabase.table('restaurants').select('*').order('created_at', desc=True).execute()
            restaurants = rresp.data or []
        except Exception as e:
            print(f"Error fetching restaurants for plan page: {e}")
    return render_template('plan/stay.html', hotels=hotels, restaurants=restaurants, hotel_categories=hotel_categories, restaurant_categories=restaurant_categories)

@app.route('/plan/stay')
def stay():
    hotels = []
    restaurants = []
    hotel_categories = ["Hotel", "Resort", "Inn", "Lodge", "Homestay"]
    restaurant_categories = [
        "Cafe", "Restaurant", "Fine Dining", "Fast Food", "Buffet",
        "Dessert", "Bar", "Food Stall", "Bakery", "Other"
    ]
    if supabase:
        try:
            resp = supabase.table('hotels').select('*').order('created_at', desc=True).execute()
            hotels = resp.data or []
        except Exception as e:
            print(f"Error fetching hotels for stay page: {e}")
        try:
            rresp = supabase.table('restaurants').select('*').order('created_at', desc=True).execute()
            restaurants = rresp.data or []
        except Exception as e:
            print(f"Error fetching restaurants for stay page: {e}")
    return render_template('plan/stay.html', hotels=hotels, restaurants=restaurants, hotel_categories=hotel_categories, restaurant_categories=restaurant_categories)

@app.route('/plan/stay/<hotel>')
def indiv_hotel(hotel):
    hotel_data = None
    similar_hotels = []
    if supabase:
        try:
            resp = supabase.table('hotels').select('*').eq('slug', hotel).single().execute()
            hotel_data = resp.data
        except Exception as e:
            print(f"Error fetching hotel '{hotel}': {e}")
        try:
            resp2 = supabase.table('hotels').select('name,slug,image_url,price_min,price_max').neq('slug', hotel).limit(4).execute()
            similar_hotels = resp2.data or []
        except Exception:
            similar_hotels = []

    # Fallback sample if not found
    if not hotel_data:
        hotel_data = {
            'name': hotel.replace('-', ' ').title(),
            'image_url': 'hero.JPG',
            'price_min': None,
            'price_max': None,
            'address': 'Main Street, Liliw, Laguna',
            'phone': '(049) 123-4567',
            'email': 'info@hotel.com',
            'description': 'Comfortable accommodation in the heart of Liliw',
            'amenities': [],
            'rooms': [],
            'policies': [],
            'map_embed': ''
        }

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
            # Set status to rejected and archive the blog
            supabase.table('blogs').update({
                'status': 'rejected',
                'is_archived': True,
                'is_deleted': False,
                'deleted_at': datetime.now().isoformat()
            }).eq('id', blog_id).execute()
            flash('Blog post rejected and archived.', 'success')
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
        print('DEBUG: entered admin_hotels_add POST handler, supabase=', bool(supabase))
        try:
            print('DEBUG: request.method=', request.method)
            print('DEBUG: request.form keys (add) =', list(request.form.keys()))
            print('DEBUG: request.files keys (add) =', list(request.files.keys()))
        except Exception:
            pass
        if supabase:
            try:
                name = request.form.get('name')
                image_url = None
                # Category selected (no free-text 'other' field required)
                category_value = request.form.get('category')
                # Handle category with optional 'Other' free-text
                category_field = request.form.get('category')
                category_other = (request.form.get('category_other') or '').strip()
                if category_field == 'Other' and category_other:
                    category_value = category_other
                else:
                    category_value = category_field
                gallery_urls = []
                # Choose storage client (prefer admin for uploads)
                storage_client = supabase_admin if supabase_admin else supabase
                # Bucket name to store attraction images. Create this bucket in Supabase storage and make it public.
                IMAGE_BUCKET = os.getenv('SUPABASE_ATTRACTION_BUCKET', 'attraction-images')

                # Handle featured image upload
                if 'image' in request.files:
                    file = request.files['image']
                    if file and file.filename:
                        file_ext = file.filename.rsplit('.', 1)[-1].lower()
                        unique_filename = f"attractions/{uuid.uuid4()}.{file_ext}"
                        file_bytes = file.read()
                        try:
                            storage_client.storage.from_(IMAGE_BUCKET).upload(
                                unique_filename, file_bytes,
                                {'content-type': file.content_type}
                            )
                            image_url = f"{SUPABASE_URL}/storage/v1/object/public/{IMAGE_BUCKET}/{unique_filename}"
                        except Exception as _e:
                            print('Failed to upload featured image to Supabase storage:', _e)

                # Handle gallery images (multiple)
                if 'gallery_images' in request.files:
                    files = request.files.getlist('gallery_images')
                    for f in files:
                        if f and f.filename:
                            try:
                                file_ext = f.filename.rsplit('.', 1)[-1].lower()
                                unique_filename = f"attractions/gallery/{uuid.uuid4()}.{file_ext}"
                                file_bytes = f.read()
                                storage_client.storage.from_(IMAGE_BUCKET).upload(
                                    unique_filename, file_bytes,
                                    {'content-type': f.content_type}
                                )
                                gallery_urls.append(f"{SUPABASE_URL}/storage/v1/object/public/{IMAGE_BUCKET}/{unique_filename}")
                            except Exception as _e:
                                print('Failed to upload gallery image to Supabase storage:', _e)
                
                attraction_data = {
                    'name': name,
                    'slug': generate_slug(name),
                    'category': request.form.get('category'),
                    'description': request.form.get('description'),
                    'full_description': request.form.get('full_description'),
                    'location': request.form.get('location'),
                    'image_url': image_url,
                    'gallery_urls': gallery_urls,
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
                # category with 'Other' handling
                category_field = request.form.get('category')
                category_other = (request.form.get('category_other') or '').strip()
                if category_field == 'Other' and category_other:
                    category_value = category_other
                else:
                    category_value = category_field

                update_data = {
                    'name': request.form.get('name'),
                    'category': category_value,
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
                
                # Handle new featured image upload
                storage_client = supabase_admin if supabase_admin else supabase
                IMAGE_BUCKET = os.getenv('SUPABASE_ATTRACTION_BUCKET', 'attraction-images')
                if 'image' in request.files:
                    file = request.files['image']
                    if file and file.filename:
                        file_ext = file.filename.rsplit('.', 1)[-1].lower()
                        unique_filename = f"attractions/{uuid.uuid4()}.{file_ext}"
                        file_bytes = file.read()
                        try:
                            storage_client.storage.from_(IMAGE_BUCKET).upload(
                                unique_filename, file_bytes,
                                {'content-type': file.content_type}
                            )
                            update_data['image_url'] = f"{SUPABASE_URL}/storage/v1/object/public/{IMAGE_BUCKET}/{unique_filename}"
                        except Exception as _e:
                            print('Failed to upload featured image to Supabase storage:', _e)
                
                # Handle new gallery uploads (append to gallery_urls)
                gallery_urls = []
                if 'gallery_images' in request.files:
                    files = request.files.getlist('gallery_images')
                    for f in files:
                        if f and f.filename:
                            try:
                                file_ext = f.filename.rsplit('.', 1)[-1].lower()
                                unique_filename = f"attractions/gallery/{uuid.uuid4()}.{file_ext}"
                                file_bytes = f.read()
                                storage_client.storage.from_(IMAGE_BUCKET).upload(
                                    unique_filename, file_bytes,
                                    {'content-type': f.content_type}
                                )
                                gallery_urls.append(f"{SUPABASE_URL}/storage/v1/object/public/{IMAGE_BUCKET}/{unique_filename}")
                            except Exception as _e:
                                print('Failed to upload gallery image to Supabase storage:', _e)
                if gallery_urls:
                    update_data['gallery_urls'] = gallery_urls

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
                # Handle featured image (single) and gallery images (multiple)
                gallery_urls = []
                # Featured image comes from input name 'image'
                if 'image' in request.files:
                    file = request.files['image']
                    if file and file.filename:
                        file_ext = file.filename.rsplit('.', 1)[-1].lower()
                        file_bytes = file.read()
                        url = upload_bytes_get_url_to_bucket(file_bytes, file_ext, file.content_type, SUPABASE_PRODUCT_BUCKET, prefix='products/')
                        if url:
                            image_url = url
                            gallery_urls.append(url)

                # Gallery images may be provided as multiple files named 'gallery_images'
                gallery_files = request.files.getlist('gallery_images') or []
                for gf in gallery_files:
                    try:
                        if gf and gf.filename:
                            gext = gf.filename.rsplit('.', 1)[-1].lower()
                            gbytes = gf.read()
                            gurl = upload_bytes_get_url_to_bucket(gbytes, gext, gf.content_type, SUPABASE_PRODUCT_BUCKET, prefix='products/')
                            if gurl:
                                gallery_urls.append(gurl)
                    except Exception as gerr:
                        print(f"Gallery image upload failed: {gerr}")
                
                # parse buy_locations_json and inquire_links_json safely
                try:
                    import json as _json
                    _buy_locations_raw = request.form.get('buy_locations_json')
                    buy_locations_val = _json.loads(_buy_locations_raw) if _buy_locations_raw and _buy_locations_raw.strip() else []
                except Exception as _e:
                    print(f"Error parsing buy_locations_json: {_e}")
                    buy_locations_val = []
                try:
                    import json as _json2
                    _inquire_raw = request.form.get('inquire_links_json')
                    inquire_links_val = _json2.loads(_inquire_raw) if _inquire_raw and _inquire_raw.strip() else []
                except Exception as _e:
                    print(f"Error parsing inquire_links_json: {_e}")
                    inquire_links_val = []

                product_data = {
                    'name': name,
                    'slug': generate_slug(name),
                    'category': request.form.get('category') or 'Other',
                    'description': request.form.get('description'),
                    'full_description': request.form.get('full_description'),
                    'price_range': request.form.get('price_range'),
                    'image_url': image_url,
                    'gallery': gallery_urls or None,
                    'making_process': request.form.get('making_process'),
                    'is_active': True
                }
                # Only include buy_locations/inquire_links if the table has those columns
                try:
                    if buy_locations_val and product_column_exists('buy_locations'):
                        product_data['buy_locations'] = buy_locations_val
                except Exception:
                    # defensive: don't block insert if detection fails
                    pass
                try:
                    if inquire_links_val and product_column_exists('inquire_links'):
                        product_data['inquire_links'] = inquire_links_val
                except Exception:
                    pass
                
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
                # parse JSON hidden fields safely for update
                try:
                    import json as _json3
                    _buy_locations_raw = request.form.get('buy_locations_json')
                    buy_locations_val = _json3.loads(_buy_locations_raw) if _buy_locations_raw and _buy_locations_raw.strip() else []
                except Exception as _e:
                    print(f"Error parsing buy_locations_json (edit): {_e}")
                    buy_locations_val = []
                try:
                    import json as _json4
                    _inquire_raw = request.form.get('inquire_links_json')
                    inquire_links_val = _json4.loads(_inquire_raw) if _inquire_raw and _inquire_raw.strip() else []
                except Exception as _e:
                    print(f"Error parsing inquire_links_json (edit): {_e}")
                    inquire_links_val = []

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
                # Only include buy_locations/inquire_links if the table has those columns
                try:
                    if product_column_exists('buy_locations'):
                        update_data['buy_locations'] = buy_locations_val
                except Exception:
                    pass
                try:
                    if product_column_exists('inquire_links'):
                        update_data['inquire_links'] = inquire_links_val
                except Exception:
                    pass
                
                if 'image' in request.files:
                    file = request.files['image']
                    if file and file.filename:
                        file_ext = file.filename.rsplit('.', 1)[-1].lower()
                        file_bytes = file.read()
                        url = upload_bytes_get_url_to_bucket(file_bytes, file_ext, file.content_type, SUPABASE_PRODUCT_BUCKET, prefix='products/')
                        if url:
                            update_data['image_url'] = url
                            # initialize gallery if not present
                            try:
                                existing = supabase.table('products').select('gallery').eq('id', product_id).single().execute()
                                existing_gallery = existing.data.get('gallery') if existing and existing.data else []
                                if existing_gallery is None:
                                    existing_gallery = []
                            except Exception:
                                existing_gallery = []
                            update_data['gallery'] = (existing_gallery or []) + [url]

                # Handle gallery_images multiple files
                gallery_files = request.files.getlist('gallery_images') or []
                if gallery_files:
                    gallery_urls = []
                    for gf in gallery_files:
                        try:
                            if gf and gf.filename:
                                gext = gf.filename.rsplit('.', 1)[-1].lower()
                                gbytes = gf.read()
                                gurl = upload_bytes_get_url_to_bucket(gbytes, gext, gf.content_type, SUPABASE_PRODUCT_BUCKET, prefix='products/')
                                if gurl:
                                    gallery_urls.append(gurl)
                        except Exception as gerr:
                            print(f"Gallery upload failed: {gerr}")
                    if gallery_urls:
                        # append to existing gallery
                        try:
                            existing = supabase.table('products').select('gallery').eq('id', product_id).single().execute()
                            existing_gallery = existing.data.get('gallery') if existing and existing.data else []
                            if existing_gallery is None:
                                existing_gallery = []
                        except Exception:
                            existing_gallery = []
                        update_data['gallery'] = (existing_gallery or []) + gallery_urls
                
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

                # Handle featured image upload (single) using helper
                if 'image' in request.files:
                    file = request.files['image']
                    if file and file.filename:
                        file_ext = file.filename.rsplit('.', 1)[-1].lower()
                        file_bytes = file.read()
                        image_url = upload_bytes_get_url_to_bucket(file_bytes, file_ext, file.content_type, bucket='blog-images', prefix='events/')

                # Handle gallery images (multiple)
                gallery_urls = []
                gallery_files = request.files.getlist('gallery_images') or []
                for gf in gallery_files:
                    if gf and gf.filename:
                        gf_ext = gf.filename.rsplit('.', 1)[-1].lower()
                        gf_bytes = gf.read()
                        url = upload_bytes_get_url_to_bucket(gf_bytes, gf_ext, gf.content_type, bucket='blog-images', prefix='events/gallery/')
                        if url:
                            gallery_urls.append(url)

                # Extra optional fields from form
                cta_text = request.form.get('cta_text') or None
                cta_url = request.form.get('cta_url') or None
                venue_address = request.form.get('venue_address') or None
                map_embed = request.form.get('map_embed') or None
                venue_lat = request.form.get('venue_lat') or None
                venue_lng = request.form.get('venue_lng') or None
                all_day = request.form.get('all_day') == 'on' or (not request.form.get('start_time') and not request.form.get('end_time'))

                # Build minimal event payload and only include optional keys if DB has those columns
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
                    'is_featured': request.form.get('is_featured') == 'on',
                    'is_active': True
                }

                # Optional persisted fields (only add if column exists)
                try:
                    if image_url and event_column_exists('image_url'):
                        event_data['image_url'] = image_url
                except Exception:
                    pass
                try:
                    if gallery_urls and event_column_exists('gallery_urls'):
                        event_data['gallery_urls'] = gallery_urls
                except Exception:
                    pass
                try:
                    if cta_text and event_column_exists('cta_text'):
                        event_data['cta_text'] = cta_text
                except Exception:
                    pass
                try:
                    if cta_url and event_column_exists('cta_url'):
                        event_data['cta_url'] = cta_url
                except Exception:
                    pass
                try:
                    if venue_address and event_column_exists('venue_address'):
                        event_data['venue_address'] = venue_address
                except Exception:
                    pass
                try:
                    if map_embed and event_column_exists('map_embed'):
                        event_data['map_embed'] = map_embed
                except Exception:
                    pass
                try:
                    if venue_lat and event_column_exists('venue_lat'):
                        event_data['venue_lat'] = float(venue_lat)
                except Exception:
                    pass
                try:
                    if venue_lng and event_column_exists('venue_lng'):
                        event_data['venue_lng'] = float(venue_lng)
                except Exception:
                    pass
                try:
                    if event_column_exists('all_day'):
                        event_data['all_day'] = all_day
                except Exception:
                    pass
                
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
                # Prepare update data including optional fields
                cta_text = request.form.get('cta_text') or None
                cta_url = request.form.get('cta_url') or None
                venue_address = request.form.get('venue_address') or None
                map_embed = request.form.get('map_embed') or None
                venue_lat = request.form.get('venue_lat') or None
                venue_lng = request.form.get('venue_lng') or None
                all_day = request.form.get('all_day') == 'on' or (not request.form.get('start_time') and not request.form.get('end_time'))

                # base update data
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

                # Optional persisted update fields
                try:
                    if event_column_exists('cta_text'):
                        update_data['cta_text'] = cta_text
                except Exception:
                    pass
                try:
                    if event_column_exists('cta_url'):
                        update_data['cta_url'] = cta_url
                except Exception:
                    pass
                try:
                    if event_column_exists('venue_address'):
                        update_data['venue_address'] = venue_address
                except Exception:
                    pass
                try:
                    if event_column_exists('map_embed'):
                        update_data['map_embed'] = map_embed
                except Exception:
                    pass
                try:
                    if venue_lat and event_column_exists('venue_lat'):
                        update_data['venue_lat'] = float(venue_lat)
                except Exception:
                    pass
                try:
                    if venue_lng and event_column_exists('venue_lng'):
                        update_data['venue_lng'] = float(venue_lng)
                except Exception:
                    pass
                try:
                    if event_column_exists('all_day'):
                        update_data['all_day'] = all_day
                except Exception:
                    pass
                
                if 'image' in request.files:
                    file = request.files['image']
                    if file and file.filename:
                        file_ext = file.filename.rsplit('.', 1)[-1].lower()
                        file_bytes = file.read()
                        update_data['image_url'] = upload_bytes_get_url_to_bucket(file_bytes, file_ext, file.content_type, bucket='blog-images', prefix='events/')

                # Handle gallery uploads: append to existing gallery_urls if present
                gallery_files = request.files.getlist('gallery_images') or []
                if gallery_files:
                    gallery_urls = []
                    for gf in gallery_files:
                        if gf and gf.filename:
                            gf_ext = gf.filename.rsplit('.', 1)[-1].lower()
                            gf_bytes = gf.read()
                            url = upload_bytes_get_url_to_bucket(gf_bytes, gf_ext, gf.content_type, bucket='blog-images', prefix='events/gallery/')
                            if url:
                                gallery_urls.append(url)
                    # Try to fetch existing gallery and merge
                    try:
                        resp = supabase.table('events').select('gallery_urls').eq('id', event_id).single().execute()
                        existing = resp.data or {}
                        existing_gallery = existing.get('gallery_urls') or []
                        update_data['gallery_urls'] = (existing_gallery or []) + gallery_urls
                    except Exception:
                        update_data['gallery_urls'] = gallery_urls
                
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
                gallery_urls = []

                # support multiple files (featured + gallery)
                if 'image' in request.files:
                    files = request.files.getlist('image')
                    uploaded = []
                    for file in files:
                        if file and getattr(file, 'filename', ''):
                            file_ext = file.filename.rsplit('.', 1)[-1].lower()
                            file_bytes = file.read()
                            url = upload_bytes_get_url_to_bucket(file_bytes, file_ext, file.content_type, SUPABASE_PRODUCT_BUCKET, prefix='hotels/')
                            if url:
                                uploaded.append(url)
                    if uploaded:
                        image_url = uploaded[0]
                        if len(uploaded) > 1:
                            gallery_urls = uploaded[1:]
                # also accept gallery_images separately
                if not gallery_urls and 'gallery_images' in request.files:
                    files = request.files.getlist('gallery_images')
                    for file in files:
                        if file and getattr(file, 'filename', ''):
                            file_ext = file.filename.rsplit('.', 1)[-1].lower()
                            file_bytes = file.read()
                            url = upload_bytes_get_url_to_bucket(file_bytes, file_ext, file.content_type, SUPABASE_PRODUCT_BUCKET, prefix='hotels/')
                            if url:
                                gallery_urls.append(url)

                # sanitize phone to digits only
                phone_raw = request.form.get('phone') or ''
                phone = re.sub(r'[^0-9]', '', phone_raw)

                # price min / max
                price_min_raw = request.form.get('price_min') or ''
                price_max_raw = request.form.get('price_max') or ''
                try:
                    price_min = float(price_min_raw) if price_min_raw != '' else None
                except Exception:
                    price_min = None
                try:
                    price_max = float(price_max_raw) if price_max_raw != '' else None
                except Exception:
                    price_max = None

                # amenities (expect JSON array string or comma-separated)
                amenities_raw = request.form.get('amenities') or ''
                amenities = []
                try:
                    import json
                    parsed = json.loads(amenities_raw)
                    if isinstance(parsed, list):
                        amenities = parsed
                except Exception:
                    # fallback: comma separated
                    amenities = [a.strip() for a in amenities_raw.split(',') if a.strip()]

                # websites (JSON or comma-separated)
                websites_raw = request.form.get('websites') or ''
                websites = []
                try:
                    import json
                    parsed = json.loads(websites_raw)
                    if isinstance(parsed, list):
                        websites = parsed
                except Exception:
                    websites = [w.strip() for w in websites_raw.split(',') if w.strip()]

                hotel_data = {
                    'name': name,
                    'slug': generate_slug(name),
                    'description': request.form.get('description'),
                    'address': request.form.get('address'),
                    'phone': phone,
                    'email': request.form.get('email'),
                    'price_min': price_min,
                    'price_max': price_max,
                    'image_url': image_url,
                    'map_embed': request.form.get('map_embed'),
                    'websites': websites,
                    'amenities': amenities,
                    'gallery_urls': gallery_urls,
                    'latitude': request.form.get('latitude'),
                    'longitude': request.form.get('longitude'),
                    'is_active': True
                }
                # Try including category by default; if DB rejects because column missing, retry without it
                # Debug: log form keys and category to help diagnose missing value
                try:
                    print('DEBUG: hotel add form keys =', list(request.form.keys()))
                    print('DEBUG: hotel add category raw =', repr(request.form.get('category')))
                except Exception:
                    pass

                # Respect the submitted category only if present; do not force a 'Hotel' fallback here
                category_val = (request.form.get('category') or '').strip()
                hotel_data_with_cat = dict(hotel_data)
                if category_val:
                    hotel_data_with_cat['category'] = category_val

                # Debug: print category value and payload we'll send to Supabase
                try:
                    print('DEBUG: category_val (to insert) =', repr(category_val))
                    # don't print entire hotel_data_with_cat if it may be large; show relevant keys
                    dbg_keys = {k: hotel_data_with_cat.get(k) for k in ['name','slug','category','price_min','price_max']}
                    print('DEBUG: hotel_data_with_cat (summary) =', dbg_keys)
                except Exception:
                    pass

                tried_without_category = False
                try:
                    resp = supabase.table('hotels').insert(hotel_data_with_cat).execute()
                    if hasattr(resp, 'error') and resp.error:
                        # If the error mentions missing column, retry without category
                        err_text = str(resp.error)
                        print('Supabase insert error for hotels:', resp.error)
                        _log_hotel_error('Supabase insert error for hotels (first attempt)', exc=resp.error, payload=hotel_data_with_cat)
                        if 'column "category" does not exist' in err_text.lower() or 'unrecognized column' in err_text.lower():
                            tried_without_category = True
                            # retry without category
                            try:
                                resp2 = supabase.table('hotels').insert(hotel_data).execute()
                                if hasattr(resp2, 'error') and resp2.error:
                                    print('Supabase insert error on retry (without category):', resp2.error)
                                    _log_hotel_error('Supabase insert error for hotels (retry no category)', exc=resp2.error, payload=hotel_data)
                                    flash('Failed to add hotel (DB error). See server logs.', 'error')
                                else:
                                    print('Hotel insert response (retry no category):', getattr(resp2, 'data', resp2))
                                    flash('Hotel added successfully!', 'success')
                            except Exception as e2:
                                print('Exception while retrying insert without category:', e2)
                                _log_hotel_error('Exception while retrying insert without category', exc=e2, payload=hotel_data)
                                flash(f'Failed to add hotel (exception): {str(e2)}', 'error')
                        else:
                            flash('Failed to add hotel (DB error). See server logs.', 'error')
                    else:
                        print('Hotel insert response:', getattr(resp, 'data', resp))
                        flash('Hotel added successfully!', 'success')
                except Exception as e:
                    print('Exception while inserting hotel:', e)
                    _log_hotel_error('Exception while inserting hotel', exc=e, payload=hotel_data_with_cat)
                    # If insert failed and we haven't tried without category, retry once without it
                    if not tried_without_category:
                        try:
                            resp_retry = supabase.table('hotels').insert(hotel_data).execute()
                            if hasattr(resp_retry, 'error') and resp_retry.error:
                                print('Supabase insert error on retry (without category):', resp_retry.error)
                                _log_hotel_error('Supabase insert error for hotels (retry no category)', exc=resp_retry.error, payload=hotel_data)
                                flash('Failed to add hotel (DB error). See server logs.', 'error')
                            else:
                                print('Hotel insert response (retry no category):', getattr(resp_retry, 'data', resp_retry))
                                flash('Hotel added successfully!', 'success')
                        except Exception as e2:
                            print('Exception while retrying insert without category:', e2)
                            _log_hotel_error('Exception while retrying insert without category', exc=e2, payload=hotel_data)
                            flash(f'Failed to add hotel (exception): {str(e2)}', 'error')
                return redirect(url_for('admin_hotels'))
            except Exception as e:
                print(f"Error adding hotel: {e}")
                flash('Failed to add hotel.', 'error')
    
    return render_template('admin/hotel-form.html', hotel=None)

@app.route('/admin/hotels/<int:hotel_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_hotels_edit(hotel_id):
    if request.method == 'POST':
        print('DEBUG: entered admin_hotels_edit POST handler for id=', hotel_id, ' supabase=', bool(supabase))
        try:
            print('DEBUG: request.method=', request.method)
            print('DEBUG: request.form keys (edit) =', list(request.form.keys()))
            print('DEBUG: request.files keys (edit) =', list(request.files.keys()))
        except Exception:
            pass
        if supabase:
            try:
                # handle images
                image_url = None
                gallery_urls = None
                if 'image' in request.files:
                    files = request.files.getlist('image')
                    uploaded = []
                    for file in files:
                        if file and getattr(file, 'filename', ''):
                            file_ext = file.filename.rsplit('.', 1)[-1].lower()
                            file_bytes = file.read()
                            url = upload_bytes_get_url_to_bucket(file_bytes, file_ext, file.content_type, SUPABASE_PRODUCT_BUCKET, prefix='hotels/')
                            if url:
                                uploaded.append(url)
                    if uploaded:
                        image_url = uploaded[0]
                        if len(uploaded) > 1:
                            gallery_urls = uploaded[1:]
                if not gallery_urls and 'gallery_images' in request.files:
                    files = request.files.getlist('gallery_images')
                    gallery_urls = []
                    for file in files:
                        if file and getattr(file, 'filename', ''):
                            file_ext = file.filename.rsplit('.', 1)[-1].lower()
                            file_bytes = file.read()
                            url = upload_bytes_get_url_to_bucket(file_bytes, file_ext, file.content_type, SUPABASE_PRODUCT_BUCKET, prefix='hotels/')
                            if url:
                                gallery_urls.append(url)

                # parse price min/max
                price_min_raw = request.form.get('price_min') or ''
                price_max_raw = request.form.get('price_max') or ''
                try:
                    price_min = float(price_min_raw) if price_min_raw != '' else None
                except Exception:
                    price_min = None
                try:
                    price_max = float(price_max_raw) if price_max_raw != '' else None
                except Exception:
                    price_max = None

                # parse websites
                websites_raw = request.form.get('websites') or ''
                websites = []
                try:
                    import json
                    parsed = json.loads(websites_raw)
                    if isinstance(parsed, list):
                        websites = parsed
                except Exception:
                    websites = [w.strip() for w in websites_raw.split(',') if w.strip()]

                update_data = {
                    'name': request.form.get('name'),
                    'description': request.form.get('description'),
                    'address': request.form.get('address'),
                    'phone': re.sub(r'[^0-9]', '', (request.form.get('phone') or '')),
                    'email': request.form.get('email'),
                    'price_min': price_min,
                    'price_max': price_max,
                    'map_embed': request.form.get('map_embed'),
                    'websites': websites,
                    'amenities': None,
                    'latitude': request.form.get('latitude'),
                    'longitude': request.form.get('longitude'),
                    'is_active': request.form.get('is_active') == 'on',
                    'updated_at': datetime.now().isoformat()
                }
                # Include category only if the column exists
                try:
                    if hotel_column_exists('category'):
                        # Debug: log incoming form keys and requested category for edits
                        try:
                            print('DEBUG: hotel edit form keys =', list(request.form.keys()))
                            print('DEBUG: hotel edit category raw =', repr(request.form.get('category')))
                        except Exception:
                            pass
                        cat_val = (request.form.get('category') or '').strip()
                        if cat_val:
                            update_data['category'] = cat_val
                            try:
                                print('DEBUG: update_data[category] =', repr(update_data.get('category')))
                            except Exception:
                                pass
                except Exception:
                    pass

                # parse amenities
                amenities_raw = request.form.get('amenities') or ''
                try:
                    import json
                    parsed = json.loads(amenities_raw)
                    if isinstance(parsed, list):
                        update_data['amenities'] = parsed
                except Exception:
                    update_data['amenities'] = [a.strip() for a in amenities_raw.split(',') if a.strip()]
                if image_url:
                    update_data['image_url'] = image_url
                if gallery_urls is not None:
                    update_data['gallery_urls'] = gallery_urls

                try:
                    # Persistent debug: write the incoming form and update payload to a log file
                    try:
                        import os, json
                        os.makedirs(os.path.join(os.path.dirname(__file__), 'logs'), exist_ok=True)
                        debug_path = os.path.join(os.path.dirname(__file__), 'logs', 'hotel_last_update.json')
                        debug_dump = {
                            'timestamp': datetime.now().isoformat(),
                            'form_keys': list(request.form.keys()),
                            'form_category_raw': request.form.get('category'),
                            'hotel_column_exists_category': None,
                            'update_data': update_data
                        }
                        try:
                            debug_dump['hotel_column_exists_category'] = hotel_column_exists('category')
                        except Exception:
                            debug_dump['hotel_column_exists_category'] = 'error'
                        with open(debug_path, 'w', encoding='utf-8') as f:
                            json.dump(debug_dump, f, default=str, indent=2)
                    except Exception as _:
                        print('Could not write hotel update debug file:', _)

                    resp = supabase.table('hotels').update(update_data).eq('id', hotel_id).execute()
                    if hasattr(resp, 'error') and resp.error:
                        print('Supabase update error for hotels:', resp.error)
                        _log_hotel_error('Supabase update error for hotels', exc=resp.error, payload=update_data)
                        flash('Failed to update hotel (DB error). See server logs.', 'error')
                    else:
                        print('Hotel update response:', getattr(resp, 'data', resp))
                        flash('Hotel updated successfully!', 'success')
                except Exception as e:
                    print('Exception while updating hotel:', e)
                    _log_hotel_error('Exception while updating hotel', exc=e, payload=update_data)
                    flash(f'Failed to update hotel (exception): {str(e)}', 'error')
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
                # validate phone
                phone = request.form.get('phone')
                if phone:
                    phone_digits = re.sub(r'\D', '', phone)
                    if not phone_digits.startswith('0'):
                        flash('Phone number must start with 0 and contain only digits.', 'error')
                        return redirect(url_for('admin_restaurants_add'))
                # Prepare galleries
                image_gallery = []
                menu_gallery = []

                # If existing gallery URLs were provided via hidden form inputs (not currently used), they can be parsed here.
                # Process main featured (single) and gallery files via helper
                if 'image' in request.files:
                    file = request.files['image']
                    if file and file.filename:
                        file_ext = file.filename.rsplit('.', 1)[-1].lower()
                        file_bytes = file.read()
                        url = upload_bytes_get_url_to_bucket(file_bytes, file_ext, file.content_type, bucket='resstaurant-images', prefix='restaurants/')
                        if url:
                            image_gallery.append(url)

                if 'gallery_images' in request.files:
                    files = request.files.getlist('gallery_images')
                    for file in files:
                        if file and file.filename:
                            file_ext = file.filename.rsplit('.', 1)[-1].lower()
                            file_bytes = file.read()
                            url = upload_bytes_get_url_to_bucket(file_bytes, file_ext, file.content_type, bucket='resstaurant-images', prefix='restaurants/')
                            if url:
                                image_gallery.append(url)

                # Menu featured and gallery
                if 'menu_image' in request.files:
                    file = request.files['menu_image']
                    if file and file.filename:
                        file_ext = file.filename.rsplit('.', 1)[-1].lower()
                        file_bytes = file.read()
                        url = upload_bytes_get_url_to_bucket(file_bytes, file_ext, file.content_type, bucket='resstaurant-images', prefix='restaurants/menu/')
                        if url:
                            menu_gallery.append(url)

                if 'menu_gallery_images' in request.files:
                    files = request.files.getlist('menu_gallery_images')
                    for file in files:
                        if file and file.filename:
                            file_ext = file.filename.rsplit('.', 1)[-1].lower()
                            file_bytes = file.read()
                            url = upload_bytes_get_url_to_bucket(file_bytes, file_ext, file.content_type, bucket='resstaurant-images', prefix='restaurants/menu/')
                            if url:
                                menu_gallery.append(url)
                # Set featured single-image fields to first gallery item for backward compatibility
                image_url = image_gallery[0] if image_gallery else None
                menu_image_url = menu_gallery[0] if menu_gallery else None

                # Build base payload and only include optional image/gallery keys
                resto_data = {
                    'name': name,
                    'slug': generate_slug(name),
                    'description': request.form.get('description'),
                    'cuisine': request.form.get('cuisine'),
                    'address': request.form.get('address'),
                    'phone': request.form.get('phone'),
                    'price_range': request.form.get('price_range'),
                    'hours': request.form.get('hours'),
                    'map_embed': request.form.get('map_embed'),
                    'is_active': True
                }

                # Conditionally add image fields only when the DB table has those columns
                try:
                    if image_url and restaurant_column_exists('image_url'):
                        resto_data['image_url'] = image_url
                except Exception:
                    pass
                try:
                    if menu_image_url and restaurant_column_exists('menu_image_url'):
                        resto_data['menu_image_url'] = menu_image_url
                except Exception:
                    pass
                try:
                    if image_gallery and restaurant_column_exists('image_gallery'):
                        resto_data['image_gallery'] = image_gallery
                except Exception:
                    pass
                try:
                    if menu_gallery and restaurant_column_exists('menu_gallery'):
                        resto_data['menu_gallery'] = menu_gallery
                except Exception:
                    pass

                # Only include category if the column exists in DB
                try:
                    cat_val = request.form.get('category')
                    if cat_val and restaurant_column_exists('category'):
                        resto_data['category'] = cat_val
                except Exception:
                    pass

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
                # Include category only if DB column exists
                try:
                    cat_val = request.form.get('category')
                    if cat_val and restaurant_column_exists('category'):
                        update_data['category'] = cat_val
                except Exception:
                    pass
                # validate phone (starts with 0)
                phone = request.form.get('phone')
                if phone:
                    phone_digits = re.sub(r'\D', '', phone)
                    if not phone_digits.startswith('0'):
                        flash('Phone number must start with 0 and contain only digits.', 'error')
                        return redirect(url_for('admin_restaurants_edit', resto_id=resto_id))
                # Determine existing images to keep based on client input (if provided).
                image_gallery_existing = []
                menu_gallery_existing = []
                try:
                    main_existing_json = request.form.get('main_existing_json')
                    if main_existing_json:
                        image_gallery_existing = json.loads(main_existing_json)
                except Exception:
                    image_gallery_existing = []
                try:
                    menu_existing_json = request.form.get('menu_existing_json')
                    if menu_existing_json:
                        menu_gallery_existing = json.loads(menu_existing_json)
                except Exception:
                    menu_gallery_existing = []
                # Fallback: if client did not provide existing lists, attempt to read from DB
                if not image_gallery_existing or not menu_gallery_existing:
                    try:
                        resp = supabase.table('restaurants').select('image_gallery,menu_gallery').eq('id', resto_id).single().execute()
                        existing = resp.data or {}
                        if not image_gallery_existing:
                            image_gallery_existing = existing.get('image_gallery') or []
                        if not menu_gallery_existing:
                            menu_gallery_existing = existing.get('menu_gallery') or []
                    except Exception:
                        pass

                # Handle main uploads via helper
                new_main = []
                if 'image' in request.files:
                    file = request.files['image']
                    if file and file.filename:
                        file_ext = file.filename.rsplit('.', 1)[-1].lower()
                        file_bytes = file.read()
                        url = upload_bytes_get_url_to_bucket(file_bytes, file_ext, file.content_type, bucket='resstaurant-images', prefix='restaurants/')
                        if url:
                            new_main.append(url)
                if 'gallery_images' in request.files:
                    files = request.files.getlist('gallery_images')
                    for file in files:
                        if file and file.filename:
                            file_ext = file.filename.rsplit('.', 1)[-1].lower()
                            file_bytes = file.read()
                            url = upload_bytes_get_url_to_bucket(file_bytes, file_ext, file.content_type, bucket='resstaurant-images', prefix='restaurants/')
                            if url:
                                new_main.append(url)
                # Combine existing + new
                combined_main = list(image_gallery_existing) + new_main
                if combined_main:
                    try:
                        if restaurant_column_exists('image_gallery'):
                            update_data['image_gallery'] = combined_main
                    except Exception:
                        pass
                    try:
                        if restaurant_column_exists('image_url'):
                            update_data['image_url'] = combined_main[0]
                    except Exception:
                        pass
                # Menu uploads via helper
                new_menu = []
                if 'menu_image' in request.files:
                    file = request.files['menu_image']
                    if file and file.filename:
                        file_ext = file.filename.rsplit('.', 1)[-1].lower()
                        file_bytes = file.read()
                        url = upload_bytes_get_url_to_bucket(file_bytes, file_ext, file.content_type, bucket='resstaurant-images', prefix='restaurants/menu/')
                        if url:
                            new_menu.append(url)
                if 'menu_gallery_images' in request.files:
                    files = request.files.getlist('menu_gallery_images')
                    for file in files:
                        if file and file.filename:
                            file_ext = file.filename.rsplit('.', 1)[-1].lower()
                            file_bytes = file.read()
                            url = upload_bytes_get_url_to_bucket(file_bytes, file_ext, file.content_type, bucket='resstaurant-images', prefix='restaurants/menu/')
                            if url:
                                new_menu.append(url)
                combined_menu = list(menu_gallery_existing) + new_menu
                if combined_menu:
                    try:
                        if restaurant_column_exists('menu_gallery'):
                            update_data['menu_gallery'] = combined_menu
                    except Exception:
                        pass
                    try:
                        if restaurant_column_exists('menu_image_url'):
                            update_data['menu_image_url'] = combined_menu[0]
                    except Exception:
                        pass
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
    report_history = []
    if supabase:
        try:
            resp = supabase.table('blog_reports').select('*, blogs(id, title, author, is_archived, status)').order('created_at', desc=True).execute()
            rows = resp.data or []

            # Aggregate by blog_id
            groups = {}
            for r in rows:
                blog = r.get('blogs') or {}
                bid = r.get('blog_id')
                if bid not in groups:
                    groups[bid] = {
                        'blog_id': bid,
                        'title': blog.get('title'),
                        'author': blog.get('author'),
                        'is_archived': blog.get('is_archived'),
                        'status': blog.get('status'),
                        'total_reports': 0,
                        'reasons': {},
                        'last_reported_at': None,
                        'reporters': [],
                        'latest_description': None,
                        'latest_report_id': None
                    }
                g = groups[bid]
                g['total_reports'] += 1
                reason = r.get('reason') or r.get('category') or 'other'
                g['reasons'][reason] = g['reasons'].get(reason, 0) + 1
                created = r.get('created_at')
                # Keep latest report info
                if created and (not g['last_reported_at'] or created > g['last_reported_at']):
                    g['last_reported_at'] = created
                    g['latest_description'] = r.get('description')
                    g['latest_report_id'] = r.get('id')
                rep = r.get('reporter_ip') or r.get('reporter') or None
                if rep and rep not in g['reporters']:
                    g['reporters'].append(rep)

            # Separate current and history
            for g in groups.values():
                if g['is_archived'] or (g['status'] in ['inactive', 'rejected']):
                    report_history.append(g)
                else:
                    reports.append(g)

            # Sort both lists
            reports = sorted(reports, key=lambda x: x['last_reported_at'] or '', reverse=True)
            report_history = sorted(report_history, key=lambda x: x['last_reported_at'] or '', reverse=True)

        except Exception as e:
            print(f"Error fetching reports: {e}")

    return render_template('admin/reports.html', reports=reports, report_history=report_history)

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
# ============================================
# BLOG VOTING API
# ============================================


@app.route('/plan/blog/<int:blog_id>/votes', methods=['GET'])
def get_blog_votes(blog_id):
    if not supabase:
        print('Supabase not initialized')
        return jsonify({'error': 'Database unavailable'}), 500
    user_id = session.get('user_id')
    voter_ip = request.remote_addr
    try:
        upvotes_rows = supabase.table('blog_votes').select('id').eq('blog_id', blog_id).eq('vote_type', 'up').execute().data or []
        downvotes_rows = supabase.table('blog_votes').select('id').eq('blog_id', blog_id).eq('vote_type', 'down').execute().data or []
        user_vote = None
        if user_id:
            user_vote_rows = supabase.table('blog_votes').select('vote_type').eq('blog_id', blog_id).eq('voter_id', user_id).execute().data
            if user_vote_rows and len(user_vote_rows) > 0:
                user_vote = user_vote_rows[0].get('vote_type')
        else:
            user_vote_rows = supabase.table('blog_votes').select('vote_type').eq('blog_id', blog_id).eq('voter_ip', voter_ip).execute().data
            if user_vote_rows and len(user_vote_rows) > 0:
                user_vote = user_vote_rows[0].get('vote_type')
        return jsonify({
            'upvotes': len(upvotes_rows),
            'downvotes': len(downvotes_rows),
            'user_vote': user_vote
        })
    except Exception as e:
        import traceback
        print('Vote fetch error:', e)
        traceback.print_exc()
        return jsonify({'error': f'Failed to fetch votes: {e}'}), 500


@app.route('/plan/blog/<int:blog_id>/vote', methods=['POST'])
def vote_blog(blog_id):
    if not supabase:
        return jsonify({'error': 'Database unavailable'}), 500
    data = request.get_json()
    vote_type = None
    if data:
        vote_type = data.get('vote_type')
    # allow None for unvote
    if vote_type not in ['up', 'down', None]:
        return jsonify({'error': 'Invalid vote type'}), 400
    user_id = session.get('user_id')
    voter_ip = request.remote_addr
    try:
        # Find existing vote
        if user_id:
            existing_rows = supabase.table('blog_votes').select('id', 'vote_type').eq('blog_id', blog_id).eq('voter_id', user_id).execute().data
        else:
            existing_rows = supabase.table('blog_votes').select('id', 'vote_type').eq('blog_id', blog_id).eq('voter_ip', voter_ip).execute().data
        existing = existing_rows[0] if existing_rows and len(existing_rows) > 0 else None
        if existing:
            prev_vote = existing.get('vote_type')
            if prev_vote == vote_type or vote_type is None:
                # Unvote: delete the vote
                supabase.table('blog_votes').delete().eq('id', existing.get('id')).execute()
            else:
                # Change vote
                supabase.table('blog_votes').update({'vote_type': vote_type}).eq('id', existing.get('id')).execute()
        else:
            if vote_type in ['up', 'down']:
                vote_data = {'blog_id': blog_id, 'vote_type': vote_type, 'created_at': datetime.utcnow().isoformat()}
                if user_id:
                    vote_data['voter_id'] = user_id
                else:
                    vote_data['voter_ip'] = voter_ip
                supabase.table('blog_votes').insert(vote_data).execute()
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error submitting vote: {e}")
        return jsonify({'error': 'Failed to submit vote'}), 500


@app.route('/plan/blog/<int:blog_id>/report', methods=['POST'])
def api_blog_report(blog_id):
    if not supabase:
        return jsonify({'success': False, 'error': 'Database unavailable'}), 500
    # Accept JSON or form-encoded submissions
    data = request.get_json(silent=True) or request.form.to_dict() or {}
    if not data:
        return jsonify({'success': False, 'error': 'Invalid request payload'}), 400
    # Map incoming 'category' -> 'reason' to match DB schema (blog_reports.reason)
    category = data.get('category') or data.get('reason')
    description = data.get('description', '')
    reporter_ip = request.remote_addr
    if not category:
        return jsonify({'success': False, 'error': 'Category is required'}), 400
    try:
        report_data = {
            'blog_id': blog_id,
            'reason': category,
            'description': description,
            'reporter_ip': reporter_ip
        }
        # Insert into blog_reports table
        supabase.table('blog_reports').insert(report_data).execute()
        # Optionally update blog's report count/flag
        blog = supabase.table('blogs').select('report_count').eq('id', blog_id).single().execute()
        if blog.data:
            supabase.table('blogs').update({
                'is_reported': True,
                'report_count': (blog.data.get('report_count') or 0) + 1
            }).eq('id', blog_id).execute()
        return jsonify({'success': True, 'message': 'Thank you for your report. Our team will review it.'})
    except Exception as e:
        import traceback
        print(f"Error reporting blog: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': 'Failed to submit report.'}), 500


# ============================================
# RUN APP
# ============================================

if __name__ == '__main__':
    app.run(debug=True)
