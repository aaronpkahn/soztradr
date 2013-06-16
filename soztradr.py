import os
import urllib

from google.appengine.api import users
from google.appengine.ext import ndb
from google.appengine.api import mail

import jinja2
import webapp2


JINJA_ENVIRONMENT = jinja2.Environment(
	loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
	extensions=['jinja2.ext.autoescape'])

DEFAULT_SOZ_KEY = '_2013'

#todo make user the parent if this app ever grows
def soz_key():
	return ndb.Key('SoZ', 'SoZ_'+DEFAULT_SOZ_KEY)

class BaseRequestHandler(webapp2.RequestHandler):
	def get(self):
		if users.get_current_user():
			self.user = users.get_current_user()
			self.template_values = {
				'user': self.user
				,'logout_url': users.create_logout_url(self.request.uri)
			}
			return self.Get()
		else:
			self.redirect(users.create_login_url(self.request.uri))
	def post(self):
		if users.get_current_user():
			self.user = users.get_current_user()
			return self.Post()
		else:
			self.redirect(users.create_login_url(self.request.uri))

class SozTransaction(ndb.Model):
	"""Models an individual transaction"""
	from_user = ndb.UserProperty()
	to_email = ndb.StringProperty()
	to_user = ndb.UserProperty()
	date = ndb.DateTimeProperty(auto_now_add=True)
	quantity = ndb.IntegerProperty()
	description = ndb.StringProperty(indexed=False)
	rejected = ndb.BooleanProperty()
	accepted = ndb.BooleanProperty()

class SozQty(ndb.Model):
	qty = ndb.IntegerProperty()
	sent = ndb.IntegerProperty()
	received = ndb.IntegerProperty()
	owner = ndb.UserProperty()

def get_user_qty(user):
	soz_qty_key = ndb.Key('SozQty', user.user_id())
	soz_qty = soz_qty_key.get()

	if(not soz_qty):
		soz_qty = SozQty(id=user.user_id(), qty=0, owner=user, sent=0, received=0)
		soz_qty.put()
	return soz_qty

class ReconcilePage(BaseRequestHandler):
	def Get(self):
		userdetails = {}
		for sq in SozQty.query():
			sq.sent = 0
			sq.received = 0
			userdetails[sq.key.id()]=sq
		
		for st in SozTransaction.query():
			if(userdetails.has_key(st.from_user.user_id())):
				sq = userdetails[st.from_user.user_id()]
				self.response.write(st.from_user.user_id())
				self.response.write(' to ')
				self.response.write(st.from_user.email())
				self.response.write(' qty ')
				self.response.write(sq.qty)
				self.response.write(' sent ')
				self.response.write(st.quantity)
				self.response.write('<br/>')
				sq.owner = st.from_user
				sq.sent += st.quantity
			
			if(st.to_user and userdetails.has_key(st.to_user.user_id())):
				sq = userdetails[st.to_user.user_id()]
				self.response.write(st.from_user.user_id())
				self.response.write(' to ')
				self.response.write(st.from_user.email())
				self.response.write(' qty ')
				self.response.write(sq.qty)
				self.response.write(' received ')
				self.response.write(st.quantity)
				self.response.write('<br/>')
				sq.owner = st.to_user
				sq.received += st.quantity
		
		for sq in userdetails.values():
			sq.put()

class RecentPage(BaseRequestHandler):
	def Get(self):
		soz_query = SozTransaction.query(
			ancestor=soz_key()).filter(SozTransaction.accepted == True).order(-SozTransaction.date)
		soz_transactions = soz_query.fetch(40)

		self.template_values['soz_transactions'] = soz_transactions
	   
		template = JINJA_ENVIRONMENT.get_template('recent.html')
		self.response.write(template.render(self.template_values))

class SendPage(BaseRequestHandler):
	def Get(self):
		soz_qty = get_user_qty(self.user)
		self.template_values['share_count'] = soz_qty.qty
		template = JINJA_ENVIRONMENT.get_template('send.html')
		self.response.write(template.render(self.template_values))
	
	def Post(self):
		quantity = int(self.request.get('quantity'))

		soz_qty = get_user_qty(self.user)
		if(soz_qty.qty < quantity):
			#TODO: return error
			self.redirect('/');
			return
		
		to_email = self.request.get('to_email')
		
		to_email = to_email.lower()

		soz_qty.qty -= quantity
		soz_qty.sent += soz_transaction.quantity
		soz_qty.put()
		soz_transaction = SozTransaction(parent=soz_key())
		soz_transaction.to_email = to_email
		soz_transaction.from_user = self.user
		soz_transaction.quantity = quantity
		soz_transaction.description = self.request.get('description')
		skey = soz_transaction.put()
		
		#if not mail.is_email_valid(to_email):
			#TODO: prompt user to enter a valid address
		#else:
		confirmation_url = "http://soztradr.appspot.com/receive?id="+skey.urlsafe()
		sender_address = self.user.email()
		subject = "SoZ incoming"
		body = "Go here to peep the transaction:%s" % confirmation_url
		mail.send_mail(sender_address, to_email, subject, body)
		self.redirect('/mysoz')
		# self.response.write('urlsafe='+skey.urlsafe())+' id='+str(skey.id())+' kind='+str(skey.kind()))#?' + urllib.urlencode(query_params))	
		# self.redirect('/receive?id='+skey.urlsafe());
		
