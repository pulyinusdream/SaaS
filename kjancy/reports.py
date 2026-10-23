"""Owner-only current-state reports and bounded, scope-bound CSV downloads."""
import csv
from datetime import date, datetime, time, timedelta
import io
import re
import unicodedata
from zoneinfo import ZoneInfo

from flask import Blueprint, Response, abort, current_app, g, render_template, request, url_for
from itsdangerous import BadData, URLSafeTimedSerializer

from .business_settings import service_choices
from .db import get_db
from .followups import utc_now
from .security import require_workspace
from .validation import STATUSES

bp = Blueprint('reports',__name__)
PAGE_SIZE = 25
EXPORT_LIMIT = 10_000
FILTER_KEYS = ('kind','start','end','service','assignee')
CSV_HEADERS = {
    'leads': ('Lead ID','Customer','Email','Phone','Service','Location','Business','Source','Current status','Assigned teammate','Received at','Updated at','Workspace timezone'),
    'appointments': ('Appointment ID','Lead ID','Customer','Email','Phone','Service','Location','Assigned teammate','Current state','Start at','End at','Duration minutes','Cancellation reason','Workspace timezone'),
}


def signer():
    return URLSafeTimedSerializer(current_app.secret_key,salt='report-export-v1')


def refresh_owner(db):
    workspace = db.execute('SELECT w.*,m.role FROM workspaces w JOIN memberships m ON m.workspace_id=w.id WHERE w.id=? AND m.user_id=?',(g.workspace['id'],g.user['id'])).fetchone()
    if not workspace or workspace['role']!='owner':
        abort(403,description='Only workspace owners can view reports and download CSV files.')
    g.workspace = workspace


def choices(db):
    services = set(service_choices(g.workspace))
    services.update(row[0] for row in db.execute("SELECT DISTINCT service FROM leads WHERE workspace_id=? AND service!=''",(g.workspace['id'],)))
    team = db.execute('SELECT u.id,u.name,CASE WHEN m.user_id IS NULL THEN 0 ELSE 1 END AS current_member FROM users u LEFT JOIN memberships m ON m.user_id=u.id AND m.workspace_id=? WHERE m.user_id IS NOT NULL OR u.id IN (SELECT assigned_user_id FROM leads WHERE workspace_id=?) OR u.id IN (SELECT assigned_user_id FROM appointments WHERE workspace_id=?) ORDER BY u.name,u.id', (g.workspace['id'],g.workspace['id'],g.workspace['id'])).fetchall()
    return sorted(services,key=lambda value:(value.casefold(),value)),team


def parse_filters(raw,services,team):
    today = utc_now().astimezone(ZoneInfo(g.workspace['timezone'])).date()
    defaults = {'kind':'leads','start':(today-timedelta(days=29)).isoformat(),'end':today.isoformat(),'service':'','assignee':'all'}
    values = {key:raw.get(key,default).strip() for key,default in defaults.items()}
    errors,dates = {},{}
    if values['kind'] not in CSV_HEADERS:
        errors['form'] = 'Choose the Leads or Appointments report.'
    for key,label in (('start','start date'),('end','end date')):
        try:
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',values[key]): raise ValueError()
            dates[key] = date.fromisoformat(values[key])
            if not 2000<=dates[key].year<=2100: raise ValueError()
        except ValueError:
            errors[key] = f'Choose a valid {label} between 2000 and 2100.'
    if not {'start','end'} & errors.keys():
        length = (dates['end']-dates['start']).days+1
        if length<1: errors['end'] = 'The end date must be on or after the start date.'
        elif length>366: errors['end'] = 'Choose a range of at most 366 dates.'
    if values['service'] and values['service'] not in services:
        errors['service'] = 'Choose a service from this workspace.'
    if values['assignee'] not in {'all','mine','unassigned'} and values['assignee'] not in {person['id'] for person in team}:
        errors['assignee'] = 'Choose a teammate from this workspace.'
    bounds = None
    if not errors:
        zone = ZoneInfo(g.workspace['timezone'])
        bounds = tuple(int(datetime.combine(day,time.min,zone).timestamp()) for day in (dates['start'],dates['end']+timedelta(days=1)))
    return values,errors,bounds


