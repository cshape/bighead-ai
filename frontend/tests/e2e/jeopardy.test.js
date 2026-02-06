const puppeteer = require('puppeteer');
const { startServers, stopServers } = require('./setup');

const BASE_URL = 'http://localhost:5173';

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

    // Click "JOIN GAME" to reveal the join form
    await waitFor(alicePage, '.join-button');
    await alicePage.click('.join-button');

    // Fill in the join form
    await waitFor(alicePage, '#gameCode');
    await alicePage.type('#gameCode', gameCode);
    await alicePage.type('#playerName', 'Alice');

    // Click "JOIN" (submit)
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

    // Click "JOIN GAME" to reveal the join form
    await waitFor(bobPage, '.join-button');
    await bobPage.click('.join-button');

    // Fill in the join form
    await waitFor(bobPage, '#gameCode');
    await bobPage.type('#gameCode', gameCode);
    await bobPage.type('#playerName', 'Bob');

    // Click "JOIN" (submit)
    await bobPage.click('.join-button');

    await bobPage.waitForFunction(
      () => window.location.pathname.includes('/lobby'),
      { timeout: 10000 }
    );
    console.log('Bob joined lobby');

    // Verify backend has 3 players via direct API call
    const apiResponse = await hostPage.evaluate(async (code) => {
      const res = await fetch(`http://localhost:8000/api/games/code/${code}`);
      return res.json();
    }, gameCode);
    console.log('API response players:', JSON.stringify(apiResponse.players));
    console.log('API response player_count:', apiResponse.player_count);

    // Navigate host back to lobby to pick up all 3 players from API
    // (Vite WS proxy drops connections, so WS broadcasts don't always reach the lobby)
    await hostPage.goto(`${BASE_URL}/game/${gameCode}/lobby`, { waitUntil: 'networkidle0' });
    console.log('Host navigated to lobby');

    // Debug: check what's on the page
    await delay(2000);
    const pageDebug = await hostPage.evaluate(() => {
      const items = document.querySelectorAll('.player-item');
      const nonEmpty = document.querySelectorAll('.player-item:not(.empty)');
      return {
        allItems: items.length,
        nonEmptyItems: nonEmpty.length,
        html: document.querySelector('.players-list')?.innerHTML || 'NO .players-list found',
        bodyText: document.body.innerText.substring(0, 500),
      };
    });
    console.log('Page debug:', JSON.stringify(pageDebug, null, 2));

    // Wait for 3 player items to appear (from API fetch)
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
    // Host has control (first registered player). Click the $200 clue in first category.
    const questions = await hostPage.$$('.question');
    expect(questions.length).toBeGreaterThan(0);

    // Click the first question ($200 in first category "HELLO, SUCKER!")
    await questions[0].click();
    console.log('Host clicked $200 clue');

    // Wait for question modal to appear on all pages
    await Promise.all([
      waitFor(hostPage, '.modal-overlay', { timeout: 15000 }),
      waitFor(alicePage, '.modal-overlay', { timeout: 15000 }),
      waitFor(bobPage, '.modal-overlay', { timeout: 15000 }),
    ]);
    console.log('Question modal visible on all pages');

    // Wait for buzzer to activate (backend sends buzzer_status after short delay in TEST_MODE)
    // The frontend has a 500ms delay before showing active state
    await waitFor(alicePage, '.player-buzzer.active', { timeout: 15000 });
    console.log('Buzzer active on Alice page');

    // Alice buzzes in
    await alicePage.click('.player-buzzer.active');
    console.log('Alice buzzed in');

    // Wait for answer input to appear on Alice's page
    await waitFor(alicePage, '.answer-input', { timeout: 10000 });

    // Type the correct answer: "the lemon" (expected answer is "the lemon (or lime)")
    await alicePage.type('.answer-input', 'What is the lemon');
    await alicePage.click('.answer-submit-btn');
    console.log('Alice submitted answer');

    // Wait for modal to dismiss (correct answer dismisses the question)
    await hostPage.waitForSelector('.modal-overlay', { hidden: true, timeout: 15000 });
    console.log('Modal dismissed after correct answer');

    // Give the score update a moment to propagate
    await delay(1000);

    // Verify Alice's score is $200
    const aliceScore = await hostPage.evaluate(() => {
      const els = document.querySelectorAll('.player-score');
      for (const el of els) {
        if (el.querySelector('.player-name')?.textContent === 'Alice') {
          return el.querySelector('.score')?.textContent;
        }
      }
      return null;
    });
    expect(aliceScore).toBe('$200');
    console.log('Test 2 passed: Alice answered correctly and has $200');
  });

  test('Player picks clue after correct answer, another player gives incorrect answer', async () => {
    // Alice now has board control (she answered correctly in previous test)
    // Wait for Alice to have the "select question" state
    await delay(1000);

    // Get the first non-used question in the first category column ($400)
    const clicked = await alicePage.evaluate(() => {
      const categories = document.querySelectorAll('.category');
      if (categories.length > 0) {
        const q = categories[0].querySelector('.question:not(.used)');
        if (q) { q.click(); return true; }
      }
      return false;
    });
    expect(clicked).toBe(true);
    console.log('Alice clicked $400 clue');

    // Wait for question modal to appear
    await Promise.all([
      waitFor(hostPage, '.modal-overlay', { timeout: 15000 }),
      waitFor(alicePage, '.modal-overlay', { timeout: 15000 }),
      waitFor(bobPage, '.modal-overlay', { timeout: 15000 }),
    ]);
    console.log('Question modal visible on all pages');

    // Wait for buzzer to activate
    await waitFor(bobPage, '.player-buzzer.active', { timeout: 15000 });
    console.log('Buzzer active on Bob page');

    // Bob buzzes in
    await bobPage.click('.player-buzzer.active');
    console.log('Bob buzzed in');

    // Wait for answer input on Bob's page
    await waitFor(bobPage, '.answer-input', { timeout: 10000 });

    // Bob gives an incorrect answer
    await bobPage.type('.answer-input', 'What is zombie');
    await bobPage.click('.answer-submit-btn');
    console.log('Bob submitted incorrect answer');

    // Wait for score to update
    await delay(2000);

    // Check Bob's score - should be -$400
    const bobScore = await hostPage.evaluate(() => {
      const els = document.querySelectorAll('.player-score');
      for (const el of els) {
        if (el.querySelector('.player-name')?.textContent === 'Bob') {
          return el.querySelector('.score')?.textContent;
        }
      }
      return null;
    });
    expect(bobScore).toBe('-$400');
    console.log(`Bob score: ${bobScore}`);
    console.log('Test 3 passed: Bob answered incorrectly and has -$400');
  });
});
