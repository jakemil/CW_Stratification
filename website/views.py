from flask import Blueprint, render_template, request, flash, jsonify, redirect, url_for
from flask_login import login_required, current_user
from .models import Note, Info, Stratification, User
from . import db
import json
import random

views = Blueprint('views', __name__)


@views.route('/', methods=['GET', 'POST'])
@login_required
def home():
    if request.method == 'POST': 
        note = request.form.get('note')  # Gets the note from the HTML 

        # Check if the user already has a note
        existing_note = Note.query.filter_by(user_id=current_user.id).first()
        if existing_note:
            flash('You already have a narrative! Please edit your existing narrative instead.', category='error')
        elif len(note) < 1:
            flash('Narrative is too short!', category='error') 
        elif len(note) > 1500:
            flash('Narrative is too long! (>=1500)', category='error')
        else:
            new_note = Note(data=note, user_id=current_user.id)  # Provide the schema for the note
            db.session.add(new_note)  # Add the note to the database
            db.session.commit()
            flash('Narrative submitted!', category='success')

    return render_template("home.html", user=current_user)

@views.route('/info', methods=['GET', 'POST'])
@login_required
def info():
    if request.method == 'POST': 
        group = request.form.get('group')  # Gets the cadet group (integer)
        squadron = request.form.get('squadron')  # Gets the cadet squadron (integer)
        flight = request.form.get('flight-staff')  # Gets the flight/staff
        class_year = request.form.get('class-year') # Gets the class year input
        admin_password = request.form.get('admin-password')  # Gets the admin password

        # Squadron-specific passwords
        squadron_passwords = {i: f"CS{i:02d}_password" for i in range(1, 41)}

        admin = None

        # Validation
        if not group or not squadron or not flight:
            flash('All fields except admin password are required!', category='error')
        elif admin_password:
            # Check admin password if provided
            correct_password = squadron_passwords.get(int(squadron))
            if correct_password and admin_password == correct_password:
                admin = squadron  # Grant admin rights
                flash(f'Admin rights granted for Cadet Squadron {squadron}!', category='success')
            else:
                flash('Invalid admin password!', category='error')
        else:
            admin = None  # No admin rights provided if no password entered

        if admin is not None or not admin_password:
            # Check if an entry already exists for the current user
            existing_info = Info.query.filter_by(user_id=current_user.id).first()
            
            if existing_info:
                # Update existing entry
                existing_info.group = group
                existing_info.squadron = squadron
                existing_info.flight = flight
                existing_info.admin = admin
                flash('Information updated successfully! Now Navigate to Narrative Page', category='success')
            else:
                # Create a new entry
                new_info = Info(
                    group=group,
                    squadron=squadron,
                    flight=flight,
                    admin=admin,
                    class_year = class_year,
                    user_id=current_user.id
                )
                new_strat = Stratification(
                user_id= current_user.id,
                overall_elo=1000,
                duty_perform_elo=1000,
                professionalism_elo=1000,
                leadership_elo=1000,
                character_elo=1000,
                )
                db.session.add(new_strat)
                db.session.add(new_info)
                flash('Information added successfully! Now Navigate to Narrative Page', category='success')
            
            db.session.commit()

    # Retrieve the existing info to display in the form
    user_info = Info.query.filter_by(user_id=current_user.id).first()

    return render_template(
        "info.html", 
        user=current_user, 
        info=user_info
    )

@views.route('/delete-note', methods=['POST'])
@login_required
def delete_note():  
    note = json.loads(request.data) # this function expects a JSON from the INDEX.js file 
    noteId = note['noteId']
    note = Note.query.get(noteId)
    if note:
        if note.user_id == current_user.id:
            db.session.delete(note)
            db.session.commit()

    return jsonify({})

@views.route('/admin-dashboard', methods=['GET'])
@login_required
def admin_dashboard():
    # Get the class year filter from query parameters
    class_year = request.args.get('class_year', type=int)
    
    # Query for users in the admin's squadron
    admin_info = Info.query.filter_by(user_id=current_user.id).first()
    if not admin_info:  # Ensure the current user is an admin
        return "Unauthorized Access", 403
    
    query = db.session.query(
        User.first_name, 
        User.last_name, 
        Stratification.overall_elo,
        Stratification.duty_perform_elo,
        Stratification.professionalism_elo,
        Stratification.leadership_elo, 
        Stratification.character_elo,
        Note.data.label("note_data")
    ).join(Info, User.id == Info.user_id)\
     .join(Stratification, User.id == Stratification.user_id, isouter=True)\
     .join(Note, User.id == Note.user_id, isouter=True)\
     .filter(Info.squadron == admin_info.squadron)
    
    print(class_year)
    if class_year:
        query = query.filter(Info.class_year == class_year)
    
    users = query.order_by(Stratification.overall_elo.desc().nullslast(), User.last_name, User.first_name).all()
    
    return render_template("admin_dashboard.html", users=users, squadron=admin_info.squadron, class_year=class_year)

