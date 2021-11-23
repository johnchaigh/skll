from flask import Flask, render_template, request, redirect, session
from flask_session.__init__ import Session
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from cs50 import SQL
from functools import wraps
import spacy
import pandas as pd

app = Flask(__name__)

db = SQL("sqlite:///skll.db")

# Configure session to use filesystem (instead of signed cookies)
app.config['SESSION_PERMANENT'] = True
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_THRESHOLD'] = 100
app.config['SECRET_KEY'] = '22de23241b664fc2abc8867581a0642d'
sess = Session()
sess.init_app(app)

def login_required(f):
    """
    Decorate routes to require login.
    http://flask.pocoo.org/docs/1.0/patterns/viewdecorators/
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

def extract_skills(resume_text): 

    nlp = spacy.load('en_core_web_sm')
    doc = nlp(resume_text)

    # removing stop words and implementing word tokenization
    tokens = [token.text for token in doc if not token.is_stop]

    # reading the csv file
    data = pd.read_csv("skills.csv")

    # extract values
    skills = list(data.columns.values)

    skillset = []

    # check for one-grams (example: python)
    for token in tokens:
        if token.lower() in skills:
            skillset.append(token)

    # check for bi-grams and tri-grams (example: machine learning)
    for token in doc.noun_chunks:
        token = token.text.lower().strip()
        if token in skills:
            skillset.append(token)

    return [i.capitalize() for i in set([i.lower() for i in skillset])]

@app.route("/")
def index():

    if request.method == "GET":
        return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Query database for username
        username = request.form.get("username")
        print(username)
        rows = db.execute("SELECT * FROM users WHERE email = ?", username)

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["password"], request.form.get("password")):
            return render_template('apology.html', message="invalid username and/or password", bodymessage = "invalid username and/or password")

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/profile")

    # User reached route via GET (as by clicking a link or via redirect)
    if request.method == "GET":
        return render_template("login.html")
    
@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "GET":
        return render_template('register.html')
    else:
        email = request.form.get("username")
        password = request.form.get("password")
        city = request.form.get("city")
        hashpassword = generate_password_hash(password)

        # Add user to database
        row = db.execute("SELECT email FROM users WHERE email = ?", email)
        print(row)
        if row:
            return render_template('apology.html', message="User already registered", bodymessage = "User already registered")
        else:
            db.execute("INSERT INTO users (email, password, city) VALUES (?, ?, ?)", email, hashpassword, city)
            resume_text = request.form.get("CV")
            cvskills = extract_skills(resume_text)

            for i in range(len(cvskills)):
                db.execute("INSERT INTO skills (username, skill, jobskill) VALUES (?,?,'NO')", email, cvskills[i])

    return redirect("/login")

@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")    


@app.route("/compare", methods=["GET", "POST"])
@login_required
def compare():

    if request.method == "GET":
        return render_template("compare.html")

    if request.method == "POST":

        info = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])
        username = info[0]["email"]

        resume_text = request.form.get("job")
        jobskills = extract_skills(resume_text)

        print(jobskills)

        for i in range(len(jobskills)):
            db.execute("INSERT INTO skills (username, skill, jobskill) VALUES (?,?,'YES')", username, jobskills[i])

        return redirect("/results")

@app.route("/results", methods=["GET"])
@login_required
def results():

    if request.method == "GET":

        info = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])
        username = info[0]["email"]

        # Determine skills from job description and number
        job = db.execute("SELECT * FROM skills WHERE username = ? AND jobskill = 'YES'", username)

        print("Job Skills")
        print(job)

        skillnumber = len(job)

        # Determine skills from CV and number
        cv = db.execute("SELECT * FROM skills WHERE username = ? AND jobskill = 'NO'", username)

        cvnumber = len(cv)

        match = db.execute("SELECT skill FROM skills WHERE username = ? GROUP BY (skill) HAVING COUNT(skill) = 2", username)

        print("CV Match ")
        print(match)

        matchnumber = len(match)

        missing = db.execute("SELECT skill FROM skills WHERE username = ? AND jobskill = 'YES' AND skill NOT IN (SELECT skill FROM skills WHERE username = ? AND jobskill = 'NO')", username, username)
        
        print("Missing Skills")
        print(missing)

        missingnumber = int(skillnumber - matchnumber)

        if (matchnumber == 0):
            percentmatch = 0
        elif (skillnumber == 0):
            percentmatch = 0
        else:
            percentmatch = round(float((matchnumber/skillnumber)*100))

         #now results have been calculated update the database, removing all the job skills
        db.execute("DELETE FROM skills WHERE username = ? AND jobskill = 'YES'", username)
        return render_template("results.html", missing = missing, missingnumber = missingnumber, rows = match, skillnumber = skillnumber, matchnumber = matchnumber, percentmatch = percentmatch)

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():

    if request.method == "GET":

        info = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])
        username = info[0]['email']
        location = info[0]['city']

        rows = db.execute("SELECT DISTINCT skill FROM skills WHERE username = ? AND jobskill = 'NO'", username)
        if len(rows) == 0:
            title = "No skills added, click below to update your profile."
        else:
            title = "Your skills: "

        return render_template('profile.html', location = location, rows = rows, title = title)

    else:

        return render_template('update.html')

@app.route("/update", methods=["GET", "POST"])
@login_required
def update():
    if request.method == "POST":

        info = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])
        username = info[0]["email"]

        #Remove old CV information from the database
        db.execute("DELETE FROM skills WHERE username = ? AND jobskill = 'NO'", username)

        #Update CV information in database

        resume_text = request.form.get("CV")
        cvskills = extract_skills(resume_text)
        for i in range(len(cvskills)):
            db.execute("INSERT INTO skills (username, skill, jobskill) VALUES (?,?,'NO')", username, cvskills[i])

        rows = db.execute("SELECT skill FROM skills WHERE username = ? AND jobskill = 'NO'", username)

        return render_template('profile.html', rows = rows)

    else:

        return render_template('update.html')

if __name__ == '__main__':
    app.debug = True
    app.run()
