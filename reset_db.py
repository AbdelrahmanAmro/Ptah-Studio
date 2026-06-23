from app import app, db, User

def reset_system():
    print("⏳ Starting System Reset...")
    
    with app.app_context():
        # 1. DROP ALL TABLES (This fixes the Unique Constraint error)
        db.drop_all()
        print("🗑️  Old database tables dropped.")

        # 2. CREATE FRESH TABLES (With the new 'role' column)
        db.create_all()
        print("✅ New tables created.")
        
        # 3. Create SUPER ADMIN (Full Access)
        super_admin = User(
            name='Super Admin',
            email='admin@ptah.com',
            role='super_admin',
            is_admin=True
        )
        super_admin.set_password('123456')
        db.session.add(super_admin)
        
        # 4. Create EMPLOYEE (Restricted Access)
        employee = User(
            name='Hossam',
            email='hossam@ptah.com',
            role='employee',
            is_admin=True
        )
        employee.set_password('123456')
        db.session.add(employee)
        
        # 5. Commit
        db.session.commit()
        
        print("\n🎉 RESET COMPLETE! Login Credentials:")
        print("========================================")
        print("👤 SUPER ADMIN")
        print("   Email:    admin@ptah.com")
        print("   Password: 123456")
        print("----------------------------------------")
        print("👤 EMPLOYEE")
        print("   Email:    hossam@ptah.com")
        print("   Password: 123456")
        print("========================================")

if __name__ == '__main__':
    reset_system()