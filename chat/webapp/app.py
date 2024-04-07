# -*- coding: utf-8 -*-
# ==============================================================================
# Copyright (c) 2024 Xavier de Carné de Carnavalet
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
# 
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
# 
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
# 
# 3. The name of the author may not be used to endorse or promote products
#    derived from this software without specific prior written permission.
# 
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
# ==============================================================================

# session id protection

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, abort, flash
from flask_mysqldb import MySQL
from flask_session import Session
import yaml

app = Flask(__name__)

# Configure secret key and Flask-Session
app.config['SECRET_KEY'] = 'your_secret_key_here'
app.config['SESSION_TYPE'] = 'filesystem'  # Options: 'filesystem', 'redis', 'memcached', etc.
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True  # To sign session cookies for extra security
app.config['SESSION_FILE_DIR'] = './sessions'  # Needed if using filesystem type

# Load database configuration from db.yaml or configure directly here
db_config = yaml.load(open('db.yaml'), Loader=yaml.FullLoader)
app.config['MYSQL_HOST'] = db_config['mysql_host']
app.config['MYSQL_USER'] = db_config['mysql_user']
app.config['MYSQL_PASSWORD'] = db_config['mysql_password']
app.config['MYSQL_DB'] = db_config['mysql_db']

mysql = MySQL(app)

# Initialize the Flask-Session
Session(app)

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    sender_id = session['user_id']
    return render_template('chat.html', sender_id=sender_id)

@app.route('/users')
def users():
    if 'user_id' not in session:
        abort(403)

    cur = mysql.connection.cursor()
    cur.execute("SELECT user_id, username FROM users")
    user_data = cur.fetchall()
    cur.close()

    filtered_users = [[user[0], user[1]] for user in user_data if user[0] != session['user_id']]
    return {'users': filtered_users}

@app.route('/fetch_messages')
def fetch_messages():
    if 'user_id' not in session:
        abort(403)

    last_message_id = request.args.get('last_message_id', 0, type=int)
    peer_id = request.args.get('peer_id', type=int)
    
    cur = mysql.connection.cursor()
    query = """SELECT message_id,sender_id,receiver_id,message_text,message_type, message_value, message_iv, message_tag, message_secret_counter
     FROM messages 
                   WHERE message_id > %s AND 
               ((sender_id = %s AND receiver_id = %s) OR (sender_id = %s AND receiver_id = %s))
               ORDER BY message_id ASC"""
    cur.execute(query, (last_message_id, peer_id, session['user_id'], session['user_id'], peer_id))

    # Fetch the column names
    column_names = [desc[0] for desc in cur.description]
    # Fetch all rows, and create a list of dictionaries, each representing a message
    messages = [dict(zip(column_names, row)) for row in cur.fetchall()]

    cur.close()
    return jsonify({'messages': messages})

@app.route('/goToRegister')
def goToRegister():
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        userDetails = request.form
        username = userDetails['username']
        password = userDetails['password']
        valid = userDetails['valid']
        input_str = userDetails['cpatchaTextBox']
        if (valid!=input_str):
            error = 'Invalid captcha'
            return render_template('login.html', error=error)
        
        cur = mysql.connection.cursor()
        cur.execute("SELECT user_id FROM users WHERE username=%s AND password=%s", (username, password,))
        account = cur.fetchone()
        if account:
            session['username'] = username
            session['user_id'] = account[0]
            return redirect(url_for('index'))
        else:
            error = 'Invalid credentials'
    return render_template('login.html', error=error)

@app.route('/send_message', methods=['POST'])
def send_message():
    if not request.json or not 'message_text' in request.json:
        abort(400)  # Bad request if the request doesn't contain JSON or lacks 'message_text'
    if 'user_id' not in session:
        abort(403)

    # Extract data from the request
    sender_id = session['user_id']
    receiver_id = request.json['receiver_id']
    message_text = request.json['message_text']
    message_type = request.json['message_type']
    message_iv = request.json['message_iv']
    message_value = request.json['message_value']
    message_tag = request.json['message_tag']
    message_secret_counter = request.json['message_secret_counter']

    # Assuming you have a function to save messages
    save_message(sender_id, receiver_id, message_text, message_type, message_iv, message_value, message_tag, message_secret_counter)
    # save_message(sender_id, receiver_id, message_text)
    
    return jsonify({'status': 'success', 'message': 'Message sent'}), 200

def save_message(sender, receiver, message, msg_type, msg_iv, msg_value, msg_tag, msg_secret_counter):
    cur = mysql.connection.cursor()
    cur.execute("INSERT INTO messages (sender_id, receiver_id, message_text, message_type, message_iv, message_value, message_tag, message_secret_counter) VALUES (%s, %s, %s, %s,%s,%s, %s, %s)", (sender, receiver, message, msg_type,msg_iv, msg_value, msg_tag, msg_secret_counter))
    # cur.execute("INSERT INTO messages (sender_id, receiver_id, message_text) VALUES (%s, %s, %s)", (sender, receiver, message))

    mysql.connection.commit()
    cur.close()

@app.route('/erase_chat', methods=['POST'])
def erase_chat():
    if 'user_id' not in session:
        abort(403)

    peer_id = request.json['peer_id']
    cur = mysql.connection.cursor()
    query = "DELETE FROM messages WHERE ((sender_id = %s AND receiver_id = %s) OR (sender_id = %s AND receiver_id = %s))"
    cur.execute(query, (peer_id, session['user_id'], session['user_id'], peer_id))
    mysql.connection.commit()

    # Check if the operation was successful by evaluating affected rows
    if cur.rowcount > 0:
        return jsonify({'status': 'success'}), 200
    else:
        return jsonify({'status': 'failure'}), 200

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been successfully logged out.', 'info')  # Flash a logout success message
    return redirect(url_for('index'))

# Registration for the new account
@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        userDetails = request.form
        # Get the username and password
        username = userDetails['username']
        password = userDetails['password']

        # Check whether the username is existed
        if check_name_existed(username):
            error = "Username is existed"
        else:
            register_new(username,password)

    return render_template('login.html', error=error)

def check_name_existed(username):
    # Connect to the databse
    cur = mysql.connection.cursor()

    # Use sql to check whether there is same username in the database
    cur.execute("SELECT COUNT(*) FROM users WHERE username = %s", (username,))
    search_result = cur.fetchone()[0]
    number_of_existing = int(search_result)

    # Check whether the number of username is more than 0
    if number_of_existing > 0:
        # Already existing
        return True
    else:
        # Not existing
        return False

def register_new(username,password):
    # Connect to the databse
    cur = mysql.connection.cursor()

    # Use sql to input the new username and the password
    cur.execute("INSERT INTO users (username, password) VALUES (%s, %s)", (username, password))

    # Commit the operation to save the change
    mysql.connection.commit()
    
    return 

if __name__ == '__main__':
    app.run(debug=True)

