const { spawn, execSync } = require('child_process');
const http = require('http');
const path = require('path');

let backendProcess = null;

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
  const frontendDir = path.resolve(projectRoot, 'frontend');

  // Build frontend so backend can serve it directly (avoids Vite WS proxy issues)
  console.log('Building frontend...');
  execSync('npx vite build', { cwd: frontendDir, stdio: 'inherit' });
  console.log('Frontend built!');

  console.log('Starting backend server with TEST_MODE=true...');
  backendProcess = spawn('uvicorn', ['app.main:app', '--port', '8000', '--host', '0.0.0.0'], {
    cwd: projectRoot,
    env: { ...process.env, TEST_MODE: 'true', SERVE_FRONTEND: 'true' },
    stdio: ['pipe', 'pipe', 'pipe'],
  });

  backendProcess.stdout.on('data', (data) => {
    console.log(`[backend] ${data.toString().trim()}`);
  });
  backendProcess.stderr.on('data', (data) => {
    console.log(`[backend] ${data.toString().trim()}`);
  });

  console.log('Waiting for backend to be ready...');
  await waitForServer('http://localhost:8000/docs', 30, 1000);
  console.log('Backend is ready!');
}

function stopServers() {
  if (backendProcess) {
    console.log('Stopping backend server...');
    backendProcess.kill('SIGTERM');
    backendProcess = null;
  }
}

module.exports = { startServers, stopServers };