def query_parts(values,bounds):
    kind = values['kind']
    start,end = bounds
    if kind=='leads':
        joined = 'leads l LEFT JOIN users u ON u.id=l.assigned_user_id'
        clauses,args = ['l.workspace_id=?','l.created>=?','l.created<?'],[g.workspace['id'],start,end]
        person,state,order = 'l.assigned_user_id','l.status','l.created DESC,l.id DESC'
        projection = 'l.id AS lead_id,l.customer_name,l.email,l.phone,l.service,l.location,l.business_name,l.source,l.status AS current_status,l.created,l.updated,u.name AS assignee_name'
    else:
        joined = 'appointments a JOIN leads l ON l.id=a.lead_id AND l.workspace_id=a.workspace_id LEFT JOIN users u ON u.id=a.assigned_user_id'
        clauses,args = ['a.workspace_id=?','a.start_at<?','a.end_at>?'],[g.workspace['id'],end,start]
        person,state,order = 'a.assigned_user_id','a.state','a.start_at,a.id'
        projection = 'a.id AS appointment_id,a.lead_id,a.start_at,a.end_at,a.state AS current_state,a.cancellation_reason,l.customer_name,l.email,l.phone,l.service,l.location,u.name AS assignee_name'
    if values['service']:
        clauses.append('l.service=?')
        args.append(values['service'])
    if values['assignee']=='unassigned': clauses.append(person+' IS NULL')
    elif values['assignee']!='all':
        clauses.append(person+'=?')
        args.append(g.user['id'] if values['assignee']=='mine' else values['assignee'])
    return joined,' AND '.join(clauses),args,state,order,projection


