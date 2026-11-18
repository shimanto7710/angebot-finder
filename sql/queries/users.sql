-- name: create_user(user_id, email, name, password_hash)!
INSERT INTO users (id, email, name, password_hash)
VALUES (:user_id, :email, :name, :password_hash);

-- name: user_by_id(user_id)
SELECT id, name, email, created_at
FROM users
WHERE id = :user_id;

-- name: user_credentials_by_email(email)
SELECT id, password_hash
FROM users
WHERE email = :email;
