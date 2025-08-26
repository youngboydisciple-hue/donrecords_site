from flask import render_template, request, redirect, url_for, flash, current_app, session
from . import main_bp
from app import db
from models import Beat, Merchandise, BlogPost, User, UserRole
from datetime import datetime


@main_bp.route('/')
@main_bp.route('/home')
def index():
    """Home page route"""
    featured_beats = Beat.query.filter_by(is_featured=True, is_published=True).limit(6).all()
    featured_merch = Merchandise.query.filter_by(is_featured=True, is_published=True).limit(4).all()
    recent_posts = BlogPost.query.filter_by(is_published=True).order_by(BlogPost.created_at.desc()).limit(3).all()
    
    return render_template('main/index.html', 
                           featured_beats=featured_beats,
                           featured_merch=featured_merch,
                           recent_posts=recent_posts,
                           title="Don Records - Home",
                           now=datetime.utcnow())


@main_bp.route('/beats')
def beats():
    """Beats catalog page"""
    page = request.args.get('page', 1, type=int)
    genre = request.args.get('genre')
    search = request.args.get('search')
    
    query = Beat.query.filter_by(is_published=True)
    
    if genre:
        query = query.filter_by(genre=genre)
    
    if search:
        query = query.filter(Beat.title.ilike(f'%{search}%') | 
                            Beat.description.ilike(f'%{search}%') | 
                            Beat.tags.ilike(f'%{search}%'))
    
    pagination = query.order_by(Beat.created_at.desc()).paginate(
        page=page, per_page=12, error_out=False)
    
    beats = pagination.items
    genres = db.session.query(Beat.genre).distinct().all()
    
    return render_template('main/beats.html', 
                           beats=beats,
                           pagination=pagination,
                           genres=genres,
                           title="Don Records - Beats")


@main_bp.route('/beat/<int:beat_id>')
def beat_detail(beat_id):
    """Individual beat detail page"""
    beat = Beat.query.get_or_404(beat_id)
    
    if not beat.is_published:
        flash('This beat is not available.', 'warning')
        return redirect(url_for('main.beats'))
    
    # Increment play count
    beat.increment_play_count()
    
    # Get related beats
    related_beats = Beat.query.filter(
        Beat.id != beat_id,
        Beat.is_published == True,
        Beat.genre == beat.genre
    ).limit(4).all()
    
    return render_template('main/beat_detail.html', 
                           beat=beat,
                           related_beats=related_beats,
                           title=f"{beat.title} - Don Records")


@main_bp.route('/merchandise')
def merchandise():
    """Merchandise catalog page"""
    page = request.args.get('page', 1, type=int)
    category = request.args.get('category')
    search = request.args.get('search')
    
    query = Merchandise.query.filter_by(is_published=True)
    
    if category:
        query = query.filter_by(category=category)
    
    if search:
        query = query.filter(Merchandise.name.ilike(f'%{search}%') | 
                            Merchandise.description.ilike(f'%{search}%'))
    
    pagination = query.order_by(Merchandise.created_at.desc()).paginate(
        page=page, per_page=12, error_out=False)
    
    merchandise_items = pagination.items
    categories = db.session.query(Merchandise.category).distinct().all()
    
    return render_template('main/merchandise.html', 
                           merchandise_items=merchandise_items,
                           pagination=pagination,
                           categories=categories,
                           title="Don Records - Merchandise")


@main_bp.route('/merchandise/<int:merch_id>')
def merchandise_detail(merch_id):
    """Individual merchandise detail page"""
    merch = Merchandise.query.get_or_404(merch_id)
    
    if not merch.is_published:
        flash('This merchandise is not available.', 'warning')
        return redirect(url_for('main.merchandise'))
    
    # Get related merchandise
    related_merch = Merchandise.query.filter(
        Merchandise.id != merch_id,
        Merchandise.is_published == True,
        Merchandise.category == merch.category
    ).limit(4).all()
    
    return render_template('main/merchandise_detail.html', 
                           merch=merch,
                           related_merch=related_merch,
                           title=f"{merch.name} - Don Records")


