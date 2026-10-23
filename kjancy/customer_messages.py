"""Customer-visible follow-ups, separate from private staff notes and reminders."""
import re
import uuid

from flask import abort, current_app, g, request, url_for
from itsdangerous import BadData, URLSafeTimedSerializer

from .db import get_db

PAGE_SIZE = 25


def signer(kind='customer'):
    return URLSafeTimedSerializer(current_app.secret_key, salt='customer-followup-v1' if kind=='customer' else 'staff-reply-v1')


def new_token(user_id, business_id, lead_id, kind='customer'):
    return signer(kind).dumps({'user':user_id,'business':business_id,'lead':lead_id,'nonce':uuid.uuid4().hex})


def reply_key(token, lead):
    try:
        signed = signer('staff').loads(token,max_age=3600)
        if (not isinstance(signed,dict) or signed.get('user')!=g.user['id'] or signed.get('business')!=lead['workspace_id']
                or signed.get('lead')!=lead['id'] or not isinstance(signed.get('nonce'),str)
                or not re.fullmatch(r'[a-f0-9]{32}',signed['nonce'])): raise BadData('Wrong reply scope')
    except BadData:
        abort(400,description='This reply form expired or changed. Reopen the request and try again.')
    return 'staff-reply:'+signed['nonce']


def unread_sql(alias, viewer_kind):
    """A correlated unread count; the caller binds the viewer ID before its WHERE args."""
    other = 'staff' if viewer_kind=='customer' else 'customer'
    return f"""(SELECT count(*) FROM customer_request_messages cm
        WHERE cm.lead_id={alias}.id AND cm.workspace_id={alias}.workspace_id
        AND cm.customer_user_id={alias}.customer_user_id AND cm.sender_kind='{other}'
        AND NOT EXISTS(SELECT 1 FROM request_message_reads mr WHERE mr.message_id=cm.id AND mr.user_id=?))"""


def unread_total():
    if not g.user: return 0
    if g.user['account_kind']=='customer':
        if not g.customer: return 0
        where,args = 'l.workspace_id=? AND l.customer_user_id=?',[g.customer['workspace_id'],g.user['id']]
    else:
        if not g.workspace: return 0
        where,args = 'l.workspace_id=?',[g.workspace['id']]
    return get_db().execute(f'SELECT coalesce(sum({unread_sql("l",g.user["account_kind"])}),0) FROM leads l WHERE {where}',
                            [g.user['id'],*args]).fetchone()[0]


def read_signer():
    return URLSafeTimedSerializer(current_app.secret_key,salt='request-read-snapshot-v1')


def mark_displayed_read(db,lead):
    """Caller has already rechecked current account and request access in its write transaction."""
    try:
        signed = read_signer().loads(request.form.get('read_token',''),max_age=3600)
        if (not isinstance(signed,dict) or signed.get('user')!=g.user['id'] or signed.get('kind')!=g.user['account_kind']
                or signed.get('business')!=lead['workspace_id'] or signed.get('lead')!=lead['id']): raise BadData('Wrong read scope')
        ids,page = signed.get('ids'),signed.get('page')
        if (not isinstance(ids,list) or not 1<=len(ids)<=PAGE_SIZE or any(type(i) is not int or i<1 for i in ids)
                or len(set(ids))!=len(ids) or type(page) is not int or page<1): raise BadData('Invalid snapshot')
    except BadData:
        abort(400,description='This message view expired or changed. Reopen the request before marking messages as read.')
    other = 'staff' if g.user['account_kind']=='customer' else 'customer'
    placeholders = ','.join('?' for _ in ids)
    found = db.execute(f'SELECT id FROM customer_request_messages WHERE id IN ({placeholders}) AND lead_id=? AND workspace_id=? AND customer_user_id=? AND sender_kind=?',
        [*ids,lead['id'],lead['workspace_id'],lead['customer_user_id'],other]).fetchall()
    if len(found)!=len(ids): abort(400,description='These messages no longer match this request. Reopen it before trying again.')
    db.executemany('INSERT OR IGNORE INTO request_message_reads(user_id,message_id) VALUES(?,?)',[(g.user['id'],i) for i in ids])
    return page


def history_context(lead, endpoint, customer_id=None):
    db = get_db()
    clause, args = 'lead_id=? AND workspace_id=?', [lead['id'],lead['workspace_id']]
    if customer_id:
        clause += ' AND customer_user_id=?'
        args.append(customer_id)
    total = db.execute(f'SELECT count(*) FROM customer_request_messages WHERE {clause}',args).fetchone()[0]
    pages = max(1,(total+PAGE_SIZE-1)//PAGE_SIZE)
    try: page = max(1,min(int(request.args.get('messages_page','1')),pages))
    except ValueError: page = 1
    other = 'staff' if g.user['account_kind']=='customer' else 'customer'
    rows = db.execute(f"SELECT id,sender_name,sender_kind,body,created,(sender_kind=? AND NOT EXISTS(SELECT 1 FROM request_message_reads mr WHERE mr.message_id=customer_request_messages.id AND mr.user_id=?)) AS is_unread FROM customer_request_messages WHERE {clause} ORDER BY created DESC,id DESC LIMIT ? OFFSET ?",
                      [other,g.user['id'],*args,PAGE_SIZE,(page-1)*PAGE_SIZE]).fetchall()
    visible_unread = [row['id'] for row in rows if row['is_unread']]
    read_token = read_signer().dumps({'user':g.user['id'],'kind':g.user['account_kind'],'business':lead['workspace_id'],
        'lead':lead['id'],'ids':visible_unread,'page':page}) if visible_unread else None
    def page_url(number):
        return url_for(endpoint,lead_id=lead['id'],messages_page=number,_anchor='follow-up-messages')
    read_endpoint = 'customers.read_messages' if customer_id else 'leads.read_messages'
    return {'customer_messages':rows,'message_total':total,'message_page':page,'message_pages':pages,
            'read_token':read_token,'read_action':url_for(read_endpoint,lead_id=lead['id']),
            'older_messages_url':page_url(page+1) if page<pages else None,
            'newer_messages_url':page_url(page-1) if page>1 else None}