def report_data(db,values,bounds,*,export=False):
    joined,where,args,state,order,projection = query_parts(values,bounds)
    labels = STATUSES if values['kind']=='leads' else ('Scheduled','Cancelled')
    summary = {label:0 for label in labels}
    for row in db.execute(f'SELECT {state} AS state,count(*) AS total FROM {joined} WHERE {where} GROUP BY {state}',args):
        summary[row['state'] if values['kind']=='leads' else row['state'].capitalize()] = row['total']
    total = sum(summary.values())
    pages = max(1,(total+PAGE_SIZE-1)//PAGE_SIZE)
    try: page = max(1,min(int(request.args.get('page','1')),pages))
    except ValueError: page = 1
    items = []
    if not export or total<=EXPORT_LIMIT:
        limit,offset = (EXPORT_LIMIT,0) if export else (PAGE_SIZE,(page-1)*PAGE_SIZE)
        items = db.execute(f'SELECT {projection} FROM {joined} WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?',[*args,limit,offset]).fetchall()
    return {'total':total,'summary':summary,'items':items,'page':page,'pages':pages,
            'shown_start':(page-1)*PAGE_SIZE+1 if total else 0,'shown_end':min(page*PAGE_SIZE,total)}


def render_report(values,errors,services,team,data=None,code=200):
    kind = values['kind'] if values['kind'] in CSV_HEADERS else 'leads'
    parameters = {**values,'kind':kind}
    tabs = [{'label':label,'kind':mode,'url':url_for('reports.index',**{**parameters,'kind':mode}),'selected':kind==mode} for mode,label in (('leads','Leads'),('appointments','Appointments'))]
    export_url = None
    if not errors and data is not None and data['total']<=EXPORT_LIMIT:
        token = signer().dumps({'workspace':g.workspace['id'],'timezone':g.workspace['timezone'],'filters':values})
        export_url = url_for('reports.export_csv',token=token)
    previous_url = url_for('reports.index',**parameters,page=data['page']-1) if data and data['page']>1 else None
    next_url = url_for('reports.index',**parameters,page=data['page']+1) if data and data['page']<data['pages'] else None
    return render_template('reports.html',title='Reports',active='reports',kind=kind,values=values,errors=errors,
        report=data,services=services,team=team,tabs=tabs,export_url=export_url,export_limit=EXPORT_LIMIT,
        previous_url=previous_url,next_url=next_url,reset_url=url_for('reports.index',kind=kind)),code


@bp.get('/reports')
@require_workspace
def index():
    db = get_db()
    with db:
        db.execute('BEGIN')
        refresh_owner(db)
        services,team = choices(db)
        values,errors,bounds = parse_filters(request.args,services,team)
        data = report_data(db,values,bounds) if not errors else None
        return render_report(values,errors,services,team,data,422 if errors else 200)


def csv_cell(value):
    if value is None: return ''
    if not isinstance(value,str): return value
    probe = value
    while probe and (probe[0].isspace() or unicodedata.category(probe[0]) in {'Cc','Cf'}):
        probe = probe[1:]
    dangerous = unicodedata.normalize('NFKC',probe).startswith(('=','+','-','@'))
    leading_control = bool(value and unicodedata.category(value[0]) in {'Cc','Cf'})
    return "'"+value if dangerous or leading_control else value


def serialize_csv(values,items):
    zone_name = g.workspace['timezone']
    zone = ZoneInfo(zone_name)
    def local(epoch): return datetime.fromtimestamp(epoch,zone).isoformat(timespec='seconds')
    output = io.StringIO(newline='')
    writer = csv.writer(output,quoting=csv.QUOTE_ALL,lineterminator='\r\n')
    writer.writerow(CSV_HEADERS[values['kind']])
    for row in items:
        if values['kind']=='leads':
            cells = (row['lead_id'],row['customer_name'],row['email'],row['phone'],row['service'],row['location'],row['business_name'],row['source'],row['current_status'],row['assignee_name'] or 'Unassigned',local(row['created']),local(row['updated']),zone_name)
        else:
            cells = (row['appointment_id'],row['lead_id'],row['customer_name'],row['email'],row['phone'],row['service'],row['location'],row['assignee_name'] or 'Unassigned',row['current_state'].capitalize(),local(row['start_at']),local(row['end_at']),(row['end_at']-row['start_at'])//60,row['cancellation_reason'],zone_name)
        writer.writerow([csv_cell(value) for value in cells])
    return output.getvalue().encode('utf-8-sig')


@bp.get('/reports/export.csv')
@require_workspace
def export_csv():
    db = get_db()
    with db:
        db.execute('BEGIN')
        refresh_owner(db)
        try:
            signed = signer().loads(request.args.get('token',''),max_age=1800)
            if (not isinstance(signed,dict) or signed.get('workspace')!=g.workspace['id'] or signed.get('timezone')!=g.workspace['timezone']
                    or not isinstance(signed.get('filters'),dict) or set(signed['filters'])!=set(FILTER_KEYS)
                    or not all(isinstance(value,str) for value in signed['filters'].values())):
                raise BadData('Wrong export scope')
        except BadData:
            abort(400,description='This export link expired or changed. Reopen Reports and choose Export CSV again.')
        services,team = choices(db)
        values,errors,bounds = parse_filters(signed['filters'],services,team)
        if errors:
            return render_report(values,errors,services,team,code=422)
        data = report_data(db,values,bounds,export=True)
        if data['total']>EXPORT_LIMIT:
            return render_report(values,{'form':'CSV downloads are limited to 10,000 rows. Narrow the date, service or teammate filters and try again.'},services,team,code=422)
        content = serialize_csv(values,data['items'])
    filename = f"kjancy-{values['kind']}-{values['start']}-to-{values['end']}.csv"
    return Response(content,content_type='text/csv; charset=utf-8',headers={'Content-Disposition':f'attachment; filename="{filename}"'})
