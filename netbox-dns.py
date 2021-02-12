#!/usr/bin/env python3

'''
************************************************************
This script is used to pull new IPAM entries from Netbox 
and create corresponding entries into Windows DNS.    

Author: Charles Allen
Date: 21 Jan 2020
************************************************************
'''


import json
import requests
import os
from datetime import datetime, timedelta
import re
import socket
import logging
import subprocess

#***************************************
#		CONFIG IMPORT
#***************************************
import config

#***************************************
#		GLOBAL VARIABLES
#***************************************

api_token = config.api_token
api_url_host = config.api_url_host
api_url_base = config.api_url_base
api_url_base_suffix = config.api_url_base_suffix
zone_name = config.zone_name
dns_server = config.dns_server

#***************************************
#		CLASSES
#***************************************

class AddDNS():
	
	def __init__(self):
		self.list_entries = []

	def add(self,change_id,obj_id,changelog_time,obj_chg_time,dns_name,ip_addr,action):

		#Execute checks on the incoming data
		if (isIntIpAddr(ip_addr=ip_addr, obj_id=obj_id) and dns_name != ""):
			self.list_entries.append(
							{'change_id':change_id, 
							'obj_id':obj_id, 
							'changelog_time':changelog_time, 
							'dns_name':procDnsName(dns_name), 
							'obj_chg_time':obj_chg_time,
							'ip_addr': removeCidr(ip_addr), 
							'action':action })

	def print(self):

		print ("****************Begin List****************")
		for entry in self.list_entries:
			print (entry)
		print ("****************End List****************")

	def sortList(self):
		'''
		This function simply sorts the list in reverse order.  
		'''
		self.list_entries = sorted(self.list_entries,key = lambda i: i['changelog_time'])

	def testProcess(self):
		for entry in self.list_entries:
			if (entry['action'] == 'Created' and not dnsEntryExist(hostname=entry['dns_name'])):
				print ("Created: {}".format(entry['dns_name']))
			elif (entry['action'] == 'Deleted'):
				print ("Deleted: {}".format(entry['dns_name']))
			elif (entry['action'] == 'Updated'):
				self.processUpdate(entry,test=True)

	def processList(self):
		for entry in self.list_entries:

			if (entry['action'] == 'Created' and not dnsEntryExist(hostname=entry['dns_name'])):
				dnsCmd(dns_name=entry['dns_name'], ip_addr=entry['ip_addr'], action=entry['action'])
			elif (entry['action'] == 'Deleted'):
				dnsCmd(dns_name=entry['dns_name'], ip_addr=entry['ip_addr'], action=entry['action'])
			elif (entry['action'] == 'Updated'):
				self.processUpdate(entry)

	def processUpdate(self, new_entry,test=False):

		#First, need to query API for the next most recent change
		base_url = "/api/extras/object-changes/?"
		param1 = "changed_object_id=" + str(new_entry['obj_id'])
		param2 = "&changed_object_type=ipam.ipaddress"
		param3 = "&time_before=" + dateChange(new_entry['obj_chg_time'])

		url = createUrl(base_url + param1 + param2 + param3)
		output = apiCall(headers=createHeader(), api_url=url)
		tmpOutput = output['results'][0]
		
		#Format the output into our expected Dictionary style
		old_entry = returnDict( 
					obj_id = tmpOutput['changed_object_id'],
					change_id = tmpOutput['id'],
					changelog_time = tmpOutput['time'],
					obj_chg_time = tmpOutput['object_data']['last_updated'],
					dns_name = tmpOutput['object_data']['dns_name'],
					ip_addr = tmpOutput['object_data']['address'],
					action = tmpOutput['action']['label']
					)
		
		'''
		We need to do some comparison between the old entry and new
		'''
		if (test == False):

			#Delete Old Entry
			dnsCmd(dns_name=old_entry['dns_name'], ip_addr=old_entry['ip_addr'], action='Deleted')

			#Recreate New Entry
			dnsCmd(dns_name=new_entry['dns_name'], ip_addr=new_entry['ip_addr'], action='Created')
		else:
			print ("Delete: {},{}".format(old_entry['dns_name'],old_entry['ip_addr']))
			print ("Create: {},{}".format(new_entry['dns_name'],new_entry['ip_addr']))

#***************************************
#		METHODS
#***************************************
def dnsEntryExist(hostname="",ip_addr = ""):
	if (hostname != ""):
		try:
			dns_lookup = socket.gethostbyname(hostname)
		except socket.gaierror:
			logging.info('No existing DNS entry for {}:{}'.format(hostname,ip_addr))
			dns_lookup = ""
	elif(ip_addr != ""):
		try:
			dns_lookup = socket.gethostbyaddr(ip_addr)
		except socket.gaierror:
			logging.info('No existing DNS entry for {}:{}'.format(hostname,ip_addr))
			dns_lookup = ""

	if(dns_lookup == ""):
		return False
	else:
		return True

