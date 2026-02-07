const puppeteer = require('puppeteer');
const { startServers, stopServers, getBackendLogs } = require('./setup');

const BASE_URL = 'http://localhost:8000';

jest.setTimeout(120000);

describe('Big Head E2E Tests', () => {
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
    await stopServers();
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

  // Helper: get a player's score from the scoreboard
  const getPlayerScore = (page, playerName) =>
    page.evaluate((name) => {
      const els = document.querySelectorAll('.player-score');
      for (const el of els) {
        if (el.querySelector('.player-name')?.textContent === name) {
          return el.querySelector('.score')?.textContent;
        }
      }
      return null;
    }, playerName);

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

  test('All three players give incorrect answers to the same clue', async () => {
    const pages = { Host: hostPage, Alice: alicePage, Bob: bobPage };
    const allNames = ['Host', 'Alice', 'Bob'];

    // After test 3: HELLO, SUCKER! $400 is still active. One player answered wrong,
    // buzzer is reactivated for the other two. We need to find which two haven't answered.
    // We'll have them buzz in and answer wrong one at a time.

    for (let round = 0; round < 2; round++) {
      // Find a player whose buzzer is active (hasn't answered yet)
      let buzzerPlayer = null;
      let buzzerPage = null;

      for (const name of allNames) {
        const isActive = await pages[name].evaluate(() => {
          const buzzer = document.querySelector('.player-buzzer.active');
          return !!buzzer;
        });
        if (isActive) {
          buzzerPlayer = name;
          buzzerPage = pages[name];
          break;
        }
      }

      if (!buzzerPlayer) {
        // Buzzer may not be active yet — wait for it on any page
        for (const name of allNames) {
          try {
            await pages[name].waitForSelector('.player-buzzer.active', { timeout: 10000 });
            buzzerPlayer = name;
            buzzerPage = pages[name];
            break;
          } catch (e) {
            // This player's buzzer didn't activate, try next
          }
        }
      }

      expect(buzzerPlayer).toBeTruthy();
      console.log(`Round ${round + 1}: ${buzzerPlayer} buzzing in with wrong answer`);

      await buzzerPage.click('.player-buzzer.active');
      await waitFor(buzzerPage, '.answer-input', { timeout: 10000 });
      await buzzerPage.type('.answer-input', 'What is zombie');
      await buzzerPage.click('.answer-submit-btn');
      console.log(`${buzzerPlayer} submitted incorrect answer`);

      // Wait a moment for the backend to process and potentially reactivate buzzer
      await delay(2000);
    }

    // All three players have now answered incorrectly.
    // Wait for question to be dismissed (modal closes)
    await hostPage.waitForSelector('.modal-overlay', { hidden: true, timeout: 15000 });
    console.log('Modal dismissed after all players answered wrong');

    // Wait for chat to contain the "Nobody got it" message
    await hostPage.waitForFunction(
      () => {
        const msgs = [...document.querySelectorAll('.message-text')];
        return msgs.some((m) => m.textContent.includes('Nobody got it'));
      },
      { timeout: 10000 }
    );

    // Verify the correct answer was revealed
    const revealMsg = await hostPage.evaluate(() => {
      const msgs = [...document.querySelectorAll('.message-text')];
      const msg = msgs.find((m) => m.textContent.includes('Nobody got it'));
      return msg?.textContent || '';
    });
    expect(revealMsg).toContain('vampire');
    console.log(`Reveal message: ${revealMsg}`);

    // Wait for board control to be restored
    const controlPlayer = await waitForControllingPlayer(hostPage);
    expect(controlPlayer).toBeTruthy();
    console.log(`Board control restored to: ${controlPlayer}`);

    console.log('Test 4 passed: All three players answered incorrectly');
  });

  test('Double Big Head: player places wager and answers incorrectly', async () => {
    const pages = { Host: hostPage, Alice: alicePage, Bob: bobPage };

    // Wait for the controlling player (restored after test 4)
    await delay(1000);
    const controllingPlayer = await waitForControllingPlayer(hostPage);
    console.log(`Controlling player for test 5: ${controllingPlayer}`);
    expect(controllingPlayer).toBeTruthy();

    const controlPage = pages[controllingPlayer];

    // Click the TOYS & GAMES $800 question (the double big head).
    // Find the 4th category (TOYS & GAMES) and click its 4th question ($800).
    const clicked = await controlPage.evaluate(() => {
      const titles = [...document.querySelectorAll('.category-title')];
      const toysIdx = titles.findIndex((t) => t.textContent.includes('TOYS'));
      if (toysIdx === -1) return false;
      const categories = document.querySelectorAll('.category');
      const toysCat = categories[toysIdx];
      if (!toysCat) return false;
      // Questions are in order $200, $400, $600, $800, $1000
      const questions = toysCat.querySelectorAll('.question:not(.used)');
      // Find the $800 question
      for (const q of questions) {
        if (q.textContent.includes('800')) {
          q.click();
          return true;
        }
      }
      return false;
    });
    expect(clicked).toBe(true);
    console.log(`${controllingPlayer} clicked TOYS & GAMES $800 (Double Big Head)`);

    // Wait for double big head modal to appear on the controlling player's page
    await waitFor(controlPage, '.modal-content.double-big-head', { timeout: 15000 });
    console.log('Double Big Head modal visible');

    // Only the selecting player sees the bet input
    await waitFor(controlPage, '.bet-input', { timeout: 10000 });

    // Set the wager value via React's input handler
    await controlPage.evaluate(() => {
      const input = document.querySelector('.bet-input');
      if (input) {
        const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
          window.HTMLInputElement.prototype, 'value'
        ).set;
        nativeInputValueSetter.call(input, '500');
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
      }
    });
    await delay(200);

    // Submit the wager
    await controlPage.click('.bet-submit-btn');
    console.log(`${controllingPlayer} placed $500 wager`);

    // Wait for the question text to appear (after bet, question is revealed)
    await waitFor(controlPage, '.question-text', { timeout: 15000 });
    console.log('Question text revealed after bet');

    // Wait for the answer input to appear (last_buzzer is set to the selecting player)
    await waitFor(controlPage, '.answer-input', { timeout: 10000 });

    // Type incorrect answer and submit
    await controlPage.type('.answer-input', 'What is Monopoly');
    await controlPage.click('.answer-submit-btn');
    console.log(`${controllingPlayer} submitted incorrect double big head answer`);

    // Wait for modal to dismiss
    await controlPage.waitForSelector('.modal-overlay', { hidden: true, timeout: 15000 });
    console.log('Modal dismissed after wrong double big head answer');

    // Wait for the correct answer to be revealed in chat
    await hostPage.waitForFunction(
      () => {
        const msgs = [...document.querySelectorAll('.message-text')];
        return msgs.some((m) => m.textContent.includes('incorrect'));
      },
      { timeout: 10000 }
    );

    // Verify score was deducted by $500
    await delay(1000);
    const score = await getPlayerScore(hostPage, controllingPlayer);
    console.log(`${controllingPlayer} score after double big head: ${score}`);
    // Alice: $200 (test 2) - $400 (test 4) - $500 (DD wager) = -$700
    expect(score).toBe('$-700');

    // Verify controlling player retains board control
    const newControl = await waitForControllingPlayer(hostPage);
    expect(newControl).toBe(controllingPlayer);
    console.log(`${controllingPlayer} retains board control after double big head`);

    console.log('Test 5 passed: Double Big Head incorrect answer handled correctly');
  });
});
