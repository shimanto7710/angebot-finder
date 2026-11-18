# Postman

1. Import both JSON files in this folder.
2. Select **AngebotFinder DE Local** as the active environment.
3. Fill in `name`, `email`, and `password`, or enter them directly in the request body.
4. Send **Register** once, then **Login** and **My profile**.
5. Use the Chat, Offers, and Android data requests.

Login saves `access_token`; registration and My profile save `user_id`. Run Login
and My profile again when switching accounts. Tokens expire after 30 minutes.
Register and Login use the JSON body as entered. The chat request reads `question`
and `user_id` from the environment; offer filters can be edited in **Params**.

PostgreSQL and the API must be running. Chat also needs prepared embeddings and
cached models. The Android endpoint returns data, not model weights.

Keep passwords and tokens local. Do not commit a populated environment export.
