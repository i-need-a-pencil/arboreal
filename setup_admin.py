import argparse
import logging
from pathlib import Path

import yaml
from pymongo import MongoClient, errors
from werkzeug.security import generate_password_hash


def load_config(path: Path) -> dict:
    """Load YAML configuration from a file."""
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_db_client(uri: str) -> MongoClient:
    """Initialize and return a MongoDB client."""
    return MongoClient(uri)


def create_admin_user(db, username: str, password: str) -> None:
    """Insert an admin user into the users collection."""
    hashed_pw = generate_password_hash(password)
    admin_user = {"username": username, "password": hashed_pw, "role": "admin"}
    try:
        db.users.insert_one(admin_user)
        logging.info("Admin user created successfully.")
    except errors.DuplicateKeyError:
        logging.warning("Admin user already exists.")
    except errors.PyMongoError as e:
        logging.error("Failed to create admin user: %s", e)
        raise


def main() -> None:
    """Main entry point for script execution."""
    parser = argparse.ArgumentParser(description="Create an admin user in MongoDB.")
    parser.add_argument(
        "--password", type=str, required=True, help="Password for the admin user"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.yml"),
        help="Path to the YAML config file",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    try:
        cfg = load_config(args.config)
        client = get_db_client(cfg["mongodb"]["uri"])
        db = client.get_default_database()
    except (yaml.YAMLError, FileNotFoundError) as e:
        logging.error("Error loading config: %s", e)
        return
    except Exception as e:
        logging.error("MongoDB connection error: %s", e)
        return

    create_admin_user(db, "admin", args.password)


if __name__ == "__main__":
    main()
