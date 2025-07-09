import logging
from functools import wraps

import yaml
from bson import ObjectId
from flask import (
    Flask,
    Response,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_pymongo import PyMongo
from werkzeug.security import check_password_hash, generate_password_hash

from converter import GraphConvertConfig, MermaidJSFlowchartTemplate, convert_str_graph

app = Flask(__name__)

with open("config.yml", "r") as ymlfile:
    cfg = yaml.safe_load(ymlfile)

app.config["MONGO_URI"] = cfg["mongodb"]["uri"]
app.secret_key = cfg["app"]["secret_key"]

mongo = PyMongo(app)


# ---------- Helper: Login Required Decorator ----------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "username" not in session:
            flash("Please login first", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated_function


# ---------- Home / Index ----------


@app.route("/")
def index():
    if "username" in session:
        return redirect(url_for("dashboard"))
    # For unauthenticated users: show only annotated (non "Not Annotated") data
    annotations = list(mongo.db.annotations.find({"status": {"$ne": "Not Annotated"}}))
    return render_template(
        "index.html", annotations=annotations, mode=session.get("mode", "light")
    )


@app.route("/help")
@login_required
def help():
    return render_template("help.html", mode=session.get("mode", "light"))


# ---------- Login / Logout ----------


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        user = mongo.db.users.find_one({"username": username})
        if user and check_password_hash(user["password"], password):
            session["username"] = username
            session["role"] = user.get("role", "annotator")
            flash("Logged in successfully", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid credentials", "danger")
    return render_template("login.html", mode=session.get("mode", "light"))


@app.route("/logout")
@login_required
def logout():
    session.clear()
    flash("Logged out", "info")
    return redirect(url_for("login"))


# ---------- Dashboard for Annotators ----------


@app.route("/dashboard")
@login_required
def dashboard():
    # Redirect admin users to a separate admin dashboard
    if session["role"] == "admin":
        return redirect(url_for("admin_dashboard"))

    # For annotators: list tasks (datasets) and their annotation statuses
    tasks = list(mongo.db.tasks.find())

    for task in tasks:
        template_annotations = list(
            mongo.db.annotations.find({"task_id": task["_id"], "template": True})
        )
        total = len(template_annotations)

        annotations = list(
            mongo.db.annotations.find(
                {"task_id": task["_id"], "annotator": session["username"]}
            )
        )

        counts = {"Not Annotated": 0, "In Progress": 0, "Finalized": 0}

        for ann in annotations:
            counts[ann["status"]] = counts.get(ann["status"], 0) + 1

        task["annotation_counts"] = counts
        task["total"] = total

    return render_template(
        "dashboard.html", tasks=tasks, mode=session.get("mode", "light")
    )


# ---------- Dataset Page ----------


@app.route("/dataset")
def dataset():
    # grab selected dataset (task) if any
    selected_task_id = request.args.get("task_id")
    # load all tasks so we can let the user choose one
    tasks = list(mongo.db.tasks.find())

    # build base filter: if a task_id was passed, only that dataset
    query = {}

    if selected_task_id:
        from bson import ObjectId

        try:
            query["task_id"] = ObjectId(selected_task_id)
        except:
            flash("Invalid dataset selected", "danger")
            return redirect(url_for("dataset"))

    if "username" in session:
        if session["role"] != "admin":
            # For annotators, merge the templates with any existing annotation records for the user.
            template_annotations = list(
                mongo.db.annotations.find({**query, "template": True})
            )
            user_annotations = list(
                mongo.db.annotations.find(
                    {**query, "annotator": session["username"], "template": False}
                )
            )
            samples = {}

            for t in template_annotations:
                samples[t["sample_id"]] = t

            for ua in user_annotations:
                samples[ua["sample_id"]] = ua

            annotations = list(samples.values())
        else:
            # Admin sees only the template records.
            annotations = list(mongo.db.annotations.find({**query, "template": True}))
    else:
        # Unauthenticated users see only annotated data.
        annotations = list(
            mongo.db.annotations.find(
                {**query, "template": True, "status": {"$ne": "Not Annotated"}}
            )
        )

    return render_template(
        "dataset.html",
        tasks=tasks,
        selected_task_id=selected_task_id,
        annotations=annotations,
        mode=session.get("mode", "light"),
    )


@app.route("/annotate/<sample_id>", methods=["GET", "POST"])
@login_required
def annotate(sample_id):
    # Check if there's an annotation record for this sample for the current annotator.
    annotation = mongo.db.annotations.find_one(
        {"sample_id": sample_id, "annotator": session["username"]}
    )

    if not annotation:
        # Clone the template record for this sample.
        template = mongo.db.annotations.find_one(
            {"sample_id": sample_id, "template": True}
        )
        template.pop("_id")
        template.update(
            {
                "annotator": session["username"],
                "template": False,
                "nodes": {
                    "Sufficiency": [],
                    "Completeness": [],
                    "Hallucinations": [],
                    "Verbosity": [],
                },
                "notes": "",
            }
        )
        oid = mongo.db.annotations.insert_one(template).inserted_id
        annotation = mongo.db.annotations.find_one({"_id": oid})

    mm_template = MermaidJSFlowchartTemplate(enable_links=True)
    g_config = GraphConvertConfig(
        outside_members=True, hide_empty_members=True, graph_template=mm_template
    )

    diagram = (
        annotation["diagram"]
        .replace("click", "cliсk")
        .replace("constructor", "construсtor")
        .replace("toString", "tоString")
    )

    annotation["diagram"] = convert_str_graph(diagram, g_config).replace("\t", "    ")

    if request.method == "POST":
        data = request.get_json()
        action = data.get("action")
        nodes_map = data.get("nodes", {})
        missing = data.get("missing", [])
        notes = data.get("notes", "")
        status = "Finalized" if action == "finalize" else "In Progress"

        # save everything
        logging.info(
            f'Saving {annotation["_id"]}, setting {nodes_map}, status {status}'
        )

        mongo.db.annotations.update_one(
            {"_id": annotation["_id"]},
            {
                "$set": {
                    "nodes": nodes_map,
                    "missing": missing,
                    "notes": notes,
                    "status": status,
                }
            },
        )
        flash("Annotation saved", "success")

        # Save or Finalize go back to dataset
        message = "Annotation {}.".format(
            "finalized" if action == "finalize" else "saved"
        )
        logging.info(message)
        flash(message, "success")

        if action == "finalize":
            task_id = annotation["task_id"]
            return redirect(url_for("dataset", task_id=task_id))
        else:
            return render_template(
                "annotate.html",
                annotation=annotation,
                mode=session.get("mode", "light"),
            )

    return render_template(
        "annotate.html", annotation=annotation, mode=session.get("mode", "light")
    )


# ---------- Admin Routes ----------
@app.route("/admin")
@login_required
def admin_dashboard():
    if session["role"] != "admin":
        flash("Unauthorized", "danger")
        return redirect(url_for("dashboard"))

    tasks = list(mongo.db.tasks.find())

    return render_template(
        "admin_dashboard.html", tasks=tasks, mode=session.get("mode", "light")
    )


@app.route("/admin/upload", methods=["GET", "POST"])
@login_required
def admin_upload():
    if session["role"] != "admin":
        flash("Unauthorized", "danger")
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        task_name = request.form.get("task_name")
        file = request.files.get("dataset_file")
        if not task_name or not file:
            flash("Task name and dataset file are required.", "danger")
            return redirect(url_for("admin_upload"))
        try:
            import json

            data = json.load(file)
        except Exception as e:
            flash("Failed to load JSON: " + str(e), "danger")
            return redirect(url_for("admin_upload"))
        # Create a new task entry.
        task_id = mongo.db.tasks.insert_one({"name": task_name}).inserted_id
        from bson import ObjectId

        # For each dataset entry, create a template annotation entry.
        for item in data:
            sample_id = str(ObjectId())
            mongo.db.annotations.insert_one(
                {
                    "task_id": task_id,
                    "sample_id": sample_id,
                    "language": item.get("language"),
                    "code": item.get("code"),
                    "repo": item.get("repo"),
                    "path": item.get("path"),
                    "query": item.get("query"),
                    "diagram": item.get("diagram"),
                    "version": item.get("version"),
                    "text_answer": item.get("text_answer"),
                    "nodes": "",
                    "notes": "",
                    "status": "Not Annotated",
                    "annotator": "",
                    "template": True,
                }
            )
        flash("Task uploaded successfully", "success")
        return redirect(url_for("admin_dashboard"))
    return render_template("upload.html", mode=session.get("mode", "light"))


@app.route("/admin/create_user", methods=["GET", "POST"])
@login_required
def create_user():
    if session["role"] != "admin":
        flash("Unauthorized", "danger")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        role = request.form.get("role", "annotator")
        hashed_pw = generate_password_hash(password)
        mongo.db.users.insert_one(
            {"username": username, "password": hashed_pw, "role": role}
        )
        flash("User created", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("create_user.html", mode=session.get("mode", "light"))


@app.route("/admin/view_annotations")
@login_required
def admin_view_annotations():
    if session["role"] != "admin":
        flash("Unauthorized", "danger")
        return redirect(url_for("dashboard"))

    annotations = list(mongo.db.annotations.find())
    return render_template(
        "admin_annotations.html",
        annotations=annotations,
        mode=session.get("mode", "light"),
    )


@app.route("/admin/manage_users", methods=["GET", "POST"])
@login_required
def manage_users():
    if session["role"] != "admin":
        flash("Unauthorized", "danger")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        # Create a new user from the form input.
        username = request.form.get("username")
        password = request.form.get("password")
        role = request.form.get("role", "annotator")

        if not username or not password:
            flash("Username and password are required", "danger")
            return redirect(url_for("manage_users"))

        hashed_pw = generate_password_hash(password)
        mongo.db.users.insert_one(
            {"username": username, "password": hashed_pw, "role": role}
        )
        flash("User created", "success")
        return redirect(url_for("manage_users"))

    users = list(mongo.db.users.find())
    return render_template(
        "manage_users.html", users=users, mode=session.get("mode", "light")
    )


@app.route("/admin/manage_users/upgrade/<user_id>")
@login_required
def upgrade_user(user_id):
    if session["role"] != "admin":
        flash("Unauthorized", "danger")
        return redirect(url_for("dashboard"))

    mongo.db.users.update_one({"_id": ObjectId(user_id)}, {"$set": {"role": "admin"}})
    flash("User upgraded to admin", "success")
    return redirect(url_for("manage_users"))


@app.route("/admin/manage_users/delete/<user_id>")
@login_required
def delete_user(user_id):
    if session["role"] != "admin":
        flash("Unauthorized", "danger")
        return redirect(url_for("dashboard"))

    user_to_delete = mongo.db.users.find_one({"_id": ObjectId(user_id)})

    if user_to_delete and user_to_delete["username"] == session["username"]:
        flash("You cannot delete yourself", "danger")
        return redirect(url_for("manage_users"))

    mongo.db.users.delete_one({"_id": ObjectId(user_id)})
    flash("User deleted", "success")
    return redirect(url_for("manage_users"))


@app.route("/admin/manage_tasks/delete/<task_id>")
@login_required
def delete_task(task_id):
    if session["role"] != "admin":
        flash("Unauthorized", "danger")
        return redirect(url_for("dashboard"))

    # Remove all annotations associated with this task
    mongo.db.annotations.delete_many({"task_id": ObjectId(task_id)})
    # Remove the task
    mongo.db.tasks.delete_one({"_id": ObjectId(task_id)})
    flash("Task removed", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/export_annotations")
@login_required
def export_annotations():
    if session["role"] != "admin":
        flash("Unauthorized", "danger")
        return redirect(url_for("dashboard"))
    import csv
    import io

    annotations = list(mongo.db.annotations.find())
    output = io.StringIO()
    writer = csv.writer(output)
    # Define the header (include any fields you need)
    header = [
        "_id",
        "sample_id",
        "task_id",
        "annotator",
        "language",
        "code",
        "repo",
        "path",
        "query",
        "diagram",
        "version",
        "text_answer",
        "nodes",
        "notes",
        "status",
        "template",
    ]
    writer.writerow(header)
    for ann in annotations:
        row = [
            str(ann.get("_id", "")),
            ann.get("sample_id", ""),
            str(ann.get("task_id", "")),
            ann.get("annotator", ""),
            ann.get("language", ""),
            ann.get("code", "").replace("\n", "\\n"),
            ann.get("repo", ""),
            ann.get("path", ""),
            ann.get("query", ""),
            ann.get("diagram", ""),
            ann.get("version", ""),
            ann.get("text_answer", ""),
            ann.get("nodes", ""),
            ann.get("notes", ""),
            ann.get("status", ""),
            str(ann.get("template", "")),
        ]
        writer.writerow(row)
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=annotations.csv"},
    )


@app.route("/toggle_theme")
def toggle_theme():
    current = session.get("mode", "light")
    logging.debug(f"Switching the theme from [{current}] to another ")
    session["mode"] = "dark" if current == "light" else "light"
    return redirect(request.referrer)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    app.run(debug=True, host=cfg["app"]["host"], port=cfg["app"]["port"])
