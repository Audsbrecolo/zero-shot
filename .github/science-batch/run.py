"""Run a published, checksum-verified subset through the unmodified detector."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BRANCH_COMMIT = 'e265cbb0832b62af261511a5d2506d994fd35681'
BASE_URL = 'http://127.0.0.1:18257'
MODEL = 'Qwen/Qwen3-VL-8B-Instruct'
UPSTREAM = 'https://github.com/Joyce-yoyo/SciFigDetect/blob/24093d014b0e09f40c7904f28de3022c07ba17e6/'
COLUMNS = {'real':'real_url','banana':'banana','gpt_v1':'gpt_v1','gpt_v2':'gpt_v2'}


def assigned(shard):
    with (ROOT/'examples/science/paper-pairs.csv').open() as f:
        pairs = list(csv.DictReader(f))
    with (HERE/'inputs.csv').open() as f:
        records = list(csv.DictReader(f))
    assert len(records) == 84 and len({r['sha256'] for r in records}) == 84
    tasks = []
    for row in records:
        if row['complete_at_dispatch'] == '1':
            continue
        index, source = row['id'].split('-',1)
        pair = pairs[int(index)-1]
        url = pair[COLUMNS[source]]
        assert url.startswith(UPSTREAM)
        tasks.append((row,source,pair['local_image'],url.replace('github.com','raw.githubusercontent.com').replace('/blob/','/')))
    return tasks[shard::20]


def process(task):
    row,source,original,url = task
    key = row['id']
    output = Path('batch-output').resolve()
    report = output/(key+'.json')
    logpath = output/(key+'.log')
    image = Path(os.environ['RUNNER_TEMP'])/(row['sha256']+'.png')
    try:
        if source == 'real':
            image.write_bytes((ROOT/original).read_bytes())
        else:
            subprocess.run(['curl','--fail','--silent','--show-error','--location','--retry','3','--max-time','150','--output',str(image),url],check=True)
        assert hashlib.sha256(image.read_bytes()).hexdigest() == row['sha256'], 'input SHA-256 mismatch'
        with logpath.open('w', encoding='utf-8') as log:
            rc = subprocess.run([sys.executable,'-u',str(ROOT/'detect.py'),str(image),'--profile','paper','--mode','agents','--backend','api','--base-url',BASE_URL+'/v1','--binary','--out',str(report)],stdout=log,stderr=subprocess.STDOUT,cwd=ROOT).returncode
        if rc == 0:
            parsed = json.loads(report.read_text())
            assert parsed['image']['sha256'] == row['sha256'] and len(parsed['inspections']) == 4 and parsed['model']==MODEL
        print(key, 'detector exit', rc, flush=True)
        return (key,rc)
    except Exception as e:
        with logpath.open('a', encoding='utf-8') as log:
            print(type(e).__name__,str(e),file=log)
        print(key,'input or runner error',type(e).__name__,flush=True)
        return (key,2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('shard',type=int)
    parser.add_argument('--list',action='store_true')
    args = parser.parse_args()
    tasks = assigned(args.shard)
    if args.list:
        print(' '.join(t[0]['id'] for t in tasks))
        return
    output = Path('batch-output'); output.mkdir(exist_ok=True)
    runtime = Path(os.environ['RUNNER_TEMP'])/'science-model'
    import PIL, numpy
    threads = min(8, len(os.sched_getaffinity(0)))
    meta = dict(base_commit=BRANCH_COMMIT,workflow=os.getenv('GITHUB_SHA'),run_id=os.getenv('GITHUB_RUN_ID'),run_attempt=os.getenv('GITHUB_RUN_ATTEMPT'),shard=args.shard,inputs=[r[0]['id'] for r in tasks],threads=threads,pillow=PIL.__version__,numpy=numpy.__version__)
    (output/'runner.json').write_text(json.dumps(meta,indent=2))
    cmd = [str(runtime/'llama-b8219/llama-server'),'-m',str(runtime/'qwen.gguf'),'--mmproj',str(runtime/'vision.gguf'),'--alias',MODEL,'--host','127.0.0.1','--port','18257','--ctx-size','8192','-np','2','-t',str(threads),'-tb',str(threads),'--no-repack','--cache-ram','0','-ub','128','--image-max-tokens','480','--no-warmup']
    with (output/'server.log').open('w') as log:
        proc = subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT)
        try:
            for _ in range(180):
                if proc.poll() is not None: raise RuntimeError('model server stopped at startup')
                try:
                    with urlopen(BASE_URL+'/health',timeout=2) as response:
                        if response.status==200:break
                except (URLError,TimeoutError):pass
                time.sleep(1)
            else:raise RuntimeError('model server startup timed out')
            with ThreadPoolExecutor(2) as pool: statuses = dict(pool.map(process,tasks))
            (output/'status.json').write_text(json.dumps(statuses,indent=2))
        finally:
            if proc.poll() is None:proc.terminate()
            proc.wait(timeout=60)

if __name__=='__main__':
    main()
