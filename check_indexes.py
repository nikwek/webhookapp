from app import create_app, db

def check_indexes():
    app = create_app()
    with app.app_context():
        # Check indexes on webhook_logs table
        result = db.engine.execute("PRAGMA index_list('webhook_logs')").fetchall()
        print("Indexes on webhook_logs table:")
        for idx in result:
            print(idx)
        
        # If indexes found, get more details
        if result:
            for idx in result:
                index_name = idx[1]
                print(f"\nColumns in index {index_name}:")
                details = db.engine.execute(f"PRAGMA index_info('{index_name}')").fetchall()
                for col in details:
                    print(col)
        else:
            print("No indexes found on webhook_logs table.")

if __name__ == "__main__":
    check_indexes()