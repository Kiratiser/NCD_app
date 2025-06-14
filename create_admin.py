# create_admin.py
from NCD_MAX import app, db, User

def create_admin():
    """
    สคริปต์สำหรับสร้าง user คนแรก (Admin)
    """
    with app.app_context():
        # ตรวจสอบว่ามี user ในระบบแล้วหรือยัง
        if User.query.first():
            print("An admin user already exists.")
            return

        print("Creating the first admin user...")
        try:
            # ถามชื่อและรหัสผ่านจาก Command Line
            username = input("Enter admin username: ")
            password = input("Enter admin password: ")

            if not username or not password:
                print("Username and password cannot be empty.")
                return

            # สร้าง user และเข้ารหัสรหัสผ่าน
            admin_user = User(username=username)
            admin_user.set_password(password)
            
            db.session.add(admin_user)
            db.session.commit()
            print(f"Admin user '{username}' created successfully!")

        except Exception as e:
            print(f"An error occurred: {e}")
            db.session.rollback()

if __name__ == '__main__':
    create_admin()