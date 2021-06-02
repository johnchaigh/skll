# @Author: johnhaigh
# @Date:   2020-06-24T19:35:47+01:00
# @Last modified by:   johnhaigh
# @Last modified time: 2021-03-18T16:40:19+00:00

#A web based application to help determine suitability of jobs to skills.

import os
import sqlite3
import re
import math
from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime
import numbers
import pandas as pd
import spacy
import csv
from functools import wraps

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

def extract_skills(resume_text): # Function copied in part from Omkar Pathak // https://github.com/OmkarPathak/ResumeParser

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

# Configure session to use filesystem (instead of signed cookies)
app.config['SESSION_PERMANENT'] = True
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_THRESHOLD'] = 100
app.config['SECRET_KEY'] = '22de23241b664fc2abc8867581a0642d'
sess = Session()
sess.init_app(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///skll.db")

@app.route("/")
def index():

    if request.method == "GET":
        return render_template("index.html")

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
        skillnumber = len(job)

        # Determine skills from CV and number
        cv = db.execute("SELECT * FROM skills WHERE username = ? AND jobskill = 'NO'", username)
        cvnumber = len(cv)

        match = db.execute("SELECT skill FROM skills WHERE username = ? GROUP BY (skill) HAVING COUNT(skill) = 2", username)
        matchnumber = len(match)

        missing = db.execute("SELECT skill FROM skills WHERE username = ? AND jobskill = 'YES' AND skill NOT IN (SELECT skill FROM skills WHERE username = ? AND jobskill = 'NO')", username, username)
        missingnumber = int(skillnumber - matchnumber)

        if (matchnumber == 0):
            percentmatch = 0
        elif (skillnumber == 0):
            percentmatch = 0
        else:
            percentmatch = round(float((matchnumber/skillnumber)*100))

        db.execute("DELETE FROM skills WHERE username = ? AND jobskill = 'YES'", username)
        return render_template("results.html", missing = missing, missingnumber = missingnumber, rows = match, skillnumber = skillnumber, matchnumber = matchnumber, percentmatch = percentmatch)

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "GET":
        return render_template('register.html')
    else:
        email = request.form.get("email")
        password = request.form.get("password")
        city = request.form.get("city")
        hashpassword = generate_password_hash(password)

        # Add user to database
        row = db.execute("SELECT * FROM users WHERE email = ?", email)
        if row:
            return render_template('apology.html', message="User already registered", bodymessage = "User already registered")
        else:
            db.execute("INSERT INTO users (email, password, city) VALUES (?, ?, ?)", email, hashpassword, city)
            resume_text = request.form.get("CV")
            cvskills = extract_skills(resume_text)

            for i in range(len(cvskills)):
                db.execute("INSERT INTO skills (username, skill, jobskill) VALUES (?,?,'NO')", email, cvskills[i])

    return redirect("/login")

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE email = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["password"], request.form.get("password")):
            return render_template('apology.html', message="invalid username and/or password", bodymessage = "invalid username and/or password")

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/profile")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")

@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():

    if request.method == "GET":

        info = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])
        username = info[0]['email']
        location = info[0]['city']

        rows = db.execute("SELECT skill FROM skills WHERE username = ? AND jobskill = 'NO'", username)
        if len(rows) == 0:
            skills = "No skills added, click below to update your profile."
        else:
            skills = "Your skills: "

        return render_template('profile.html', location = location, rows = rows, skills = skills)

    else:

        return render_template('update.html')

@app.route("/update", methods=["GET", "POST"])
@login_required
def update():
    if request.method == "POST":

        info = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])
        username = info[0]["email"]

        #Update CV information in database

        resume_text = request.form.get("CV")
        cvskills = extract_skills(resume_text)
        for i in range(len(cvskills)):
            db.execute("INSERT INTO skills (username, skill, jobskill) VALUES (?,?,'NO')", username, cvskills[i])

        rows = db.execute("SELECT skill FROM skills WHERE username = ? AND jobskill = 'NO'", username)

        return render_template('profile.html', rows = rows)

    else:

        return render_template('update.html')


app.run()
# TODO: Centre 'goback' button on apology page