@views.route('/strat-users', methods=['GET', 'POST'])
@login_required
def strat_users():
    # Get the current admin's squadron info
    admin_info = Info.query.filter_by(user_id=current_user.id).first()
    if not admin_info:
        return "Unauthorized Access", 403  # Ensure the current user is an admin

    # Get the class year from query parameters
    class_year = request.args.get('class_year', type=int)

    if not class_year:
        # If no class year is selected, provide a dropdown for selection
        class_years = db.session.query(Info.class_year).distinct().all()
        return render_template('strat_users.html', class_years=[cy[0] for cy in class_years], users=None)

    # Query for users in the same squadron and class year
    users = db.session.query(User, Note, Stratification).join(Info, Info.user_id == User.id) \
        .join(Note, Note.user_id == User.id) \
        .join(Stratification, Stratification.user_id == User.id, isouter=True) \
        .filter(Info.squadron == admin_info.squadron) \
        .filter(Info.class_year == class_year).all()

    if not users:
        flash(f"No users found for class year {class_year} in squadron {admin_info.squadron}.", category='error')
        return redirect(url_for('views.strat_users'))

    if request.method == 'POST':
        # Handle ranking update based on form submission
        winner_id = int(request.form['winner'])
        loser_id = int(request.form['loser'])

        # Update all ELO rankings
        winner = Stratification.query.filter_by(user_id=winner_id).first()
        loser = Stratification.query.filter_by(user_id=loser_id).first()

        criteria_list = ['overall', 'duty_performance', 'professionalism', 'leadership', 'character']

        # Ensure 'overall' is required
        overall_winner = request.form.get('overall_winner')
        if not overall_winner:
            flash('The "overall" criterion is required.', category='error')
            return redirect(request.url)  # Redirect back if overall is missing

        # Process the overall criterion
        if overall_winner == 'winner':
            update_elo(winner, loser, 'overall')
        elif overall_winner == 'loser':
            update_elo(loser, winner, 'overall')

        # Process optional criteria
        for criterion in criteria_list[1:]:  # Skip 'overall'
            criterion_winner = request.form.get(f'{criterion}_winner')
            if criterion_winner == 'winner':
                update_elo(winner, loser, criterion)
            elif criterion_winner == 'loser':
                update_elo(loser, winner, criterion)
            # If no input is provided for this criterion, skip it

        db.session.commit()

    # Select two random users for binary comparison
    user1, user2 = random.sample(users, 2)
    return render_template(
        'strat_users.html',
        class_year=class_year,
        user1=user1,
        user2=user2,
        users=users
    )



def update_elo(winner, loser, criterion, k=32):
    # Define the ELO fields for each criterion
    elo_fields = {
        'overall': 'overall_elo',
        'duty_performance': 'duty_perform_elo',
        'professionalism': 'professionalism_elo',
        'leadership': 'leadership_elo',
        'character': 'character_elo'
    }

    if criterion not in elo_fields:
        raise ValueError("Invalid criterion for ELO update.")

    # Get the ELO fields
    winner_field = getattr(winner, elo_fields[criterion])
    loser_field = getattr(loser, elo_fields[criterion])

    # Calculate expected scores
    expected_winner = 1 / (1 + 10 ** ((loser_field - winner_field) / 400))
    expected_loser = 1 - expected_winner

    # Update scores
    setattr(winner, elo_fields[criterion], int(winner_field + k * (1 - expected_winner)))
    setattr(loser, elo_fields[criterion], int(loser_field + k * (0 - expected_loser)))

@views.route('/metrics', methods=['GET'])
@login_required
def metrics():
    # Get the current user's Info entry (to determine squadron and class year)
    current_user_info = Info.query.filter_by(user_id=current_user.id).first()
    if not current_user_info:
        flash("User information not found.", category="error")
        return redirect(url_for('views.home'))

    # Get class year and squadron of current user
    class_year = current_user_info.class_year
    squadron = current_user_info.squadron

    # Query all users in the same squadron and class year
    users = db.session.query(User, Stratification).join(Info, User.id == Info.user_id) \
        .join(Stratification, User.id == Stratification.user_id) \
        .filter(Info.squadron == squadron, Info.class_year == class_year).all()

    # Calculate rankings for all categories
    categories = ['overall_elo', 'duty_perform_elo', 'professionalism_elo', 'leadership_elo', 'character_elo']
    rankings = {}

    for category in categories:
        # Sort users based on the current category in descending order
        sorted_users = sorted(users, key=lambda u: getattr(u[1], category), reverse=True)

        # Find the rank of the current user
        for rank, user in enumerate(sorted_users, start=1):
            if user[0].id == current_user.id:
                rankings[category] = f"{rank}/{len(sorted_users)}"
                break

    # Render the template with the rankings
    return render_template(
        "metrics.html",
        rankings=rankings,
        category_labels=['Overall', 'Duty Performance', 'Professionalism', 'Leadership', 'Character']
    )
