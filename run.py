#!/usr/bin/env python3

import subprocess
import re
import shlex
import datetime
import os
import sys
import json

# Prompt to choose a USB device.
devices = (subprocess.check_output(['lsusb'])).splitlines()
devices = list(map(lambda device: device.decode('utf8'), devices))

for index, device in enumerate(devices):
	print('{:2d} | {}'.format(index + 1, device))
device_index = int(input('\nSelect a device: '))

# Parse selection.
device = devices[device_index - 1]
device_ids = re.findall(r'([a-zA-Z0-9]{4}):([a-zA-Z0-9]{4})', device)[0]
vendor_id = device_ids[0]
product_id = device_ids[1]

target='ubuntu-16.04'
target_directory='./ubuntu-16.04'

# https://stackoverflow.com/a/36971820/1459103
def parse_shell_var(line):
	return shlex.split(line, posix=True)[0].split('=', 1)

# Load config.
with open(target_directory + '/Vagrantfile.conf', 'r') as f:
	configs = dict(parse_shell_var(line) for line in f if '=' in line)

# Restore base snapshot
snapshots = (subprocess.check_output(['vagrant', 'snapshot', 'list'], cwd=target_directory)).decode('utf8')
if not re.match(r"" + re.escape(configs['SNAPSHOT_NAME']) + "", snapshots):
	print('Snapshot not found')
	exit(1)
subprocess.call(['vagrant', 'halt', '--force'], cwd=target_directory)
subprocess.call(['VBoxManage', 'snapshot', configs['MACHINE_NAME'], 'restore', configs['SNAPSHOT_NAME']], cwd=target_directory)

# Enable USB
subprocess.call(['VBoxManage', 'modifyvm', configs['MACHINE_NAME'], '--usb', 'on'], cwd=target_directory)
subprocess.call(['VBoxManage', 'modifyvm', configs['MACHINE_NAME'], '--usbxhci', 'on'], cwd=target_directory)

# Add filter for our device
subprocess.call([
	'VBoxManage',
	'usbfilter',
	'add',
	'0',
	'--name',
	'USB WiFI NIC',
	'--target',
	configs['MACHINE_NAME'],
	'--vendorid',
	vendor_id,
	'--productid',
	product_id
], cwd=target_directory)

now = datetime.datetime.utcnow()
formatted = now.strftime('%Y-%m-%d-%H-%M-%S')

current_dir = os.path.dirname(os.path.realpath(__file__))
log_dir = current_dir + '/logs/' + formatted

os.mkdir(log_dir)
os.mkdir(log_dir + '/downloads')
os.mkdir(log_dir + '/uploads')

def run_test(command, summary_log_file_path, key):
	args = shlex.split(command)
	proc = subprocess.Popen(args, cwd=target_directory, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	with open(summary_log_file_path, "w") as summary_log_file:
		stdoutdata, stderrdata = proc.communicate(input=None)

		if proc.returncode != 0:
			print("Unexpected error occurred (probably NIC not detected in VM)")
			return

		out = stdoutdata.decode('utf8')
		data = json.loads(out)

		error = data.get("error")
		if error != None:
			raise Exception(error)

		# Upload
		if key == 'sum_sent':
			test_log_dir = 'uploads'
		# Download
		elif key == 'sum_received':
			test_log_dir = 'downloads'

		file_name = datetime.datetime.utcnow().strftime('%Y-%m-%d-%H-%M-%S') + '.json'

		# Write complete log file for this test iteration.
		test_log = open(log_dir + '/' + test_log_dir + '/' + file_name, 'a')
		test_log.write(out)
		test_log.close()

		# Write summary test information to stdout and summary log file.
		bits = data.get('end').get(key).get('bits_per_second')
		mbps = bits / 1000000
		print('{:f} {:s}'.format(mbps, 'Mbps'))
		summary_log_file.write(str(mbps))
		summary_log_file.close()

vagrant_up_log = open(log_dir + '/vagrant.log', 'w')
subprocess.call(['vagrant', 'up'], cwd=target_directory, stdout=vagrant_up_log, stderr=vagrant_up_log)

wifi_connect_log = open(log_dir + '/wifi-connect.log', 'w')
subprocess.call(['vagrant', 'ssh', '--', '/vbin/wifi-connect'], cwd=target_directory, stdout=wifi_connect_log, stderr=wifi_connect_log)

info_log = open(log_dir + '/info.log', 'w')
subprocess.call(['vagrant', 'ssh', '--', '/vbin/info'], cwd=target_directory, stdout=info_log, stderr=info_log)

download_log_dir = log_dir + '/download-results.txt'
upload_log_dir = log_dir + '/upload-results.txt'

max = 50
width = len(str(max))

for x in range(1, max):
	try:
		print('{:{width}d} | download test'.format(x, width=width))
		run_test('vagrant ssh -- /vbin/wifi-download-test.sh', download_log_dir, 'sum_received')
		print('{:{width}d} | upload test'.format(x, width=width))
		run_test('vagrant ssh -- /vbin/wifi-upload-test.sh', upload_log_dir, 'sum_sent')
	except Exception as e:
		print(e)