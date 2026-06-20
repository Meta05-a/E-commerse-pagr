import os
from flask import Flask, render_template, redirect, url_for, request, flash, session
from flask_login import (
    LoginManager, login_user, logout_user, login_required, current_user
)
from models import db, User, Product, Order, OrderItem

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE_DIR, "shop.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)

    login_manager = LoginManager()
    login_manager.login_view = "login"
    login_manager.login_message = "Sign in to continue."
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

   

    @app.route("/")
    def index():
        return redirect(url_for("dashboard") if current_user.is_authenticated else url_for("login"))

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            username = request.form.get("username", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            confirm = request.form.get("confirm", "")

            error = None
            if not username or not email or not password:
                error = "All fields are required."
            elif password != confirm:
                error = "Passwords don't match."
            elif len(password) < 6:
                error = "Password must be at least 6 characters."
            elif User.query.filter_by(username=username).first():
                error = "That username is taken."
            elif User.query.filter_by(email=email).first():
                error = "An account with that email already exists."

            if error:
                flash(error, "error")
                return render_template("register.html", username=username, email=email)

            user = User(username=username, email=email)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash("Account created. Welcome in.", "success")
            return redirect(url_for("dashboard"))

        return render_template("register.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            identifier = request.form.get("identifier", "").strip().lower()
            password = request.form.get("password", "")

            user = User.query.filter(
                (User.username == identifier) | (User.email == identifier)
            ).first()

            if user and user.check_password(password):
                login_user(user)
                flash("Signed in.", "success")
                next_page = request.args.get("next")
                return redirect(next_page or url_for("dashboard"))

            flash("Incorrect username/email or password.", "error")

        return render_template("login.html")

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        flash("Signed out.", "success")
        return redirect(url_for("login"))

    # ---------- dashboard ----------

    @app.route("/dashboard")
    @login_required
    def dashboard():
        orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).all()
        total_spent_cents = sum(o.total_cents for o in orders)
        recent_orders = orders[:5]
        cart_count = sum(item["quantity"] for item in session.get("cart", {}).values())

        return render_template(
            "dashboard.html",
            order_count=len(orders),
            total_spent=total_spent_cents / 100,
            recent_orders=recent_orders,
            cart_count=cart_count,
            product_count=Product.query.count(),
        )

    # ---------- products & cart ----------

    @app.route("/products")
    @login_required
    def products():
        items = Product.query.order_by(Product.name).all()
        return render_template("products.html", products=items)

    @app.route("/cart/add/<int:product_id>", methods=["POST"])
    @login_required
    def add_to_cart(product_id):
        product = db.session.get(Product, product_id)
        if not product:
            flash("That product no longer exists.", "error")
            return redirect(url_for("products"))

        qty = max(1, int(request.form.get("quantity", 1)))
        cart = session.get("cart", {})
        key = str(product_id)
        current_qty = cart.get(key, {}).get("quantity", 0)
        cart[key] = {"quantity": current_qty + qty}
        session["cart"] = cart
        flash(f"Added {product.name} to cart.", "success")
        return redirect(url_for("products"))

    @app.route("/cart")
    @login_required
    def cart():
        cart = session.get("cart", {})
        line_items = []
        subtotal_cents = 0
        for product_id, entry in cart.items():
            product = db.session.get(Product, int(product_id))
            if not product:
                continue
            quantity = entry["quantity"]
            line_total = product.price_cents * quantity
            subtotal_cents += line_total
            line_items.append({
                "product": product,
                "quantity": quantity,
                "line_total": line_total / 100,
            })
        return render_template("cart.html", line_items=line_items, subtotal=subtotal_cents / 100)

    @app.route("/cart/update/<int:product_id>", methods=["POST"])
    @login_required
    def update_cart(product_id):
        cart = session.get("cart", {})
        key = str(product_id)
        qty = int(request.form.get("quantity", 1))
        if key in cart:
            if qty <= 0:
                cart.pop(key)
            else:
                cart[key]["quantity"] = qty
            session["cart"] = cart
        return redirect(url_for("cart"))

    @app.route("/cart/remove/<int:product_id>", methods=["POST"])
    @login_required
    def remove_from_cart(product_id):
        cart = session.get("cart", {})
        cart.pop(str(product_id), None)
        session["cart"] = cart
        return redirect(url_for("cart"))

    # ---------- checkout ----------

    @app.route("/checkout", methods=["GET", "POST"])
    @login_required
    def checkout():
        cart = session.get("cart", {})
        if not cart:
            flash("Your cart is empty.", "error")
            return redirect(url_for("products"))

        line_items = []
        subtotal_cents = 0
        for product_id, entry in cart.items():
            product = db.session.get(Product, int(product_id))
            if not product:
                continue
            quantity = entry["quantity"]
            line_total = product.price_cents * quantity
            subtotal_cents += line_total
            line_items.append({"product": product, "quantity": quantity, "line_total": line_total / 100})

        if request.method == "POST":
            order = Order(user_id=current_user.id, total_cents=subtotal_cents, status="placed")
            db.session.add(order)
            db.session.flush()  # get order.id before commit

            for li in line_items:
                product = li["product"]
                db.session.add(OrderItem(
                    order_id=order.id,
                    product_id=product.id,
                    product_name=product.name,
                    unit_price_cents=product.price_cents,
                    quantity=li["quantity"],
                ))
                # naive stock decrement, floor at 0
                product.stock = max(0, product.stock - li["quantity"])

            db.session.commit()
            session["cart"] = {}
            flash(f"Order {order.reference} placed.", "success")
            return redirect(url_for("order_detail", order_id=order.id))

        return render_template("checkout.html", line_items=line_items, subtotal=subtotal_cents / 100)

    # ---------- orders ----------

    @app.route("/orders")
    @login_required
    def orders():
        all_orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).all()
        return render_template("orders.html", orders=all_orders)

    @app.route("/orders/<int:order_id>")
    @login_required
    def order_detail(order_id):
        order = db.session.get(Order, order_id)
        if not order or order.user_id != current_user.id:
            flash("Order not found.", "error")
            return redirect(url_for("orders"))
        return render_template("order_detail.html", order=order)

    return app


def seed_products():
    if Product.query.count() > 0:
        return
    sample = [
        Product(name="Field Notebook", description="Dot-grid, 96 pages, stitched binding.", price_cents=1400, stock=120, sku="FN-001"),
        Product(name="Brass Compass", description="Pocket compass with engraved lid.", price_cents=3200, stock=45, sku="BC-002"),
        Product(name="Canvas Tote", description="14oz waxed canvas, leather straps.", price_cents=2800, stock=80, sku="CT-003"),
        Product(name="Enamel Mug", description="12oz, chip-resistant rim.", price_cents=950, stock=200, sku="EM-004"),
        Product(name="Wool Blanket", description="Merino blend, 50x70 in.", price_cents=8900, stock=30, sku="WB-005"),
        Product(name="Trail Map Set", description="Set of 3 regional topographic maps.", price_cents=2200, stock=60, sku="TM-006"),
    ]
    db.session.bulk_save_objects(sample)
    db.session.commit()


app = create_app()

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        seed_products()
    app.run(debug=True, host="0.0.0.0", port=5000)