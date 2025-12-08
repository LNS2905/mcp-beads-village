#!/usr/bin/env node
/**
 * Beads Village MCP Server - Cross-platform launcher
 * 
 * Spawns the Python MCP server and forwards stdio.
 * Works on Windows, macOS, and Linux.
 */

const { spawn, spawnSync } = require('child_process');
const path = require('path');
const fs = require('fs');

const serverPath = path.join(__dirname, '..', 'beads_village', 'server.py');

if (!fs.existsSync(serverPath)) {
    console.error('Error: server.py not found at', serverPath);
    process.exit(1);
}

function findPython() {
    const isWindows = process.platform === 'win32';
    const pythonCommands = isWindows 
        ? ['python', 'python3', 'py']
        : ['python3', 'python'];
    
    for (const cmd of pythonCommands) {
        try {
            const result = spawnSync(cmd, ['--version'], {
                stdio: 'pipe',
                windowsHide: true
            });
            if (result.status === 0) {
                return cmd;
            }
        } catch (e) {
            continue;
        }
    }
    return null;
}

const pythonCmd = findPython();

if (!pythonCmd) {
    console.error('Error: Python not found. Please install Python 3.8+');
    console.error('  Windows: https://www.python.org/downloads/');
    console.error('  macOS:   brew install python3');
    console.error('  Linux:   apt install python3 / yum install python3');
    process.exit(1);
}

const server = spawn(pythonCmd, [serverPath], {
    stdio: ['pipe', 'pipe', 'inherit'],
    env: {
        ...process.env,
        PYTHONUNBUFFERED: '1',
        PYTHONIOENCODING: 'utf-8'
    },
    windowsHide: true
});

process.stdin.pipe(server.stdin);
server.stdout.pipe(process.stdout);

server.on('error', (err) => {
    console.error('Failed to start server:', err.message);
    process.exit(1);
});

server.on('close', (code) => {
    process.exit(code || 0);
});

process.on('SIGINT', () => {
    server.kill('SIGINT');
});

process.on('SIGTERM', () => {
    server.kill('SIGTERM');
});
