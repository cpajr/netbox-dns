#!/usr/bin/env python

'''
************************************************************
This script is used to pull new IPAM entries from Netbox 
and create corresponding entries into Windows DNS.    

Author: Charles Allen
Date: 29 Jul 2021
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

class NetboxObjects():
	
	def __init__(self):
		self.list_entries = []

	def add(self,change_id,obj_id,action,prechange_data,postchange_data):


		if((action == "create" or action == "update") and postchange_data['address'] == ""):
			pass
		elif (action == "create" and not checkIpAddr(postchange_data['address'],obj_id)):
			pass
		elif (action == "update" and not checkIpAddr(postchange_data['address'],obj_id)):
			pass
		elif (action == "delete" and not checkIpAddr(prechange_data['address'],obj_id)):
			pass
		else:
			self.list_entries.append(
				{'change_id':change_id, 
				'obj_id':obj_id,  
				'action':action,
				'prechange_data':prechange_data,
				'postchange_data': postchange_data})

	def print(self):

		print ("****************Begin List****************")
		for entry in self.list_entries:
			print (entry)
			print("+++++++++++++++++++++++++++++++++++++++++\n")
		print ("****************End List****************")

	def processList(self,testFlag = False):

		if (testFlag):
			for entry in self.list_entries:
				if (entry['action'] == 'create'):
					print ("Created: {}".format(entry['postchange_data']['dns_name']))
				elif (entry['action'] == 'delete'):
					print ("Deleted: {}".format(entry['prechange_data']['dns_name']))
				elif (entry['action'] == 'update'):
					print ("Updated: {}:{}".format(entry['postchange_data']['dns_name'],entry['postchange_data']['address']))
		else:
			for entry in self.list_entries:
				if (entry['action'] == 'create'):
					dnsCmd(
						dns_name=reviseDnsName(entry['postchange_data']['dns_name']),
						ip_addr=removeCidr(entry['postchange_data']['address']),
						action=entry['action']
					)
				elif (entry['action'] == 'delete'):
					dnsCmd(
						dns_name=reviseDnsName(entry['prechange_data']['dns_name']),
						ip_addr=removeCidr(entry['prechange_data']['address']),
						action=entry['action']
					)					
				elif (entry['action'] == 'update'):
					dnsCmd(
						dns_name=reviseDnsName(entry['prechange_data']['dns_name']),
						ip_addr=removeCidr(entry['prechange_data']['address']),
						action='delete'
					)
					dnsCmd(
						dns_name=reviseDnsName(entry['postchange_data']['dns_name']),
						ip_addr=removeCidr(entry['postchange_data']['address']),
						action='create'
					)	


#***************************************
#		METHODS
#***************************************
def runPwshCmd(cmd):
	returnInfo = subprocess.run(["powershell", "-Command", cmd], capture_output=True)
	
	if (returnInfo.returncode != 0):
		#logging.critical("Failed execution of powershell script: {}".format(cmd))
		return False
	else:
		logging.info("Successful powershell execution: {}".format(cmd))
		return True

def dnsCmd(dns_name, ip_addr, action):

	if (action == "create" and not existDns(dns_name)):
		cmd = "Add-DnsServerResourceRecordA -ComputerName {} -Name \"{}\" -ZoneName {} -IPv4Address \"{}\" -CreatePtr".format(dns_server,dns_name,zone_name,ip_addr)
		runPwshCmd(cmd)
	elif (action == "delete" and existDns(dns_name)):
		cmd = "Remove-DnsServerResourceRecord -ComputerName {} -ZoneName {} -RRType \"A\" -Name \"{}\" -RecordData \"{}\" -Force".format(dns_server,zone_name,dns_name,ip_addr)
		runPwshCmd(cmd)
	else:
		logging.critical("Unexpected action in dnsCmd: {}::{}::{}".format(dns_name, ip_addr, action))

def existDns(dns_name):

	cmd = "Get-DnsServerResourceRecord -ZoneName {} -Name {} -ComputerName {}".format(zone_name, dns_name, dns_server)
	if (runPwshCmd(cmd)):
		#print ("Entry exists")
		return True
	else:
		#print ("Entry doesn't exist")
		return False



'''
++++++++++++++++++++++++++++++++++++++++++++++++++++++++
				Output processing
++++++++++++++++++++++++++++++++++++++++++++++++++++++++
'''

def checkIpAddr(ip_addr,obj_id):
	try:
		intIpAddr = re.search(r"^(?:10|192).(?:\d{1,3}|168).\d{1,3}.\d{1,3}", ip_addr).group(0)
	except AttributeError:
		intIpAddr = ""

	if (intIpAddr != ""):
		return True
	else:
		logging.info('Unexpected IP Address({}) used on obj_id:{}'.format(ip_addr,obj_id))
		return False

def removeCidr(ip_addr):

	return re.sub(r'\/\d{2}','',ip_addr)

def reviseDnsName(dns_name):

	try:
		result = re.search(r''+re.escape(zone_name)+'$', dns_name).group(0)
	except AttributeError:
		result = ""

	if (result != ""):
		return re.sub(r'\.'+re.escape(zone_name),'',dns_name)

	else:
		return dns_name

def procOutput(output):

	theObjects = NetboxObjects()

	if (output['count'] != 0):

		for item in reversed(output['results']):
			theObjects.add(
				change_id=item['id'],
				obj_id=item['changed_object_id'],
				action=item['action']['value'],
				prechange_data=item['prechange_data'],
				postchange_data=item['postchange_data']
				)

		theObjects.processList()

'''
++++++++++++++++++++++++++++++++++++++++++++++++++++++++
				API Call Methods
++++++++++++++++++++++++++++++++++++++++++++++++++++++++
'''

def todayDate():

	ts = datetime.utcnow() - timedelta(minutes=10)

	year = ts.strftime("%Y")
	month = ts.strftime("%m")
	day = ts.strftime("%d")
	hour = ts.strftime("%H")
	minute = ts.strftime("%M")
	second = ts.strftime("%S")
	
	return "{}-{}-{}+{}%3A{}%3A{}".format(year,month,day,hour,minute,second)

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

'''
++++++++++++++++++++++++++++++++++++++++++++++++++++++++
				Logging
++++++++++++++++++++++++++++++++++++++++++++++++++++++++
'''
#Haven't decided yet if I want to do this or not

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
>>>>>>> cleanup
