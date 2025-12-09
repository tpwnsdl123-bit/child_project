from flask import Blueprint, url_for, render_template
from werkzeug.utils import redirect

bp = Blueprint('main', __name__, url_prefix='/')

@bp.route('/')
def index():
    return render_template('main/home.html')


@bp.route('/introduce')
def introduce():
    return render_template('main/introduce.html')    

@bp.route('/dashboard')
def dashboard():
    return render_template('main/dashboard.html')


@bp.route('/predict')
def predict():
    return render_template('main/predict.html')


@bp.route('/qna')
def qna():
    # return render_template('question/qna.html')
     return redirect(url_for('question._list'))

@bp.route('/terms')
def terms():
    return render_template('policy/terms.html')

@bp.route('/privacy')
def privacy():
    return render_template('policy/privacy.html')


