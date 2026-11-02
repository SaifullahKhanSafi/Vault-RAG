"""Wait for the local CI stack without hiding a failed readiness response."""
import argparse
import json
import time
from urllib.request import urlopen
from urllib.error import URLError

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--url',default='http://localhost:8000/health/ready');parser.add_argument('--timeout',type=int,default=90);args=parser.parse_args()
    deadline=time.monotonic()+args.timeout
    while time.monotonic()<deadline:
        try:
            with urlopen(args.url,timeout=5) as response:
                if response.status==200 and json.load(response).get('status')=='healthy':print('API, database, worker and model protocol ready.');return
        except (URLError,TimeoutError,ValueError):pass
        time.sleep(1)
    raise SystemExit('Stack did not become ready; inspect service logs.')

if __name__=='__main__':main()
