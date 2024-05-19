from flask import Flask, render_template, request, session, redirect
from flask_pymongo import PyMongo
from flask_mail import Mail, Message
from werkzeug.utils import secure_filename
import json
import time
import os
import math

with open('config.json', 'r') as c:
    params = json.load(c)["params"]

app = Flask(__name__)
app.secret_key = 'super-secret-key'
app.config['UPLOAD_FOLDER'] = params['upload_location']

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USE_SSL'] = True
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USERNAME'] = params['gmail_user']
app.config['MAIL_PASSWORD'] = params['gmail_password']

mail = Mail(app)

if params['local_server']:
    app.config["MONGO_URI"] = params['local_uri']
else:
    app.config["MONGO_URI"] = params['prod_uri']

mongo = PyMongo(app)

def get_next_sequence_value():
    last_post = mongo.db.blog_post.find_one(sort=[("_id", -1)])
    if last_post:
        return last_post['_id'] + 1
    return 1  # Start from 1 if no posts exist

def reassign_ids():
    # Temporary collection to hold reassigned posts
    temp_collection_name = 'temp_blog_post'
    
    # Drop the temporary collection if it exists
    mongo.db[temp_collection_name].drop()
    
    # Fetch all posts sorted by original _id
    posts = list(mongo.db.blog_post.find().sort('_id', 1))
    
    # Insert posts into the temporary collection with new _ids
    for index, post in enumerate(posts):
        post['_id'] = index + 1  # Start IDs from 1
        mongo.db[temp_collection_name].insert_one(post)
    
    # Drop the original collection and rename the temporary collection
    mongo.db.blog_post.drop()
    mongo.db[temp_collection_name].rename('blog_post')

@app.route('/')
def home():
    posts = list(mongo.db.blog_post.find().sort([('timestamp', -1), ('_id', -1)]))  # Sort posts by timestamp and ID
    no_of_posts = int(params['no_of_posts'])
    total_posts = len(posts)
    last = math.ceil(total_posts / no_of_posts)
    
    page = request.args.get('page', default=1, type=int)
    if page < 1:
        page = 1
    elif page > last:
        page = last

    start = (page - 1) * no_of_posts
    end = start + no_of_posts
    posts_to_display = posts[start:end]

    prev = f"/?page={page - 1}" if page > 1 else "#"
    next = f"/?page={page + 1}" if page < last else "#"

    return render_template('index.html', params=params, posts=posts_to_display, prev=prev, next=next)


@app.route('/about')
def about():
    return render_template('about.html', params=params)

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'user' in session and session['user'] == params['admin_user']:
        posts = list(mongo.db.blog_post.find().sort('timestamp', -1))
        print("Fetched posts:", posts)  # Debugging statement
        return render_template('dashboard.html', params=params, posts=posts)

    if request.method == 'POST':
        username = request.form.get('uname')
        password = request.form.get('password')
        if username == params['admin_user'] and password == params['admin_password']:
            session['user'] = username
            posts = list(mongo.db.blog_post.find().sort('timestamp', -1))
            print("Fetched posts after login:", posts)  # Debugging statement
            return render_template('dashboard.html', params=params, posts=posts)

    return render_template('login.html', params=params)



@app.route('/edit/<string:_id>', methods=['GET', 'POST'])
def edit(_id):
    if 'user' in session and session['user'] == params['admin_user']:
        if request.method == 'POST':
            slug = request.form['slug']
            title = request.form['title']
            sub_title = request.form['sub_title']
            content = request.form['content']
            img_file = request.form['img_file']

            if _id == '0':
                # Generate a new custom ID using the counter
                new_id = get_next_sequence_value()
                post = {
                    '_id': new_id,
                    'slug': slug,
                    'title': title,
                    'sub_title': sub_title,
                    'content': content,
                    'img_file': img_file,
                    'timestamp': int(time.time())
                }
                mongo.db.blog_post.insert_one(post)
            else:
                mongo.db.blog_post.update_one(
                    {'_id': int(_id)},
                    {'$set': {
                        'slug': slug,
                        'title': title,
                        'sub_title': sub_title,
                        'content': content,
                        'img_file': img_file
                    }}
                )

            return redirect('/dashboard')  # Redirect to dashboard after updating or adding a post

        post = mongo.db.blog_post.find_one({'_id': int(_id)}) if _id != '0' else None
        return render_template('edit.html', params=params, post=post, _id=_id)
    
    return redirect('/login')

@app.route('/post/<string:post_slug>', methods=['GET', 'POST'])
def post_route(post_slug):
    post = mongo.db.blog_post.find_one({'slug': post_slug})
    if post:
        return render_template('post.html', params=params, post=post)
    else:
        return "Post not found", 404

@app.route('/uploader', methods=['GET', 'POST'])
def uploader():
    if 'user' in session and session['user'] == params['admin_user']:
        if request.method == 'POST':
            f = request.files['file1']
            f.save(os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(f.filename)))
            return "uploaded successfully"
        return render_template('dashboard.html', params=params)

@app.route('/logout')
def logout():
    session.pop('user')
    return redirect('/dashboard')

@app.route('/delete/<string:_id>', methods=['GET', 'POST'])
def delete(_id):
    if 'user' in session and session['user'] == params['admin_user']:
        mongo.db.blog_post.delete_one({'_id': int(_id)})  # Delete the post by ID
        reassign_ids()  # Reassign IDs to maintain sequence
        return redirect('/dashboard')
    return redirect('/login')

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        message = request.form['message']

        new_entry = {
            'name': name,
            'email': email,
            'phone': phone,
            'message': message
        }

        mongo.db.details.insert_one(new_entry)

        email_message = Message('New message from ' + name,
                                sender=email,
                                recipients=[params['gmail_user']])
        email_message.body = f"Name: {name}\nEmail: {email}\nPhone: {phone}\nMessage: {message}"
        mail.send(email_message)

    return render_template('contact.html', params=params)

if __name__ == "__main__":
    app.run(debug=True)





