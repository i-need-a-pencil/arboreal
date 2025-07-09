import sys

from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

if __name__ == "__main__":

    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <old_username> <new_username>")
        sys.exit(1)

    old_username, new_username = sys.argv[1], sys.argv[2]

    client = MongoClient("mongodb://localhost:27017/annotationdb")
    db = client.get_default_database()

    # ensure the new user doesn't already exist
    if db.users.find_one({"username": new_username}):
        print(f"Error: user {new_username!r} already exists.")
        sys.exit(1)

    # fetch the old user document
    old_user = db.users.find_one({"username": old_username})
    if not old_user:
        print(f"Error: no such user {old_username!r}")
        sys.exit(1)

    # clone the user record
    new_user = {
        "username": new_username,
        "password": old_user["password"],  # same hash
        "role": old_user.get("role", "annotator"),
    }
    res = db.users.insert_one(new_user)
    print(
        f"✅ Cloned user {old_username!r} → {new_username!r} (new _id={res.inserted_id})"
    )

    # clone all that user's non-template annotations
    query = {"annotator": old_username, "template": False}
    cursor = db.annotations.find(query)
    count = 0

    for ann in cursor:
        ann_copy = dict(ann)
        ann_copy.pop("_id")  # drop old primary key
        ann_copy["annotator"] = new_username
        try:
            db.annotations.insert_one(ann_copy)
            count += 1
        except DuplicateKeyError:
            pass

    print(f"Cloned {count} annotations from {old_username!r} to {new_username!r}")
