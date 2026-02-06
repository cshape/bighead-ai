const { spawn } = require('child_process');
const http = require('http');
const path = require('path');

let backendProcess = null;
let frontendProcess = null;

function waitForServer(url, maxRetries = 30, interval = 1000) {
  return new Promise((resolve, reject) => {
    let retries = 0;
    const check = () => {
      http.get(url, (res) => {
        resolve(true);
      }).on('error', () => {
        retries++;
        if (retries >= maxRetries) {
          reject(new Error(`Server at ${url} not ready after ${maxRetries} retries`));
        } else {
          setTimeout(check, interval);
        }
      });
    };
    check();
  });
}

async function startServers() {
  const projectRoot = path.resolve(__dirname, '..', '..', '..');

  console.log('Starting backend server with TEST_MODE=true...');
  backendProcess = spawn('uvicorn', ['app.main:app', '--port', '8000', '--host', '0.0.0.0'], {
    cwd: projectRoot,
    env: { ...process.env, TEST_MODE: 'true' },
    stdio: ['pipe', 'pipe', 'pipe'],
  });

  backendProcess.stdout.on('data', (data) => {
    console.log(`[backend] ${data.toString().trim()}`);
  });
  backendProcess.stderr.on('data', (data) => {
    console.log(`[backend] ${data.toString().trim()}`);
  });

  console.log('Starting frontend dev server...');
  frontendProcess = spawn('npx', ['vite', '--port', '5173', '--strictPort'], {
    cwd: path.resolve(projectRoot, 'frontend'),
    env: { ...process.env },
    stdio: ['pipe', 'pipe', 'pipe'],
  });

  frontendProcess.stdout.on('data', (data) => {
    console.log(`[frontend] ${data.toString().trim()}`);
  });
  frontendProcess.stderr.on('data', (data) => {
    console.log(`[frontend] ${data.toString().trim()}`);
  });

  console.log('Waiting for backend to be ready...');
  await waitForServer('http://localhost:8000/docs', 30, 1000);
  console.log('Backend is ready!');

  console.log('Waiting for frontend to be ready...');
  await waitForServer('http://localhost:5173', 30, 1000);
  console.log('Frontend is ready!');
}

function stopServers() {
  if (backendProcess) {
    console.log('Stopping backend server...');
    backendProcess.kill('SIGTERM');
    backendProcess = null;
  }
  if (frontendProcess) {
    console.log('Stopping frontend server...');
    frontendProcess.kill('SIGTERM');
    frontendProcess = null;
  }
}

module.exports = { startServers, stopServers };
