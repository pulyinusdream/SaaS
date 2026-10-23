"""Read-only day/week calendar projections in the workspace timezone."""
from datetime import date, datetime, time, timedelta
import re
from zoneinfo import ZoneInfo

from flask import Blueprint, abort, g, render_template, request

from .db import get_db
from .followups import utc_now
from .security import require_workspace

bp = Blueprint('calendar',__name__)


@bp.get('/calendar')
@require_workspace
def calendar():
    zone = ZoneInfo(g.workspace['timezone'])
    today = utc_now().astimezone(zone).date()
    raw = request.args.get('date',today.isoformat())
    try:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',raw): raise ValueError()
        anchor = date.fromisoformat(raw)
        if not 2000<=anchor.year<=2100: raise ValueError()
    except ValueError:
        abort(400,description='Choose a calendar date between 2000 and 2100.')
    view = request.args.get('view','week')
    if view not in {'day','week'}: abort(400,description='Choose day or week view.')
    include_cancelled = request.args.get('include_cancelled','')
    if include_cancelled not in {'','1'}: abort(400,description='Choose a valid cancelled-appointment filter.')
    first = anchor-timedelta(days=anchor.weekday()) if view=='week' else anchor
    length = 7 if view=='week' else 1
    last = first+timedelta(days=length)
    def midnight(day): return int(datetime.combine(day,time.min,zone).timestamp())
    db = get_db()
    members = db.execute('SELECT u.id,u.name FROM users u JOIN memberships m ON m.user_id=u.id WHERE m.workspace_id=? ORDER BY u.name,u.id',(g.workspace['id'],)).fetchall()
    assignee = request.args.get('assignee','all')
    if assignee not in {'all','mine','unassigned'} and assignee not in {row['id'] for row in members}:
        abort(400,description='Choose a teammate from this workspace.')
    clauses, args = ['a.workspace_id=?','a.start_at<?','a.end_at>?'],[g.workspace['id'],midnight(last),midnight(first)]
    if not include_cancelled: clauses.append("a.state='scheduled'")
    if assignee=='unassigned': clauses.append('a.assigned_user_id IS NULL')
    elif assignee!='all':
        clauses.append('a.assigned_user_id=?')
        args.append(g.user['id'] if assignee=='mine' else assignee)
    where = ' AND '.join(clauses)
    total = db.execute(f'SELECT count(*) FROM appointments a WHERE {where}',args).fetchone()[0]
    try: page = max(1,min(int(request.args.get('page','1')),100000))
    except ValueError: page = 1
    pages = max(1,(total+49)//50)
    page = min(page,pages)
    items = db.execute(f'SELECT a.*,l.customer_name,l.service,l.location,u.name AS assignee_name FROM appointments a JOIN leads l ON l.id=a.lead_id AND l.workspace_id=a.workspace_id LEFT JOIN users u ON u.id=a.assigned_user_id WHERE {where} ORDER BY a.start_at,a.id LIMIT 50 OFFSET ?',[*args,(page-1)*50]).fetchall()
    days = []
    for offset in range(length):
        day = first+timedelta(days=offset)
        start,end = midnight(day),midnight(day+timedelta(days=1))
        def clock(epoch):
            local = datetime.fromtimestamp(epoch,zone)
            return local.strftime('%H:%M %Z' if local.date()==day else '%b %d, %H:%M %Z')
        entries = [{'item':item,'start_label':clock(item['start_at']),'end_label':clock(item['end_at']),
                    'continues_before':item['start_at']<start,'continues_after':item['end_at']>end}
                   for item in items if item['start_at']<end and item['end_at']>start]
        days.append({'date':day,'entries':entries,'today':day==today})
    previous,next_date = first-timedelta(days=length),first+timedelta(days=length)
    return render_template('calendar.html',title='Calendar',active='calendar',view=view,anchor=anchor,first=first,
        last=last-timedelta(days=1),days=days,team=members,selected_assignee=assignee,include_cancelled=include_cancelled,
        previous=previous if 2000<=previous.year<=2100 else None,next_date=next_date if 2000<=next_date.year<=2100 else None,
        today=today,total=total,page=page,pages=pages,shown_start=(page-1)*50+1 if total else 0,shown_end=min(page*50,total))
