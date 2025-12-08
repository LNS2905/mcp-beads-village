import asyncio
import json
import sys
import os
os.environ['PYTHONIOENCODING'] = 'utf-8'

async def test():
    proc = await asyncio.create_subprocess_exec(
        sys.executable, '-m', 'beads_village.server',
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    
    # Give server time to start
    await asyncio.sleep(1)
    
    init_req = json.dumps({
        'jsonrpc': '2.0',
        'id': 1,
        'method': 'initialize',
        'params': {
            'protocolVersion': '2024-11-05', 
            'capabilities': {}, 
            'clientInfo': {'name': 'test', 'version': '1.0'}
        }
    }) + '\n'
    
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    print(f"Sending: {init_req[:100]}")
    proc.stdin.write(init_req.encode())
    await proc.stdin.drain()
    
    print("Waiting for response...")
    try:
        line = await asyncio.wait_for(proc.stdout.readline(), timeout=10.0)
        response = line.decode('utf-8', errors='replace')[:500]
        print(f'Response: {response}')
        
        # Try tools/list
        tools_req = json.dumps({
            'jsonrpc': '2.0',
            'id': 2,
            'method': 'tools/list',
            'params': {}
        }) + '\n'
        
        proc.stdin.write(tools_req.encode())
        await proc.stdin.drain()
        
        line2 = await asyncio.wait_for(proc.stdout.readline(), timeout=10.0)
        tools_response = line2.decode('utf-8', errors='replace')[:2000]
        print(f'Tools response: {tools_response}')
        
    except asyncio.TimeoutError:
        print('TIMEOUT!')
        stderr = await proc.stderr.read()
        print(f'STDERR: {stderr.decode()[:1000]}')
    
    proc.kill()

if __name__ == '__main__':
    asyncio.run(test())
