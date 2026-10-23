from contextlib import closing
import csv
from datetime import datetime
from html import unescape
import io
from pathlib import Path
import re
import sqlite3
import time
import unittest
from unittest.mock import patch

from flask import request
import test_app as existing
from test_app import database


def epoch(value):
    return int(datetime.fromisoformat(value).timestamp())


class Reports(unittest.TestCase):
    setUp = existing.AccountsAndLeads.setUp
    tearDown = existing.AccountsAndLeads.tearDown
    csrf = existing.AccountsAndLeads.csrf
    register = existing.AccountsAndLeads.register

    def fixture(self):
        self.workspace,self.public = self.register()
        self.assertEqual(self.client.get('/reports').status_code,200)
        with database(Path(self.temp.name)/'kjancy.sqlite3') as db:
            self.owner = db.execute('SELECT id FROM users').fetchone()[0]
            db.execute("INSERT INTO users(id,name,email,password_hash,created) VALUES('staff','Sam Chen','sam@example.test','unused',1)")
            db.execute("INSERT INTO memberships VALUES(?,'staff','dispatcher')",(self.workspace,))
            rows = [('new','Taylor New','New',self.owner,'HVAC'),('contacted','Casey Contacted','Contacted','staff','Drain cleaning'),
                    ('booked','Avery Booked','Appointment booked',None,'HVAC'),('closed','Morgan Closed','Closed',self.owner,'HVAC')]
            for uid,name,status,person,service in rows:
                self.add_lead(db,uid,name,status=status,assignee=person,service=service)
            self.add_lead(db,'old','Old Inquiry',status='Appointment booked',created='2026-01-01T00:00:00+00:00')
            for uid,lead,person,start,end,state in (
                ('scheduled','old',self.owner,'2026-10-23T12:00:00+00:00','2026-10-23T13:00:00+00:00','scheduled'),
                ('cancelled','new','staff','2026-10-22T23:30:00+00:00','2026-10-23T01:30:00+00:00','cancelled')):
                db.execute('INSERT INTO appointments(id,workspace_id,lead_id,assigned_user_id,start_at,end_at,state,cancellation_reason,created,updated) VALUES(?,?,?,?,?,?,?,?,1,1)',
                    (uid,self.workspace,lead,person,epoch(start),epoch(end),state,'Customer requested cancellation' if state=='cancelled' else ''))

    def add_lead(self,db,uid,name,*,status='New',assignee=None,service='HVAC',created='2026-10-23T10:00:00+00:00',email='customer@example.test',phone=''):
        db.execute("INSERT INTO leads(id,workspace_id,customer_name,email,phone,service,location,status,assigned_user_id,internal_notes,message,created,updated,source) VALUES(?,?,?,?,?,?,'Austin',?,?,'PRIVATE_INTERNAL_NOTE','PRIVATE_REQUEST_MESSAGE',?,?,'manual')",
            (uid,self.workspace,name,email,phone,service,status,assignee,epoch(created),epoch(created)))

    def report(self,**changes):
        values = {'kind':'leads','start':'2026-10-23','end':'2026-10-23','service':'','assignee':'all'}
        values.update(changes)
        return self.client.get('/reports',query_string=values)

    def export_url(self,response=None):
        response = response if response is not None else self.report()
        match = re.search(rb'href="([^\"]*reports/export\.csv[^\"]*)"',response.data)
        self.assertIsNotNone(match,'The report should offer its signed export link.')
        return unescape(match.group(1).decode())

    def export(self,response=None):
        return self.client.get(self.export_url(response))

    def csv_rows(self,response):
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.data.startswith(b'\xef\xbb\xbf'))
        return list(csv.DictReader(io.StringIO(response.data.decode('utf-8-sig'))))

    def test_lead_counts_are_current_statuses_for_received_dates(self):
        self.fixture()
        result = self.report()
        self.assertIn(b'4 leads received',result.data)
        self.assertNotIn(b'Old Inquiry',result.data)
        for status in ('New','Contacted','Appointment booked','Closed'):
            self.assertRegex(result.data.decode(),rf'<dt>{status}</dt>\s*<dd>1</dd>')
        self.assertIn(b'Closed does not mean a won sale',result.data)
        self.assertEqual({row['Current status'] for row in self.csv_rows(self.export(result))}, {'New','Contacted','Appointment booked','Closed'})

    def test_service_and_teammate_filters_match_page_and_csv_with_historical_services(self):
        self.fixture()
        with database(Path(self.temp.name)/'kjancy.sqlite3') as db:
            db.execute('UPDATE workspaces SET services_json=? WHERE id=?',('["Electrical"]',self.workspace))
        result = self.report(service='Drain cleaning',assignee='staff')
        self.assertIn(b'1 lead received',result.data)
        self.assertIn(b'Casey Contacted',result.data)
        rows = self.csv_rows(self.export(result))
        self.assertEqual([(row['Service'],row['Assigned teammate']) for row in rows],[('Drain cleaning','Sam Chen')])
        self.assertEqual(len(self.csv_rows(self.export(self.report(assignee='mine')))),2)
        self.assertEqual([row['Customer'] for row in self.csv_rows(self.export(self.report(assignee='unassigned')))],['Avery Booked'])

    def test_appointment_report_uses_overlapping_slots_not_lead_received_or_cancellation_event_date(self):
        self.fixture()
        result = self.report(kind='appointments')
        self.assertIn(b'2 appointments overlap',result.data)
        self.assertIn(b'Old Inquiry',result.data)
        self.assertRegex(result.data.decode(),r'<dt>Scheduled</dt>\s*<dd>1</dd>')
        self.assertRegex(result.data.decode(),r'<dt>Cancelled</dt>\s*<dd>1</dd>')
        rows = self.csv_rows(self.export(result))
        self.assertEqual({row['Appointment ID'] for row in rows},{'scheduled','cancelled'})
        self.assertEqual(next(row for row in rows if row['Appointment ID']=='cancelled')['Duration minutes'],'120')
        self.assertEqual(len(self.csv_rows(self.export(self.report(kind='appointments',assignee='mine')))),1)

    def test_pagination_does_not_limit_summary_or_export_to_visible_page(self):
        self.fixture()
        with database(Path(self.temp.name)/'kjancy.sqlite3') as db:
            for index in range(30): self.add_lead(db,f'bulk-{index:02}',f'Customer {index:02}')
        first,second = self.report(),self.report(page='2')
        for result in (first,second): self.assertIn(b'34 leads received',result.data)
        def visible_rows(result):
            body = re.search(rb'<tbody>(.*?)</tbody>',result.data,re.S).group(1)
            return len(re.findall(rb'<tr\b',body))
        self.assertEqual((visible_rows(first),visible_rows(second)),(25,9))
        self.assertEqual(len(self.csv_rows(self.export(second))),34)
        self.assertIn(b'Page 2 of 2',second.data)

    def test_csv_quotes_multiline_values_neutralizes_formulas_and_excludes_private_fields(self):
        self.fixture()
        dangerous = ['=2+2',' +SUM(1,1)','\t@SUM(1)','\n-2','＋1+1','－2','  =HYPERLINK("x")']
        normal = 'Normal, "quoted"\nSecond line'
        with database(Path(self.temp.name)/'kjancy.sqlite3') as db:
            for index,name in enumerate([*dangerous,normal]):
                self.add_lead(db,f'unsafe-{index}',name,phone='+1 555-010-2040')
        response = self.export()
        rows = self.csv_rows(response)
        names = {row['Customer'] for row in rows}
        self.assertTrue(all("'"+name in names for name in dangerous))
        self.assertIn(normal,names)
        self.assertTrue(all(row['Phone'].startswith("'") for row in rows if row['Phone']))
        self.assertNotIn(b'PRIVATE_INTERNAL_NOTE',response.data)
        self.assertNotIn(b'PRIVATE_REQUEST_MESSAGE',response.data)
        self.assertNotIn(b'owner@reed.test',response.data)
        self.assertNotIn(b'password_hash',response.data)
        self.assertIn('attachment;',response.headers['Content-Disposition'])
        self.assertIn('no-store',response.headers['Cache-Control'])

    def test_owner_permissions_and_company_scope_apply_to_reports_and_exports(self):
        self.fixture()
        url = self.export_url()
        public = self.app.test_client()
        self.assertEqual(public.get('/reports').status_code,303)
        self.assertEqual(public.get(url).status_code,303)
        staff = self.app.test_client()
        self.register(staff,'staff-owner@other.test','Separate Staff Business')
        with database(Path(self.temp.name)/'kjancy.sqlite3') as db:
            user = db.execute("SELECT id FROM users WHERE email='staff-owner@other.test'").fetchone()[0]
            db.execute("INSERT INTO memberships VALUES(?,?,'dispatcher')",(self.workspace,user))
        staff.post('/workspace/switch',data={'csrf_token':self.csrf(staff,'/inbox'),'workspace_id':self.workspace})
        self.assertEqual(staff.get('/reports').status_code,403)
        self.assertEqual(staff.get(url).status_code,403)
        self.assertNotIn(b'>Reports<',staff.get('/inbox').data)
        other = self.app.test_client()
        foreign,_ = self.register(other,'foreign@other.test','Foreign Company')
        self.assertNotIn(b'Taylor New',other.get('/reports').data)
        self.assertNotIn(b'Taylor New',other.get(url).data)
        self.assertEqual(len(self.csv_rows(self.export(self.report(workspace_id=foreign)))),4)

    def test_demoted_owner_is_rechecked_after_identity_loading(self):
        enabled = {'value':False}
        @self.app.before_request
        def demote():
            if enabled['value'] and request.path.startswith('/reports'):
                with database(Path(self.temp.name)/'kjancy.sqlite3') as db:
                    db.execute("UPDATE memberships SET role='dispatcher' WHERE workspace_id=? AND user_id=?",(self.workspace,self.owner))
        self.fixture()
        url = self.export_url()
        for path in ('/reports',url):
            with database(Path(self.temp.name)/'kjancy.sqlite3') as db:
                db.execute("UPDATE memberships SET role='owner' WHERE workspace_id=? AND user_id=?",(self.workspace,self.owner))
            enabled['value'] = True
            result = self.client.get(path)
            enabled['value'] = False
            self.assertEqual(result.status_code,403)
            self.assertNotIn(b'Taylor New',result.data)

    def test_export_link_binds_displayed_company_filters_and_ignores_unsigned_overrides(self):
        self.fixture()
        url = self.export_url(self.report(service='Drain cleaning'))
        self.assertEqual([row['Customer'] for row in self.csv_rows(self.client.get(url+'&kind=appointments&service=HVAC'))],['Casey Contacted'])
        other = self.app.test_client()
        foreign,_ = self.register(other,'foreign@other.test','Foreign Company')
        with database(Path(self.temp.name)/'kjancy.sqlite3') as db:
            db.execute("INSERT INTO memberships VALUES(?,?,'owner')",(foreign,self.owner))
        self.client.post('/workspace/switch',data={'csrf_token':self.csrf(self.client,'/inbox'),'workspace_id':foreign})
        response = self.client.get(url)
        self.assertEqual(response.status_code,400)
        self.assertNotIn('Content-Disposition',response.headers)

    def test_expired_tampered_or_old_timezone_download_link_is_rejected(self):
        self.fixture()
        url = self.export_url()
        self.assertEqual(self.client.get('/reports/export.csv?token=tampered').status_code,400)
        self.assertEqual(self.client.get('/reports/export.csv').status_code,400)
        expired = self.app.test_client()
        cookie_name = self.app.config['SESSION_COOKIE_NAME']
        expired.set_cookie(cookie_name,self.client.get_cookie(cookie_name).value)
        with patch('itsdangerous.timed.TimestampSigner.get_timestamp',return_value=int(time.time())+1801):
            self.assertEqual(expired.get(url).status_code,400)
        self.client.post('/workspace/timezone',data={'csrf_token':self.csrf(self.client,'/inbox'),'timezone':'Asia/Singapore'})
        self.assertEqual(self.client.get(url).status_code,400)
        rows = self.csv_rows(self.export())
        self.assertTrue(all(row['Workspace timezone']=='Asia/Singapore' for row in rows))
        self.assertTrue(all(row['Received at'].endswith('+08:00') for row in rows))

    def test_invalid_filters_show_errors_without_false_zero_metrics_or_csv(self):
        self.fixture()
        for changes in ({'kind':'forged'},{'start':'bad'},{'end':''},{'start':'1999-12-31'},
                        {'end':'2101-01-01'},{'start':'2026-10-24'},{'start':'2024-01-01','end':'2026-10-23'},
                        {'service':"x' OR 1=1 --"},{'assignee':'foreign'}):
            with self.subTest(changes=changes):
                result = self.report(**changes)
                self.assertEqual(result.status_code,422)
                self.assertIn(b'data-error-summary',result.data)
                self.assertNotIn(b'0 leads received',result.data)
                self.assertNotIn(b'href="/reports/export.csv',result.data)

    def test_empty_report_has_real_zero_states_and_headers_only_export(self):
        self.fixture()
        for kind in ('leads','appointments'):
            result = self.report(kind=kind,start='2026-10-25',end='2026-10-25')
            self.assertEqual(result.status_code,200)
            self.assertIn(b'No matching',result.data)
            self.assertEqual(self.csv_rows(self.export(result)),[])

    def test_unavailable_filters_remain_selected_and_escaped_on_error(self):
        self.fixture()
        result = self.report(service='<removed service>',assignee='<removed person>')
        self.assertEqual(result.status_code,422)
        self.assertIn(b'<option value="&lt;removed service&gt;" selected>Unavailable: &lt;removed service&gt;</option>',result.data)
        self.assertIn(b'<option value="&lt;removed person&gt;" selected>Unavailable teammate</option>',result.data)
        self.assertNotIn(b'<removed service>',result.data)
        self.assertNotIn(b'<removed person>',result.data)

    def test_export_refuses_more_than_ten_thousand_without_silent_truncation(self):
        self.fixture()
        url = self.export_url()
        with database(Path(self.temp.name)/'kjancy.sqlite3') as db:
            for index in range(10000): self.add_lead(db,f'bulk-{index:05}',f'Bulk customer {index}')
        result = self.client.get(url)
        self.assertEqual(result.status_code,422)
        self.assertIn(b'10,000',result.data)
        self.assertNotIn('Content-Disposition',result.headers)
        page = self.report()
        self.assertIn(b'aria-disabled="true"',page.data)
        self.assertNotIn(b'href="/reports/export.csv',page.data)

    def test_local_midnight_boundaries_include_whole_23_and_25_hour_dates(self):
        self.fixture()
        with database(Path(self.temp.name)/'kjancy.sqlite3') as db:
            db.execute("UPDATE workspaces SET timezone='America/New_York' WHERE id=?",(self.workspace,))
            for uid,created in (('fall-before','2026-11-01T03:59:59+00:00'),('fall-start','2026-11-01T04:00:00+00:00'),
                                ('fall-end','2026-11-02T04:59:59+00:00'),('fall-after','2026-11-02T05:00:00+00:00'),
                                ('spring-before','2026-03-08T04:59:59+00:00'),('spring-start','2026-03-08T05:00:00+00:00'),
                                ('spring-end','2026-03-09T03:59:59+00:00'),('spring-after','2026-03-09T04:00:00+00:00')):
                self.add_lead(db,uid,uid,created=created)
        for day,prefix in (('2026-11-01','fall'),('2026-03-08','spring')):
            rows = self.csv_rows(self.export(self.report(start=day,end=day)))
            self.assertEqual({row['Lead ID'] for row in rows},{prefix+'-start',prefix+'-end'})

    def test_former_teammate_filter_retains_cancelled_appointment_history(self):
        self.fixture()
        self.client.post('/team/members/staff/remove',data={'csrf_token':self.csrf(self.client,'/team')})
        result = self.report(kind='appointments',assignee='staff')
        self.assertIn(b'former teammate',result.data)
        rows = self.csv_rows(self.export(result))
        self.assertEqual([(row['Appointment ID'],row['Assigned teammate']) for row in rows],[('cancelled','Sam Chen')])

    def test_report_and_export_do_not_mutate_any_existing_table_values(self):
        self.fixture()
        def snapshot():
            with closing(sqlite3.connect(Path(self.temp.name)/'kjancy.sqlite3')) as db:
                tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
                return {table:sorted(db.execute(f'SELECT * FROM "{table}"').fetchall(),key=repr) for table in tables}
        before = snapshot()
        self.export()
        self.export(self.report(kind='appointments'))
        self.assertEqual(snapshot(),before)

    def test_report_customer_html_is_escaped(self):
        self.fixture()
        with database(Path(self.temp.name)/'kjancy.sqlite3') as db:
            self.add_lead(db,'html','<script>alert(1)</script>')
        result = self.report()
        self.assertIn(b'&lt;script&gt;alert(1)&lt;/script&gt;',result.data)
        self.assertNotIn(b'<script>alert(1)</script>',result.data)
