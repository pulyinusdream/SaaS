"""Visibility regressions for simplified native disclosure forms."""
import re
import unittest
from html.parser import HTMLParser
import test_customers as customer_cases


class MainTools(HTMLParser):
    def __init__(self,html):
        super().__init__()
        self.stack=[]
        self.tools_in_main=None
        self.feed(html)

    def handle_starttag(self,tag,attrs):
        if tag=='details' and 'inbox-tools' in dict(attrs).get('class','').split():
            self.tools_in_main='main' in self.stack
        if tag not in {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}:
            self.stack.append(tag)

    def handle_endtag(self,tag):
        if tag in self.stack:
            del self.stack[len(self.stack)-1-self.stack[::-1].index(tag):]


class SimpleUI(unittest.TestCase):
    setUp = customer_cases.Customers.setUp
    tearDown = customer_cases.Customers.tearDown
    csrf = customer_cases.Customers.csrf
    register = customer_cases.Customers.register
    inquiry = customer_cases.Customers.inquiry
    signup_customer = customer_cases.Customers.signup_customer
    fixture = customer_cases.Customers.fixture

    def test_business_tools_remain_inside_the_main_work_surface(self):
        self.register()
        page=self.client.get('/inbox')
        self.assertIs(MainTools(page.get_data(as_text=True)).tools_in_main,True)

    def disclosure_open(self,response,section):
        match = re.search(rb'<details\b[^>]*\bid="'+section.encode()+rb'"[^>]*>',response.data)
        self.assertIsNotNone(match,'The expandable section must exist.')
        return bool(re.search(rb'\bopen(?:\s|=|>)',match[0]))

    def test_account_starts_with_profile_and_keeps_security_controls_available(self):
        self.fixture()
        for client in (self.client,self.customer):
            response = client.get('/account/settings')
            self.assertTrue(self.disclosure_open(response,'profile'))
            self.assertFalse(self.disclosure_open(response,'password'))
            self.assertFalse(self.disclosure_open(response,'sessions'))
            for action in (b'/account/profile',b'/account/password',b'/account/sessions/revoke-others'):
                self.assertIn(action,response.data)

    def test_password_and_session_errors_open_the_correct_security_section(self):
        self.fixture()
        for client in (self.client,self.customer):
            response = client.post('/account/password',data={'csrf_token':self.csrf(client,'/account/settings'),
                'current_password':'wrong','new_password':'short','password_confirm':'different'})
            self.assertEqual(response.status_code,422)
            self.assertTrue(self.disclosure_open(response,'password'))
            self.assertIn(b'current_password-error',response.data)
            response = client.post('/account/sessions/revoke-others',data={'csrf_token':self.csrf(client,'/account/settings'),'session_password':'wrong'})
            self.assertEqual(response.status_code,422)
            self.assertTrue(self.disclosure_open(response,'sessions'))

    def test_invalid_followup_opens_its_form_and_retains_submitted_action(self):
        _,public = self.register()
        lead = self.inquiry(public)
        response = self.client.post('/leads/'+lead+'/follow-up',data={'csrf_token':self.csrf(self.client,'/leads/'+lead),
            'version':'1','operation':'save','workspace_timezone':'UTC','assigned_user_id':'','followup_action':'Call about service',
            'followup_due':'not-a-time'})
        self.assertEqual(response.status_code,422)
        self.assertTrue(self.disclosure_open(response,'followup-tools'))
        self.assertIn(b'Call about service',response.data)
        self.assertIn(b'followup_due-error',response.data)
