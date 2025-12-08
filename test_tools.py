import asyncio
import os
import json
os.environ['BEADS_WS'] = 'C:\\Working\\Code\\ProxyAPI\\CLIPROXYAPI'

# Test bd command directly
async def bd(*args):
    workspace = os.environ.get("BEADS_WS", os.getcwd())
    try:
        proc = await asyncio.create_subprocess_exec(
            "bd", *args, "--json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.DEVNULL,
            cwd=workspace,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=10.0)
        except asyncio.TimeoutError:
            proc.kill()
            return {"error": "bd command timeout after 10s"}
        if proc.returncode != 0:
            return {"error": err.decode()[:200]}
        return json.loads(out.decode()) if out.strip() else {}
    except Exception as e:
        return {"error": str(e)[:200]}

async def test():
    print('Testing bd init...')
    r = await bd("init")
    print(f'init: {r}')
    
    print('Testing bd list...')
    r = await bd("list", "--status", "open")
    print(f'list: {r}')
    
    print('Testing bd stats...')
    r = await bd("stats")
    print(f'stats: {r}')

asyncio.run(test())
