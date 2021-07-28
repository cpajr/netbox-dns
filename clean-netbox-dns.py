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