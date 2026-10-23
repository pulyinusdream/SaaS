from html.parser import HTMLParser
import unittest
import test_app as fixtures


class LoginElements(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.images=[]
        self.headings=[]
        self.current=None
        self.feed(html)
    def handle_starttag(self,tag,attrs):
        if tag=='img': self.images.append(dict(attrs))
        if tag=='h1': self.current=''
    def handle_data(self,data):
        if self.current is not None: self.current+=data
    def handle_endtag(self,tag):
        if tag=='h1' and self.current is not None:
            self.headings.append(self.current.strip());self.current=None


class UIHierarchy(unittest.TestCase):
    setUp=fixtures.AccountsAndLeads.setUp
    tearDown=fixtures.AccountsAndLeads.tearDown

    def test_both_logins_have_a_local_dimensioned_image_and_one_role_heading(self):
        for path,role in (('/login','Admin sign in'),('/customer/login','Customer sign in')):
            with self.subTest(path=path):
                response=self.client.get(path)
                parsed=LoginElements(response.get_data(as_text=True))
                self.assertEqual(parsed.headings,[role])
                self.assertEqual(len(parsed.images),1)
                photo=parsed.images[0]
                self.assertTrue(photo['src'].startswith('/static/'))
                self.assertIn('alt',photo)
                self.assertGreater(int(photo['width']),0)
                self.assertGreater(int(photo['height']),0)
                asset=self.client.get(photo['src'])
                self.assertEqual(asset.status_code,200)
                self.assertEqual(asset.mimetype,'image/webp')
                asset.close()
                self.assertIn(b'autocomplete="current-password"',response.data)
                self.assertIn(b'name="csrf_token"',response.data)
