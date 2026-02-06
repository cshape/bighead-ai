const puppeteer = require('puppeteer');
const { startServers, stopServers } = require('./setup');

const BASE_URL = 'http://localhost:8000';

jest.setTimeout(120000);

describe('Jeopardy E2E Tests', () => {
  let browser;
  let hostContext, aliceContext, bobContext;
  let hostPage, alicePage, bobPage;

  beforeAll(async () => {
    await startServers();

    browser = await puppeteer.launch({
      headless: 'new',
      args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1280,800'],
    });
  });

  afterAll(async () => {
    if (browser) await browser.close();
    stopServers();
  });

  // Helper: wait for selector with longer timeout
  const waitFor = (page, selector, opts = {}) =>
    page.waitForSelector(selector, { timeout: 15000, ...opts });

  // Helper: short delay
  const delay = (ms) => new Promise((r) => setTimeout(r, ms));

  // Helper: get the LAST controlling player's name from chat messages
  const getControllingPlayer = (page) =>
    page.evaluate(() => {
      const chatTexts = [...document.querySelectorAll('.message-text')];
      for (let j = chatTexts.length - 1; j >= 0; j--) {
        const text = chatTexts[j].textContent || '';
        const match = text.match(/(\w+), you have control of the board/);
        if (match) return match[1];
      }
      return null;
    });

  // Helper: wait for a controlling player to be assigned
  const waitForControllingPlayer = async (page, maxAttempts = 30) => {
    for (let i = 0; i < maxAttempts; i++) {
      const player = await getControllingPlayer(page);
      if (player) return player;
      await delay(500);
    }
    return null;
  };

  test('Create game, join with 3 players, and start', async () => {
    // --- Host creates game ---
    hostContext = await browser.createBrowserContext();
    hostPage = await hostContext.newPage();
    await hostPage.setViewport({ width: 1280, height: 800 });
    await hostPage.goto(BASE_URL, { waitUntil: 'networkidle0' });

    // Click CREATE GAME to show the create form
    await waitFor(hostPage, '.create-button');
    await hostPage.click('.create-button');

    // Fill in host name and preferences
    await waitFor(hostPage, '#playerName');
    await hostPage.type('#playerName', 'Host');
    await hostPage.type('#preferences', 'Science');

    // Click CREATE (submit the form)
    await hostPage.click('.create-button');

    // Wait for redirect to lobby (host arrives already registered)
    await hostPage.waitForFunction(
      () => window.location.pathname.includes('/lobby'),
      { timeout: 15000 }
    );
    console.log('Host redirected to lobby');

    // Extract game code
    await waitFor(hostPage, '.game-code');
    const gameCode = await hostPage.$eval('.game-code', (el) => el.textContent.trim());
    console.log(`Game code: ${gameCode}`);
    expect(gameCode).toMatch(/^[A-Z0-9]{6}$/);

    // Host should already appear in the player list
    await waitFor(hostPage, '.player-item');
    console.log('Host visible in player list');

    // --- Alice joins ---
    aliceContext = await browser.createBrowserContext();
    alicePage = await aliceContext.newPage();
    await alicePage.setViewport({ width: 1280, height: 800 });
    await alicePage.goto(BASE_URL, { waitUntil: 'networkidle0' });

    await waitFor(alicePage, '.join-button');
    await alicePage.click('.join-button');

    await waitFor(alicePage, '#gameCode');
    await alicePage.type('#gameCode', gameCode);
    await alicePage.type('#playerName', 'Alice');

    await alicePage.click('.join-button');

    await alicePage.waitForFunction(
      () => window.location.pathname.includes('/lobby'),
      { timeout: 10000 }
    );
    console.log('Alice joined lobby');

    // --- Bob joins ---
    bobContext = await browser.createBrowserContext();
    bobPage = await bobContext.newPage();
    await bobPage.setViewport({ width: 1280, height: 800 });
    await bobPage.goto(BASE_URL, { waitUntil: 'networkidle0' });

    await waitFor(bobPage, '.join-button');
    await bobPage.click('.join-button');

    await waitFor(bobPage, '#gameCode');
    await bobPage.type('#gameCode', gameCode);
    await bobPage.type('#playerName', 'Bob');

    await bobPage.click('.join-button');

    await bobPage.waitForFunction(
      () => window.location.pathname.includes('/lobby'),
      { timeout: 10000 }
    );
    console.log('Bob joined lobby');

    // Wait for host to see 3 players (via WS broadcast or API fetch)
    await hostPage.waitForFunction(
      () => document.querySelectorAll('.player-item:not(.empty)').length >= 3,
      { timeout: 15000 }
    );
    console.log('Host sees 3 players');

    // Wait for start button to become enabled
    await waitFor(hostPage, '.start-button:not([disabled])', { timeout: 10000 });
    console.log('Start button enabled');

    // Click START GAME
    await hostPage.click('.start-button');

    // All pages should see the board
    await Promise.all([
      waitFor(hostPage, '.category-title', { timeout: 60000 }),
      waitFor(alicePage, '.category-title', { timeout: 60000 }),
      waitFor(bobPage, '.category-title', { timeout: 60000 }),
    ]);
    console.log('Board visible on all pages');

    // Verify 5 categories
    const categories = await hostPage.$$('.category-title');
    expect(categories.length).toBe(5);

    // Verify 3 players in scoreboard, all with $0
    const scores = await hostPage.$$eval('.player-score', (els) =>
      els.map((el) => ({
        name: el.querySelector('.player-name')?.textContent,
        score: el.querySelector('.score')?.textContent,
      }))
    );
    expect(scores.length).toBe(3);
    expect(scores.map((s) => s.name)).toEqual(expect.arrayContaining(['Host', 'Alice', 'Bob']));
    scores.forEach((s) => expect(s.score).toBe('$0'));
    console.log('Test 1 passed: Game created, joined, and started');
  });

  test('Controlling player picks a clue, player buzzes in with correct answer', async () => {
    const pages = { Host: hostPage, Alice: alicePage, Bob: bobPage };

    // Wait for the backend to assign a controlling player
    const controllingPlayer = await waitForControllingPlayer(hostPage);
    console.log(`Controlling player: ${controllingPlayer}`);
    expect(controllingPlayer).toBeTruthy();

    const controlPage = pages[controllingPlayer];
    expect(controlPage).toBeTruthy();

    // Let WebSocket stabilize after page transition before clicking
    await delay(500);

    // Click the first question ($200 in first category) from the controlling player's page
    const questions = await controlPage.$$('.question:not(.used)');
    expect(questions.length).toBeGreaterThan(0);
    await questions[0].click();
    console.log(`${controllingPlayer} clicked $200 clue`);

    // Wait for question modal to appear on all pages
    await Promise.all([
      waitFor(hostPage, '.modal-overlay', { timeout: 15000 }),
      waitFor(alicePage, '.modal-overlay', { timeout: 15000 }),
      waitFor(bobPage, '.modal-overlay', { timeout: 15000 }),
    ]);
    console.log('Question modal visible on all pages');

    // Pick a non-controlling player to buzz in
    const buzzerPlayerName = controllingPlayer === 'Alice' ? 'Bob' : 'Alice';
    const buzzerPage = pages[buzzerPlayerName];

    // Wait for buzzer to activate
    await waitFor(buzzerPage, '.player-buzzer.active', { timeout: 15000 });
    console.log(`Buzzer active on ${buzzerPlayerName} page`);

    // Buzzer player buzzes in
    await buzzerPage.click('.player-buzzer.active');
    console.log(`${buzzerPlayerName} buzzed in`);

    // Wait for answer input to appear
    await waitFor(buzzerPage, '.answer-input', { timeout: 10000 });

    // Type the correct answer
    await buzzerPage.type('.answer-input', 'What is the lemon');
    await buzzerPage.click('.answer-submit-btn');
    console.log(`${buzzerPlayerName} submitted answer`);

    // Wait for modal to dismiss (correct answer dismisses the question)
    await hostPage.waitForSelector('.modal-overlay', { hidden: true, timeout: 15000 });
    console.log('Modal dismissed after correct answer');

    // Give the score update a moment to propagate
    await delay(1000);

    // Verify the buzzer player's score is $200
    const score = await hostPage.evaluate((name) => {
      const els = document.querySelectorAll('.player-score');
      for (const el of els) {
        if (el.querySelector('.player-name')?.textContent === name) {
          return el.querySelector('.score')?.textContent;
        }
      }
      return null;
    }, buzzerPlayerName);
    expect(score).toBe('$200');
    console.log(`Test 2 passed: ${buzzerPlayerName} answered correctly and has $200`);
  });

  test('Player picks clue after correct answer, another player gives incorrect answer', async () => {
    const pages = { Host: hostPage, Alice: alicePage, Bob: bobPage };

    // The player who answered correctly now has board control
    // Wait for the new "you have control" message
    await delay(1000);
    const controllingPlayer = await waitForControllingPlayer(hostPage);
    console.log(`Controlling player for test 3: ${controllingPlayer}`);
    expect(controllingPlayer).toBeTruthy();

    const controlPage = pages[controllingPlayer];

    // Click the first non-used question from the controlling player's page
    const clicked = await controlPage.evaluate(() => {
      const categories = document.querySelectorAll('.category');
      if (categories.length > 0) {
        const q = categories[0].querySelector('.question:not(.used)');
        if (q) { q.click(); return true; }
      }
      return false;
    });
    expect(clicked).toBe(true);
    console.log(`${controllingPlayer} clicked next clue`);

    // Wait for question modal to appear
    await Promise.all([
      waitFor(hostPage, '.modal-overlay', { timeout: 15000 }),
      waitFor(alicePage, '.modal-overlay', { timeout: 15000 }),
      waitFor(bobPage, '.modal-overlay', { timeout: 15000 }),
    ]);
    console.log('Question modal visible on all pages');

    // Pick a different player to buzz in and give a wrong answer
    const wrongPlayerName = controllingPlayer === 'Bob' ? 'Alice' : 'Bob';
    const wrongPage = pages[wrongPlayerName];

    // Wait for buzzer to activate
    await waitFor(wrongPage, '.player-buzzer.active', { timeout: 15000 });
    console.log(`Buzzer active on ${wrongPlayerName} page`);

    // Wrong player buzzes in
    await wrongPage.click('.player-buzzer.active');
    console.log(`${wrongPlayerName} buzzed in`);

    // Wait for answer input
    await waitFor(wrongPage, '.answer-input', { timeout: 10000 });

    // Give an incorrect answer
    await wrongPage.type('.answer-input', 'What is zombie');
    await wrongPage.click('.answer-submit-btn');
    console.log(`${wrongPlayerName} submitted incorrect answer`);

    // Wait for score to update
    await delay(2000);

    // Check the wrong player's score - should be negative
    const wrongScore = await hostPage.evaluate((name) => {
      const els = document.querySelectorAll('.player-score');
      for (const el of els) {
        if (el.querySelector('.player-name')?.textContent === name) {
          return el.querySelector('.score')?.textContent;
        }
      }
      return null;
    }, wrongPlayerName);
    expect(wrongScore).toMatch(/^(\$-|-\$)/);
    console.log(`${wrongPlayerName} score: ${wrongScore}`);
    console.log('Test 3 passed: Incorrect answer deducted points');
  });
});