@main_bp.route('/blog')
def blog():
    """Blog posts listing page"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search')
    
    query = BlogPost.query.filter_by(is_published=True)
    
    if search:
        query = query.filter(BlogPost.title.ilike(f'%{search}%') | 
                            BlogPost.content.ilike(f'%{search}%'))
    
    pagination = query.order_by(BlogPost.published_at.desc()).paginate(
        page=page, per_page=10, error_out=False)
    
    posts = pagination.items
    
    return render_template('main/blog.html', 
                           posts=posts,
                           pagination=pagination,
                           title="Don Records - Blog")


@main_bp.route('/blog/<string:slug>')
def blog_post(slug):
    """Individual blog post page"""
    post = BlogPost.query.filter_by(slug=slug).first_or_404()
    
    if not post.is_published:
        flash('This blog post is not available.', 'warning')
        return redirect(url_for('main.blog'))
    
    # Increment view count
    post.increment_view_count()
    
    # Get recent posts for sidebar
    recent_posts = BlogPost.query.filter(
        BlogPost.id != post.id,
        BlogPost.is_published == True
    ).order_by(BlogPost.published_at.desc()).limit(5).all()
    
    return render_template('main/blog_post.html', 
                           post=post,
                           recent_posts=recent_posts,
                           title=post.title)


@main_bp.route('/about')
def about():
    """About page"""
    producers = User.query.filter_by(role=UserRole.PRODUCER, is_approved=True).all()
    return render_template('main/about.html', 
                           producers=producers,
                           title="About Don Records")


@main_bp.route('/contact')
def contact():
    """Contact page"""
    return render_template('main/contact.html', title="Contact Us")


@main_bp.route('/cart')
def cart():
    """Shopping cart page"""
    cart_items = session.get('cart', [])
    total = 0
    cart_contents = []
    
    for item in cart_items:
        if item['type'] == 'beat':
            product = Beat.query.get(item['id'])
            if product and product.is_published:
                cart_contents.append({
                    'id': product.id,
                    'type': 'beat',
                    'name': product.title,
                    'price': product.price,
                    'image': product.cover_image,
                    'quantity': item['quantity']
                })
                total += product.price * item['quantity']
        elif item['type'] == 'merchandise':
            product = Merchandise.query.get(item['id'])
            if product and product.is_published:
                cart_contents.append({
                    'id': product.id,
                    'type': 'merchandise',
                    'name': product.name,
                    'price': product.price,
                    'image': product.image,
                    'quantity': item['quantity']
                })
                total += product.price * item['quantity']
    
    return render_template('main/cart.html', 
                           cart_items=cart_contents,
                           total=total,
                           title="Shopping Cart")


@main_bp.route('/add-to-cart', methods=['POST'])
def add_to_cart():
    """Add item to cart"""
    item_id = request.form.get('item_id', type=int)
    item_type = request.form.get('item_type')
    quantity = request.form.get('quantity', 1, type=int)
    
    if not all([item_id, item_type]):
        flash('Invalid request', 'danger')
        return redirect(request.referrer or url_for('main.index'))
    
    # Validate item exists
    if item_type == 'beat':
        item = Beat.query.get_or_404(item_id)
    elif item_type == 'merchandise':
        item = Merchandise.query.get_or_404(item_id)
        # Check stock
        if item.stock_quantity < quantity:
            flash(f'Sorry, only {item.stock_quantity} in stock', 'warning')
            return redirect(request.referrer or url_for('main.index'))
    else:
        flash('Invalid item type', 'danger')
        return redirect(request.referrer or url_for('main.index'))
    
    # Add to cart in session
    cart = session.get('cart', [])
    
    # Check if item already in cart
    for cart_item in cart:
        if cart_item['id'] == item_id and cart_item['type'] == item_type:
            cart_item['quantity'] += quantity
            session['cart'] = cart
            flash('Cart updated successfully', 'success')
            return redirect(request.referrer or url_for('main.index'))
    
    # Add new item to cart
    cart.append({
        'id': item_id,
        'type': item_type,
        'quantity': quantity
    })
    
    session['cart'] = cart
    flash('Item added to cart', 'success')
    return redirect(request.referrer or url_for('main.index'))


@main_bp.route('/remove-from-cart/<string:item_type>/<int:item_id>')
def remove_from_cart(item_type, item_id):
    """Remove item from cart"""
    cart = session.get('cart', [])
    
    # Find and remove item
    for i, item in enumerate(cart):
        if item['id'] == item_id and item['type'] == item_type:
            del cart[i]
            break
    
    session['cart'] = cart
    flash('Item removed from cart', 'success')
    return redirect(url_for('main.cart'))


@main_bp.route('/update-cart', methods=['POST'])
def update_cart():
    """Update cart quantities"""
    cart = session.get('cart', [])
    item_ids = request.form.getlist('item_id')
    item_types = request.form.getlist('item_type')
    quantities = request.form.getlist('quantity')
    
    # Update quantities
    for i in range(len(item_ids)):
        item_id = int(item_ids[i])
        item_type = item_types[i]
        quantity = int(quantities[i])
        
        # Find and update item
        for cart_item in cart:
            if cart_item['id'] == item_id and cart_item['type'] == item_type:
                # Validate stock for merchandise
                if item_type == 'merchandise':
                    merch = Merchandise.query.get(item_id)
                    if merch and merch.stock_quantity < quantity:
                        flash(f'Sorry, only {merch.stock_quantity} of {merch.name} in stock', 'warning')
                        quantity = merch.stock_quantity
                
                cart_item['quantity'] = quantity
                break
    
    session['cart'] = cart
    flash('Cart updated', 'success')
    return redirect(url_for('main.cart'))