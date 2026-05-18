import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from app import create_app, db
from app.models.user import User

app = create_app('development')
with app.app_context():
    u = User.query.filter_by(username='admin').first()
    if u:
        u.set_password('admin123')
        db.session.commit()
        print('Password reset OK for admin')
    else:
        u = User(username='admin', email='admin@kubetrain.local', role='admin', is_active=True)
        u.set_password('admin123')
        db.session.add(u)
        db.session.commit()
        print('Admin user created')