class MySozPage(BaseRequestHandler):
	def Get(self):
		soz_query = SozTransaction.query(
			ancestor=soz_key()
			).filter(ndb.OR(SozTransaction.from_user == self.user
				,SozTransaction.to_user == self.user
				,SozTransaction.to_email == self.user.email().lower())
			).order(-SozTransaction.date)
		soz_transactions = soz_query.fetch(40)

		soz_qty = get_user_qty(self.user)
		
		self.template_values['share_count'] = soz_qty.qty
		self.template_values['soz_transactions'] = soz_transactions
		template = JINJA_ENVIRONMENT.get_template('mysoz.html')
		self.response.write(template.render(self.template_values))


class ReceivePage(BaseRequestHandler):
	def Get(self):
		soz_key_param = self.request.get('id')
		
		if(not soz_key_param):
			self.redirect('/')
			return
		soz_key = ndb.Key(urlsafe=soz_key_param)
		soz_transaction = soz_key.get()
		
		if(not soz_transaction 
			#or self.user.email() != soz_transaction.to_email 
			or soz_transaction.rejected 
			or soz_transaction.to_user ):
			self.redirect('/')
			return

		self.template_values['soz_transaction'] = soz_transaction
		template = JINJA_ENVIRONMENT.get_template('receive.html')
		self.response.write(template.render(self.template_values))

class StatsPage(BaseRequestHandler):
	def Get(self):

		sozqtys = []
		for sq in SozQty.query():
			sozqtys.append(sq)

		self.template_values['userdetails'] = sorted( sozqtys, key=lambda sq: sq.sent-sq.received )

		template = JINJA_ENVIRONMENT.get_template('stats.html')
		self.response.write(template.render(self.template_values))

class Accept(BaseRequestHandler):
	def Get(self):
		self.redirect('/')
	def Post(self):
		soz_key_param = self.request.get('id')
		
		if(not soz_key_param):
			self.redirect('/')
			return
		soz_key = ndb.Key(urlsafe=soz_key_param)
		soz_transaction = soz_key.get()
		
		if( self.user.email().lower() != soz_transaction.to_email 
			or not soz_transaction 
			or soz_transaction.rejected 
			or soz_transaction.to_user ):
			self.redirect('/')
			return
		
		soz_qty = get_user_qty(self.user)
		
		#if we have a negative value, make sure the transaction won't bring user into the negatives
		if(soz_qty.qty+soz_transaction.quantity < 0):
			#TODO: return error
			self.redirect('/');
			return
		
		soz_qty.qty += soz_transaction.quantity
		soz_qty.received += soz_transaction.quantity
		soz_qty.put()
		soz_transaction.to_user = self.user
		soz_transaction.accepted = True
		soz_transaction.put()
		self.redirect('/mysoz')

class Reject(BaseRequestHandler):
	def Get(self):
		self.redirect('/')
	def Post(self):
		soz_key_param = self.request.get('id')
		
		if(not soz_key_param):
			self.redirect('/')
			return
		soz_key = ndb.Key(urlsafe=soz_key_param)
		soz_transaction = soz_key.get()
		
		if(self.user.email() != soz_transaction.to_email 
			or not soz_transaction 
			or soz_transaction.to_user 
			or soz_transaction.rejected ):
			#TODO: show error
			self.redirect('/')
			return
		
		soz_qty = get_user_qty(soz_transaction.from_user)
		soz_qty.qty += soz_transaction.quantity
		soz_qty.sent -= soz_transaction.quantity
		soz_qty.put()
		
		soz_transaction.rejected = True
		
		soz_transaction.put()
		self.redirect('/mysoz')

class Delete(BaseRequestHandler):
	def Get(self):
		self.redirect('/')
	def Post(self):
		soz_key_param = self.request.get('id')
		
		if(not soz_key_param):
			self.redirect('/')
			return
		soz_key = ndb.Key(urlsafe=soz_key_param)
		soz_transaction = soz_key.get()
		
		if(not soz_transaction 
			or soz_transaction.to_user 
			or soz_transaction.rejected):
			#TODO: show error
			self.redirect('/')
			return
		
		soz_qty = get_user_qty(soz_transaction.from_user)
		soz_qty.qty += soz_transaction.quantity
		soz_qty.sent -= soz_transaction.quantity
		soz_qty.put()
		
		soz_key.delete()
		self.redirect('/mysoz')

application = webapp2.WSGIApplication([
	('/', SendPage),
	('/recent', RecentPage),
	('/mysoz', MySozPage),
	('/send', SendPage),
	('/receive', ReceivePage),
	('/accept', Accept),
	('/reject', Reject),
	('/delete', Delete),
	('/stats', StatsPage),
	('/reconcile', ReconcilePage)
], debug=True)