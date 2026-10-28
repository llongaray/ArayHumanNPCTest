"""Loopback-only Flask dashboard. No start/stop/shell/game endpoints."""
import hmac
import secrets
from pathlib import Path
from urllib.parse import urlsplit
from flask import Flask,abort,jsonify,render_template,request
from .store import runs,run_by_id,history
from .lab import Laboratory,catalog,SCENARIOS

def create_app():
    app=Flask(__name__);app.config.update(MAX_CONTENT_LENGTH=16384,TRUSTED_HOSTS=['127.0.0.1','localhost'])
    token=secrets.token_urlsafe(32);lab=Laboratory();app.config['LAB_TOKEN']=token
    @app.before_request
    def local_only():
        if request.remote_addr not in ('127.0.0.1','::1'):abort(403)
        if request.method=='POST':
            origin=request.headers.get('Origin')
            if origin and urlsplit(origin).netloc!=request.host:abort(403)
            if not hmac.compare_digest(request.headers.get('X-Neural-Token',''),token):abort(403)
    @app.after_request
    def headers(response):
        response.headers['Cache-Control']='no-store';response.headers['X-Content-Type-Options']='nosniff'
        response.headers['X-Frame-Options']='DENY';response.headers['Referrer-Policy']='no-referrer'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'"
        return response
    @app.get('/')
    def index():return render_template('dashboard.html',token=token)
    @app.get('/api/runs')
    def get_runs():return jsonify(runs())
    @app.get('/api/checkpoints')
    def get_checkpoints():return jsonify(catalog())
    @app.get('/api/scenarios')
    def get_scenarios():return jsonify(SCENARIOS)
    @app.get('/api/runs/<run_id>')
    def get_run(run_id):
        try:run=run_by_id(run_id)
        except ValueError:abort(404)
        if run is None:abort(404)
        error=''
        try:
            with (Path(run['path'])/'error.log').open('rb') as stream:
                stream.seek(0,2);size=stream.tell();stream.seek(max(0,size-16384));error=stream.read().decode('utf-8',errors='replace')
        except OSError:pass
        return jsonify(state=run,history=history(run['path']),error=error)
    @app.post('/api/laboratory')
    def laboratory():
        body=request.get_json(silent=True)
        if not isinstance(body,dict) or set(body)-{'message','checkpoint_id','scenario'}:abort(400)
        try:return jsonify(lab.predict(body.get('message'),body.get('checkpoint_id'),body.get('scenario','calm')))
        except ValueError as exc:return jsonify(error=str(exc)),400
        except RuntimeError as exc:return jsonify(error=str(exc)),409
        except Exception:
            app.logger.exception('Laboratory inference failed')
            return jsonify(error='inference_failed_see_dashboard_terminal'),500
    return app