def returnDict(change_id,obj_id,changelog_time,obj_chg_time,dns_name,ip_addr,action):
	return { 
			'change_id':change_id, 
			'obj_id':obj_id, 
			'changelog_time':changelog_time, 
			'obj_chg_time':obj_chg_time,
			'dns_name':procDnsName(dns_name),
			'ip_addr': removeCidr(ip_addr), 
			'action':action 
			}

def dateChange(date):

	returnDate = date.replace('T','+')
	returnDate = returnDate.replace(':',"%3A")

	return returnDate

def todayDate():

	ts = datetime.utcnow() - timedelta(minutes=15)

	year = ts.strftime("%Y")
	month = ts.strftime("%m")
	day = ts.strftime("%d")
	hour = ts.strftime("%H")
	minute = ts.strftime("%M")
	second = ts.strftime("%S")
	
	return "{}-{}-{}+{}%3A{}%3A{}".format(year,month,day,hour,minute,second)

def runPwshCmd(cmd):
	returnInfo = subprocess.run(["powershell", "-Command", cmd], capture_output=True)
	
	if (returnInfo.returncode != 0):
		logging.critical("Failed execution of powershell script: {}".format(cmd))
	else:
		logging.info("Successful powershell execution: {}".format(cmd))

def dnsCmd(dns_name, ip_addr, action):

	#We will act on three different actions: created, updated, and deleted
	returnCode = 0

	if (action == "Created"):
		cmd = "Add-DnsServerResourceRecordA -ComputerName {} -Name \"{}\" -ZoneName \"{}\" -IPv4Address \"{}\" -CreatePtr".format(dns_server,dns_name,zone_name,ip_addr)
		runPwshCmd(cmd)
	elif (action == "Deleted"):
		cmd = "Remove-DnsServerResourceRecord -ComputerName {} -ZoneName \"{}\" -RRType \"A\" -Name \"{}\" -RecordData \"{}\" -Force".format(dns_server,zone_name,dns_name,ip_addr)
		runPwshCmd(cmd)
	else:
		logging.critical("Unexpected action in dnsCmd: {}-{}-{}".format(dns_name, ip_addr, action))

def procDnsName(dns_name):

	'''
	It is preferred that the hostname not contain the dns suffix.  This function
	will remove the DNS suffix.  
	'''
	try:
		result = re.search(r''+re.escape(zone_name)+'$', dns_name).group(0)
	except AttributeError:
		result = ""

	if (result != ""):
		return re.sub(r'\.'+re.escape(zone_name),'',dns_name)

	else:
		return dns_name

def removeCidr(ip_addr):

	return re.sub(r'\/\d{2}','',ip_addr)

def isIntIpAddr(ip_addr,obj_id):

	try:
		intIpAddr = re.search(r"^(?:10|192).(?:\d{1,3}|168).\d{1,3}.\d{1,3}", ip_addr).group(0)
	except AttributeError:
		intIpAddr = ""

	if (intIpAddr != ""):
		return True
	else:
		logging.info('Public IP Address({}) used on obj_id:{}'.format(ip_addr,obj_id))
		return False

def createUrl (url=""):

	if (url == ""):
		return api_url_host + api_url_base + todayDate() + api_url_base_suffix
	else:
		return api_url_host + url

def createHeader():

	return {'Content-Type': 'application/json','Authorization': 'Token {0}'.format(api_token)}

def apiCall(headers, api_url):

	try:
		response = requests.get(api_url, headers=headers)
	except requests.exceptions.RequestException as e:
		logging.critical("Exception in executing API call {}".format(e))
		raise SystemExit(e)
	
	return json.loads(response.content.decode('utf-8'))

def procOutput(output):

	writer = AddDNS()

	if (output['count'] != 0):
		for i in output['results']:

			if (i['object_data']['status'] != 'active'):
				continue

			changeID = i['id']
			objID = i['changed_object_id']
			changeTime = i['time']
			objChgTime = i['object_data']['last_updated']
			ipAddr = i['object_data']['address']
			dnsName = i['object_data']['dns_name']
			theAction = i['action']['label']

			writer.add(change_id = changeID, obj_id = objID, 
						changelog_time = changeTime, dns_name=dnsName, 
						obj_chg_time=objChgTime, ip_addr=ipAddr, action=theAction)
	
	writer.sortList()
	#writer.processList()
	writer.testProcess()

#***************************************
#		MAIN ROUTINE
#***************************************
def main():

	#logging configuration
	logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s', filename='netbox-dns.log', level=logging.INFO, datefmt = '%b %d %Y %H:%M:%S')
	logging.info('Starting script')

	output = apiCall(headers=createHeader(), api_url=createUrl())
	procOutput(output)

	logging.info('Finishing script')

if __name__ == "__main__":
	main()
