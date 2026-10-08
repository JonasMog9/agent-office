import os

# Point the app at an in-memory SQLite database before any app module creates its engine.
os.environ["DATABASE_URL"] = "sqlite://"
