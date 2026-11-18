-- name: recent_turns(user_id, limit)
SELECT id, question, answer, created_at
FROM (
    SELECT id, question, answer, created_at
    FROM chat_turns
    WHERE user_id = :user_id
    ORDER BY id DESC
    LIMIT :limit
) AS recent
ORDER BY id;

-- name: save_turn(user_id, question, answer)!
INSERT INTO chat_turns (user_id, question, answer)
VALUES (:user_id, :question, :answer);
