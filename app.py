from flask import Flask,render_template
from models.models import db
from blueprints.org import org_bp
from blueprints.members import members_bp
from blueprints.shifts import shifts_bp
from blueprints.leave import leave_bp
from blueprints.rota import rota_bp
from blueprints.pdf import pdf_bp

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///rota.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'your_secret_key'

db.init_app(app)

with app.app_context():
    db.create_all()

# Register blueprints
app.register_blueprint(org_bp)
app.register_blueprint(members_bp)
app.register_blueprint(shifts_bp)
app.register_blueprint(leave_bp)
app.register_blueprint(rota_bp)
app.register_blueprint(pdf_bp)

@app.route('/')
def home():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)