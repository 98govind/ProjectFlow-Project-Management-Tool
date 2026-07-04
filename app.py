from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

def india_time():
    return datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)

app = Flask(__name__)
app.config["SECRET_KEY"] = "projectflow_secret_key"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///projectflow.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)


class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=india_time)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)


class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(50), default="To Do")
    assigned_to = db.Column(db.String(100))
    due_date = db.Column(db.String(50))
    comment = db.Column(db.Text)
    priority = db.Column(db.String(50), default="Medium")
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=False)


class TaskComment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    comment_text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=india_time)
    task_id = db.Column(db.Integer, db.ForeignKey("task.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)


class ActivityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=india_time)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def add_activity(project_id, action):
    activity = ActivityLog(
        action=action,
        project_id=project_id,
        user_id=current_user.id
    )
    db.session.add(activity)
    db.session.commit()


def get_due_date(task):
    if task.due_date:
        try:
            return datetime.strptime(task.due_date, "%Y-%m-%d").date()
        except:
            return None
    return None


def is_overdue(task):
    task_date = get_due_date(task)
    return task_date is not None and task.status != "Done" and task_date < date.today()


def is_due_soon(task):
    task_date = get_due_date(task)
    if task_date is None or task.status == "Done":
        return False

    today = date.today()
    soon_limit = today + timedelta(days=3)
    return today <= task_date <= soon_limit


@app.route("/")
def home():
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        email = request.form["email"].strip()
        password = generate_password_hash(request.form["password"])

        if User.query.filter_by(email=email).first():
            flash("Email already registered.")
            return redirect(url_for("register"))

        user = User(username=username, email=email, password=password)
        db.session.add(user)
        db.session.commit()
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip()
        password = request.form["password"]

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.")

    return render_template("login.html")


@app.route("/dashboard", methods=["GET", "POST"])
@login_required
def dashboard():
    if request.method == "POST":
        project = Project(
            title=request.form["title"].strip(),
            description=request.form["description"].strip(),
            owner_id=current_user.id
        )
        db.session.add(project)
        db.session.commit()
        return redirect(url_for("dashboard"))

    search = request.args.get("search", "").strip()

    all_projects = Project.query.filter_by(owner_id=current_user.id).all()
    project_ids = [project.id for project in all_projects]

    if search:
        projects = Project.query.filter(
            Project.owner_id == current_user.id,
            (Project.title.ilike(f"%{search}%")) |
            (Project.description.ilike(f"%{search}%"))
        ).all()
    else:
        projects = all_projects

    total_projects = len(all_projects)

    if project_ids:
        all_tasks = Task.query.filter(Task.project_id.in_(project_ids)).all()
    else:
        all_tasks = []

    total_tasks = len(all_tasks)
    completed_tasks = len([task for task in all_tasks if task.status == "Done"])
    todo_tasks = len([task for task in all_tasks if task.status == "To Do"])
    progress_tasks = len([task for task in all_tasks if task.status == "In Progress"])
    overdue_tasks = len([task for task in all_tasks if is_overdue(task)])
    due_soon_tasks = len([task for task in all_tasks if is_due_soon(task)])
    pending_tasks = total_tasks - completed_tasks

    overall_progress = int((completed_tasks / total_tasks) * 100) if total_tasks > 0 else 0
    todo_percent = int((todo_tasks / total_tasks) * 100) if total_tasks > 0 else 0
    progress_percent = int((progress_tasks / total_tasks) * 100) if total_tasks > 0 else 0
    done_percent = int((completed_tasks / total_tasks) * 100) if total_tasks > 0 else 0

    most_active_project = "No project yet"
    max_task_count = 0

    for project in all_projects:
        task_count = Task.query.filter_by(project_id=project.id).count()
        if task_count > max_task_count:
            max_task_count = task_count
            most_active_project = project.title

    return render_template(
        "dashboard.html",
        projects=projects,
        total_projects=total_projects,
        total_tasks=total_tasks,
        completed_tasks=completed_tasks,
        todo_tasks=todo_tasks,
        progress_tasks=progress_tasks,
        pending_tasks=pending_tasks,
        overdue_tasks=overdue_tasks,
        due_soon_tasks=due_soon_tasks,
        overall_progress=overall_progress,
        todo_percent=todo_percent,
        progress_percent=progress_percent,
        done_percent=done_percent,
        most_active_project=most_active_project,
        search=search
    )


@app.route("/project/<int:project_id>", methods=["GET", "POST"])
@login_required
def project_detail(project_id):
    project = Project.query.get_or_404(project_id)

    if project.owner_id != current_user.id:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        task = Task(
            title=request.form["title"].strip(),
            description=request.form["description"].strip(),
            assigned_to=request.form["assigned_to"].strip(),
            due_date=request.form["due_date"],
            priority=request.form["priority"],
            comment=request.form["comment"].strip(),
            project_id=project.id
        )

        db.session.add(task)
        db.session.commit()
        add_activity(project.id, f"Task created: {task.title}")

        return redirect(url_for("project_detail", project_id=project.id))

    task_search = request.args.get("task_search", "").strip()
    status_filter = request.args.get("status", "").strip()
    priority_filter = request.args.get("priority", "").strip()
    sort_filter = request.args.get("sort", "").strip()

    tasks_query = Task.query.filter_by(project_id=project.id)

    if task_search:
        tasks_query = tasks_query.filter(
            (Task.title.ilike(f"%{task_search}%")) |
            (Task.description.ilike(f"%{task_search}%")) |
            (Task.assigned_to.ilike(f"%{task_search}%")) |
            (Task.comment.ilike(f"%{task_search}%"))
        )

    if status_filter:
        tasks_query = tasks_query.filter_by(status=status_filter)

    if priority_filter:
        tasks_query = tasks_query.filter_by(priority=priority_filter)

    tasks = tasks_query.all()

    if sort_filter == "deadline":
        tasks = sorted(tasks, key=lambda task: get_due_date(task) or date.max)

    all_tasks = Task.query.filter_by(project_id=project.id).all()

    todo_count = Task.query.filter_by(project_id=project.id, status="To Do").count()
    progress_count = Task.query.filter_by(project_id=project.id, status="In Progress").count()
    done_count = Task.query.filter_by(project_id=project.id, status="Done").count()
    overdue_count = len([task for task in all_tasks if is_overdue(task)])
    due_soon_count = len([task for task in all_tasks if is_due_soon(task)])

    total_count = len(all_tasks)
    project_progress = int((done_count / total_count) * 100) if total_count > 0 else 0

    task_comments = {}
    for task in all_tasks:
        task_comments[task.id] = TaskComment.query.filter_by(
            task_id=task.id
        ).order_by(TaskComment.created_at.desc()).all()

    activities = ActivityLog.query.filter_by(
        project_id=project.id
    ).order_by(ActivityLog.created_at.desc()).limit(10).all()

    return render_template(
        "project.html",
        project=project,
        tasks=tasks,
        todo_count=todo_count,
        progress_count=progress_count,
        done_count=done_count,
        overdue_count=overdue_count,
        due_soon_count=due_soon_count,
        project_progress=project_progress,
        is_overdue=is_overdue,
        is_due_soon=is_due_soon,
        task_search=task_search,
        status_filter=status_filter,
        priority_filter=priority_filter,
        sort_filter=sort_filter,
        task_comments=task_comments,
        activities=activities
    )


@app.route("/add_comment/<int:task_id>", methods=["POST"])
@login_required
def add_comment(task_id):
    task = Task.query.get_or_404(task_id)
    project = Project.query.get_or_404(task.project_id)

    if project.owner_id != current_user.id:
        return redirect(url_for("dashboard"))

    comment_text = request.form["comment_text"].strip()

    if comment_text:
        comment = TaskComment(
            comment_text=comment_text,
            task_id=task.id,
            user_id=current_user.id
        )
        db.session.add(comment)
        db.session.commit()

        add_activity(project.id, f"Comment added on task: {task.title}")

    return redirect(url_for("project_detail", project_id=project.id))


@app.route("/edit_project/<int:project_id>", methods=["GET", "POST"])
@login_required
def edit_project(project_id):
    project = Project.query.get_or_404(project_id)

    if project.owner_id != current_user.id:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        old_title = project.title
        project.title = request.form["title"].strip()
        project.description = request.form["description"].strip()
        db.session.commit()

        add_activity(project.id, f"Project updated: {old_title}")

        return redirect(url_for("dashboard"))

    return render_template("edit_project.html", project=project)


@app.route("/update_task/<int:task_id>/<status>")
@login_required
def update_task_status(task_id, status):
    task = Task.query.get_or_404(task_id)
    project = Project.query.get_or_404(task.project_id)

    if project.owner_id != current_user.id:
        return redirect(url_for("dashboard"))

    old_status = task.status
    task.status = status
    db.session.commit()

    add_activity(project.id, f"Task status changed: {task.title} ({old_status} → {status})")

    return redirect(url_for("project_detail", project_id=project.id))


@app.route("/edit_task/<int:task_id>", methods=["GET", "POST"])
@login_required
def edit_task(task_id):
    task = Task.query.get_or_404(task_id)
    project = Project.query.get_or_404(task.project_id)

    if project.owner_id != current_user.id:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        task.title = request.form["title"].strip()
        task.description = request.form["description"].strip()
        task.assigned_to = request.form["assigned_to"].strip()
        task.due_date = request.form["due_date"]
        task.priority = request.form["priority"]
        task.comment = request.form["comment"].strip()

        db.session.commit()

        add_activity(project.id, f"Task edited: {task.title}")

        return redirect(url_for("project_detail", project_id=project.id))

    return render_template("edit_task.html", task=task)


@app.route("/delete_task/<int:task_id>")
@login_required
def delete_task(task_id):
    task = Task.query.get_or_404(task_id)
    project = Project.query.get_or_404(task.project_id)

    if project.owner_id != current_user.id:
        return redirect(url_for("dashboard"))

    project_id = task.project_id
    task_title = task.title

    TaskComment.query.filter_by(task_id=task.id).delete()
    db.session.delete(task)
    db.session.commit()

    add_activity(project_id, f"Task deleted: {task_title}")

    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/delete_project/<int:project_id>")
@login_required
def delete_project(project_id):
    project = Project.query.get_or_404(project_id)

    if project.owner_id != current_user.id:
        return redirect(url_for("dashboard"))

    tasks = Task.query.filter_by(project_id=project.id).all()
    for task in tasks:
        TaskComment.query.filter_by(task_id=task.id).delete()

    ActivityLog.query.filter_by(project_id=project.id).delete()
    Task.query.filter_by(project_id=project.id).delete()

    db.session.delete(project)
    db.session.commit()

    return redirect(url_for("dashboard"))


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    app.run(debug=False)