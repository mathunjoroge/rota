from werkzeug.security import generate_password_hash

# Sample plaintext password (replace with your desired password)
plaintext_password = "SecurePassword123"

# Generate hashed password
hashed_password = generate_password_hash(plaintext_password, method='pbkdf2:sha256')

# Print the hashed password
print("Hashed Password:", hashed_password)