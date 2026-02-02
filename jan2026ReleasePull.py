import time
import os
import requests
from urllib.parse import unquote
from bs4 import BeautifulSoup

from util import verify
import argparse

def main():
	parser = argparse.ArgumentParser(description='Download DOJ release files')
	parser.add_argument('--verbose', action='store_true', help='Enable verbose debug output')
	parser.add_argument('--non-interactive', action='store_true', dest='non_interactive', help='Run without prompting to continue (useful for CI)')
	args = parser.parse_args()
	verbose = args.verbose
	non_interactive = args.non_interactive
	with open('sample.html', 'r', encoding='utf-8') as f:
		soup = BeautifulSoup(f, 'html.parser')

	if verbose:
		print('Verbose mode enabled')
	item_list_div = soup.find('div', class_='item-list')
	if not item_list_div:
		print('No item-list div found.')
		return

	items = item_list_div.find_all('li')
	root_url = "https://www.justice.gov"
	timestamp = time.strftime("%Y%m%d_%H%M%S")
	output_dir = f"jan2026ReleasePull_{timestamp}"
	os.makedirs(output_dir, exist_ok=True)
	error_filename = os.path.join(output_dir, f"error_log_{timestamp}.txt")

	for item in items:
		link = item.find('a')
		if link and link.has_attr('href'):
			file_url = root_url + link['href']
			try:
				# Use headless Playwright-based pull as primary mechanism
				result = verify.pull_doj_file_headless(file_url, output_dir, timeout=30, verbose=verbose, non_interactive=non_interactive)
				if not result:
					error_msg = f"[ERROR] Failed to obtain {file_url} via headless pull. This file may need manual download. Continuing."
					print(error_msg)
					with open(error_filename, 'a', encoding='utf-8') as ef:
						ef.write(error_msg + '\n')
					continue
				content = result.get('content')
				returned_filename = result.get('filename')
				# Prefer the displayed filename from the page, fallback to returned filename
				display_name = link.get_text(strip=True)
				if not display_name:
					display_name = returned_filename or unquote(os.path.basename(link['href']))
				filename = display_name.replace('/', '_')
				file_path = os.path.join(output_dir, filename)
				with open(file_path, 'wb') as out_f:
					out_f.write(content)
				print(f"Saved: {file_path} (size: {len(content)} bytes)")
			except Exception as e:
				error_msg = f"[ERROR] Failed to fetch {file_url}: {e}"
				print(error_msg)
				with open(error_filename, 'a', encoding='utf-8') as ef:
					ef.write(error_msg + '\n')
		else:
			error_msg = f"[ERROR] Missing or malformed link in item: {item.get_text(strip=True)}"
			print(error_msg)
			with open(error_filename, 'a', encoding='utf-8') as ef:
				ef.write(error_msg + '\n')

main()